from __future__ import annotations

import os
import io
import csv
import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from flask import Blueprint, jsonify, request, g, current_app
from pymongo import UpdateOne

from extensions import mongo
from auth import requires_auth

api = Blueprint("api", __name__, url_prefix="/api")

# ---------------- Basics ----------------

def _json_ok(**kwargs):
    d = {"ok": True}
    d.update(kwargs)
    return jsonify(d)

def _json_err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code

def _now_utc() -> datetime:
    return datetime.utcnow()

def _parse_int(v, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default

# ---------------- LLM: Gemini helpers ----------------

def _gemini_post(payload: dict, timeout: int | None = None) -> dict:
    api_base = os.getenv("LLM_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    api_key  = (os.getenv("LLM_API_KEY") or "").strip()
    model    = "gemini-2.5-flash"
    timeout  = int(os.getenv("LLM_TIMEOUT_SECONDS", "60")) if timeout is None else timeout
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set")
    url = f"{api_base}/models/{model}:generateContent"
    r = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    return r.json()

def _extract_json(txt: str) -> dict:
    if not isinstance(txt, str):
        raise ValueError("Respuesta vacía")
    s = txt.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s, flags=re.DOTALL)
        s = re.sub(r"\s*```$", "", s, flags=re.DOTALL)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        raise ValueError("No se encontró JSON en la respuesta del modelo")
    return json.loads(m.group(0))

def _gemini_generate_json(prompt: str, max_tokens: int = 30000, temperature: float = 0.7, top_p: float = 0.9) -> dict:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "candidateCount": 1
        },
    }
    data = _gemini_post(payload)
    try:
        txt = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"Respuesta Gemini inesperada: {json.dumps(data)[:600]}")
    try:
        return _extract_json(txt)
    except Exception as e:
        raise RuntimeError(f"JSON inválido de Gemini: {e}")

# ---------------- Perfil ----------------

@api.get("/me")
@requires_auth
def get_me():
    sub = g.current_user.get("sub")
    doc = mongo.db.users.find_one({"sub": sub})
    if not doc:
        return _json_err("Perfil no encontrado", 404)
    doc["_id"] = str(doc["_id"])
    return _json_ok(**doc)

@api.put("/me/profile")
@requires_auth
def update_profile():
    sub = g.current_user.get("sub")
    body = request.get_json(force=True, silent=True) or {}

    allowed = {"birthdate", "sex", "height_cm", "weight_kg", "notes"}
    profile_updates = {k: v for k, v in body.items() if k in allowed}

    base_updates = {}
    if "name" in body:  base_updates["name"]  = body.get("name")
    if "email" in body: base_updates["email"] = body.get("email")

    if not profile_updates and not base_updates:
        return _json_err("Nada que actualizar", 400)

    now = _now_utc()
    set_ops = {"updated_at": now, "profileComplete": True}
    set_ops.update(base_updates)
    for k, v in profile_updates.items():
        set_ops[f"profile.{k}"] = v

    mongo.db.users.update_one({"sub": sub}, {"$set": set_ops}, upsert=True)

    doc = mongo.db.users.find_one({"sub": sub})
    doc["_id"] = str(doc["_id"])
    return _json_ok(user=doc)

@api.post("/me/sync")
@requires_auth
def sync_me():
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    email   = g.current_user.get("email")  or body.get("email")
    name    = g.current_user.get("name")   or body.get("name")
    picture = g.current_user.get("picture") or body.get("picture")

    now = _now_utc()
    mongo.db.users.update_one(
        {"sub": sub},
        {
            "$setOnInsert": {"sub": sub, "created_at": now},
            "$set": {"last_login": now, "email": email, "name": name, "picture": picture},
        },
        upsert=True,
    )
    doc = mongo.db.users.find_one({"sub": sub})
    doc["_id"] = str(doc["_id"])
    return _json_ok(user=doc)

# ---------------- Utiles de fecha ----------------

from dateutil import parser as dtparser

def _parse_any_datetime(s: str) -> Optional[datetime]:
    try:
        return dtparser.parse(s)
    except Exception:
        return None

# ---------------- Métricas (series y detalle) ----------------

@api.get("/metrics/series")
@requires_auth
def metrics_series():
    sub = g.current_user.get("sub")
    mtype = request.args.get("type")
    if not mtype:
        return _json_err("Falta type", 400)

    from_str = request.args.get("from")
    to_str   = request.args.get("to")

    def _parse_iso(s):
        try:
            return dtparser.parse(s)
        except Exception:
            return None

    if from_str and to_str:
        t_from = _parse_iso(from_str)
        t_to   = _parse_iso(to_str)
        if not t_from or not t_to or t_from >= t_to:
            return _json_err("Parámetros from/to inválidos", 400)
    else:
        minutes = _parse_int(request.args.get("minutes", 60), 60)
        t_to = _now_utc()
        t_from = t_to - timedelta(minutes=minutes)

    cur = mongo.db.measurements.find(
        {"sub": sub, "type": mtype, "ts": {"$gte": t_from, "$lte": t_to}},
        {"_id": 0, "ts": 1, "value": 1},
    ).sort("ts", 1)

    points = [{"t": d["ts"].isoformat(), "v": d.get("value")} for d in cur]
    return _json_ok(points=points, from_=t_from.isoformat(), to_=t_to.isoformat())

@api.get("/metrics/detail")
@requires_auth
def metrics_detail():
    sub = g.current_user.get("sub")
    mtype = request.args.get("type")
    ts_str = request.args.get("ts")
    if not mtype or not ts_str:
        return _json_err("Faltan parámetros type y ts", 400)
    try:
        ts = dtparser.parse(ts_str)
    except Exception:
        return _json_err("ts inválido", 400)

    meas = mongo.db.measurements.find_one(
        {"sub": sub, "type": mtype, "ts": ts},
        projection={"_id": 0, "value": 1, "ts": 1, "advice": 1, "source": 1, "scored_at": 1},
    )
    if not meas:
        return _json_err("No existe medición en ese instante", 404)

    # Devuelve features del RAW correspondiente
    features = None
    raw = None
    if mtype == "sleep":
        raw = mongo.db.sleep_raw.find_one({"sub": sub, "ts": ts}, projection={"_id": 0, "features": 1})
    elif mtype == "stress":
        raw = mongo.db.stress_raw.find_one({"sub": sub, "ts": ts}, projection={"_id": 0, "features": 1})
    if raw and isinstance(raw.get("features"), dict):
        features = raw["features"]

    return _json_ok(
        value=meas.get("value"),
        ts=meas.get("ts").isoformat(),
        advice=meas.get("advice"),
        source=meas.get("source"),
        scored_at=meas.get("scored_at").isoformat() if meas.get("scored_at") else None,
        features=features,
    )

@api.get("/metrics/detail/by_date")
@requires_auth
def metrics_detail_by_date():
    sub = g.current_user.get("sub")
    mtype = request.args.get("type")
    date_str = request.args.get("date")
    if not mtype or not date_str:
        return _json_err("Faltan parámetros type y date (YYYY-MM-DD)", 400)

    try:
        d = dtparser.parse(date_str)
    except Exception:
        return _json_err("date inválido (usa YYYY-MM-DD)", 400)

    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1) - timedelta(microseconds=1000)

    meas = mongo.db.measurements.find_one(
        {"sub": sub, "type": mtype, "ts": {"$gte": start, "$lte": end}},
        projection={"_id": 0, "value": 1, "ts": 1, "advice": 1, "source": 1, "scored_at": 1},
    )
    if not meas:
        return _json_err("No existe medición para esa fecha", 404)

    features = None
    raw = None
    if mtype == "sleep":
        raw = mongo.db.sleep_raw.find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}}, projection={"_id": 0, "features": 1})
    elif mtype == "stress":
        raw = mongo.db.stress_raw.find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}}, projection={"_id": 0, "features": 1})
    if raw and isinstance(raw.get("features"), dict):
        features = raw["features"]

    return _json_ok(
        value=meas.get("value"),
        ts=meas.get("ts").isoformat(),
        advice=meas.get("advice"),
        source=meas.get("source"),
        scored_at=meas.get("scored_at").isoformat() if meas.get("scored_at") else None,
        features=features,
    )

# ---------------- Simulaciones (IA, gemelo digital) ----------------

def _prompt_interventions(metric: str) -> str:
    return (
        f"Eres un asistente de salud. Propón exactamente 3 intervenciones realistas y breves para mejorar '{metric}'.\n"
        "Devuelve ÚNICAMENTE JSON válido (sin Markdown ni ```), con esta forma exacta:\n"
        '{ "interventions": [\n'
        '  { "title": "…", "description": "…", "category": "…", "effort": 1 },\n'
        '  { "title": "…", "description": "…", "category": "…", "effort": 2 },\n'
        '  { "title": "…", "description": "…", "category": "…", "effort": 3 }\n'
        "] }"
    )

def _prompt_simulate_point(metric: str, features: Dict[str, Any], base_val: int, interventions: List[Dict[str, Any]]) -> str:
    return (
        "Actúa como un gemelo digital humano que estima el resultado tras aplicar intervenciones de bienestar.\n"
        "Tarea: con los DATOS de un día y unas INTERVENCIONES propuestas, estima la puntuación esperada para el próximo ciclo si la persona aplica las intervenciones con adherencia ~70%.\n"
        "Escala entera 1–5 (1=peor, 5=excelente). No asumas mejora automática.\n"
        "Devuelve SOLO JSON válido (sin Markdown ni ```) con esta forma exacta:\n"
        '{ "after_score": 3, "rationale": "explica en 1-2 frases por qué sube/baja o se mantiene" }\n\n'
        f"Métrica: {metric}\n"
        f"Puntuación real previa (base): {base_val}\n"
        "Datos:\n"
        f"{json.dumps(features, ensure_ascii=False)}\n"
        "Intervenciones:\n"
        f"{json.dumps(interventions, ensure_ascii=False)}\n"
        "Reglas:\n"
        "- Usa SOLO números enteros 1..5 para after_score.\n"
        "- Sé conservador si el dato ya es 5."
    )

def _prompt_interventions_day(metric: str, features: Dict[str, Any], base_val: int) -> str:
    return (
        "Eres un asistente de salud personal que diseña intervenciones específicas por día.\n"
        "Tarea: con los DATOS de un día y su PUNTUACIÓN real (1–5), propone exactamente 3 intervenciones breves y concretas, "
        "adaptadas a ese día en particular. Si el día es 1/5 usa medidas más intensivas; si es 4/5 usa ajustes finos.\n"
        "Devuelve SOLO JSON válido (sin Markdown ni ```) con esta forma exacta:\n"
        '{ "interventions": [\n'
        '  { "title": "…", "description": "…", "category": "…", "effort": 1 },\n'
        '  { "title": "…", "description": "…", "category": "…", "effort": 2 },\n'
        '  { "title": "…", "description": "…", "category": "…", "effort": 3 }\n'
        "] }\n\n"
        f"Métrica: {metric}\n"
        f"Puntuación real del día: {base_val}\n"
        "Datos del día:\n"
        f"{json.dumps(features, ensure_ascii=False)}\n"
        "Reglas:\n"
        "- Deben ser accionables hoy o en el próximo ciclo.\n"
        "- No repitas exactamente las mismas intervenciones entre días si los datos difieren.\n"
        "- Mantén títulos cortos y descripciones concretas.\n"
    )

@api.get("/simulations/latest")
@requires_auth
def simulations_latest():
    sub = g.current_user.get("sub")
    metric = request.args.get("metric")
    if not metric:
        return _json_err("Falta metric", 400)

    sim = mongo.db.simulations.find_one({"sub": sub, "metric": metric}, sort=[("created_at", -1)])
    if not sim:
        return _json_err("No hay simulación", 404)

    sim["_id"] = str(sim["_id"])
    return _json_ok(**sim)

@api.get("/simulations/by_date")
@requires_auth
def simulations_by_date():
    sub = g.current_user.get("sub")
    metric = request.args.get("metric")
    date_str = request.args.get("date")
    if not metric or not date_str:
        return _json_err("Faltan metric y date (YYYY-MM-DD)", 400)

    try:
        d = dtparser.parse(date_str)
    except Exception:
        return _json_err("date inválido", 400)

    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1) - timedelta(microseconds=1000)

    sim = mongo.db.simulations.find_one({"sub": sub, "metric": metric}, sort=[("created_at", -1)])
    if not sim:
        return _json_err("No hay simulación", 404)

    entry = None
    for it in sim.get("forecast", []):
        try:
            ts = dtparser.parse(it.get("ts"))
            if start <= ts <= end:
                entry = it
                break
        except Exception:
            continue

    if not entry:
        return _json_err("No hay simulación para esa fecha", 404)

    return _json_ok(
        ts=entry.get("ts"),
        base=entry.get("base"),
        sim=entry.get("value"),
        delta=entry.get("delta"),
        rationale=entry.get("rationale"),
        interventions=entry.get("interventions", []),
        created_at=sim.get("created_at"),
        forecast_mode=sim.get("forecast_mode"),
    )

@api.delete("/simulations")
@requires_auth
def simulations_delete():
    sub = g.current_user.get("sub")
    metric = request.args.get("metric")
    q = {"sub": sub}
    if metric:
        q["metric"] = metric
    res = mongo.db.simulations.delete_many(q)
    return _json_ok(deleted=res.deleted_count)

@api.post("/ai/simulate/<metric>")
@requires_auth
def ai_simulate_metric(metric: str):
    """
    Gemelo digital (sleep/stress):
      - Por cada fecha con medición real: pide 3 intervenciones específicas del día y simula 'after_score'.
      - Guarda: ts, base, value(sim), delta, rationale, interventions.
    """
    sub = g.current_user.get("sub")
    metric = (metric or "").strip().lower()

    # Historico real
    real_rows = list(mongo.db.measurements.find(
        {"sub": sub, "type": metric},
        projection={"_id": 0, "ts": 1, "value": 1}
    ).sort("ts", 1))
    if not real_rows:
        return _json_err("No hay datos históricos para simular", 404)

    # Features por ts desde RAW
    features_by_ts: Dict[str, Dict[str, Any]] = {}
    raw_col = mongo.db.sleep_raw if metric == "sleep" else mongo.db.stress_raw
    raw_rows = raw_col.find({"sub": sub}, projection={"_id": 0, "ts": 1, "features": 1})
    for r in raw_rows:
        if r.get("ts") and isinstance(r.get("features"), dict):
            features_by_ts[r["ts"].isoformat()] = r["features"]

    forecast_abs: List[Dict[str, Any]] = []
    improved = same = worse = 0
    deltas: List[int] = []

    for r in real_rows:
        ts_iso = r["ts"].isoformat()
        base_val = int(r.get("value") or 3)
        features = features_by_ts.get(ts_iso) or {}

        # Intervenciones del día
        day_interventions: List[Dict[str, Any]] = []
        try:
            day_json = _gemini_generate_json(_prompt_interventions_day(metric, features, base_val),
                                             max_tokens=30000, temperature=0.8, top_p=0.9)
            raw_list = day_json.get("interventions", [])
            for it in raw_list if isinstance(raw_list, list) else []:
                if isinstance(it, dict) and it.get("title") and it.get("description"):
                    day_interventions.append({
                        "title": str(it["title"])[:200],
                        "description": str(it["description"])[:800],
                        "category": (str(it.get("category") or "general")[:60]),
                        "effort": int(it.get("effort") or 2),
                    })
        except Exception as e:
            current_app.logger.warning(f"LLM day interventions error: {e}")

        while len(day_interventions) < 3:
            day_interventions.append({
                "title": "Ajuste breve",
                "description": "Pequeño ajuste recomendado para este día.",
                "category": "general",
                "effort": 2
            })

        # Simulación
        sim_val = base_val
        rationale = ""
        try:
            prompt = _prompt_simulate_point(metric, features, base_val, day_interventions)
            out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.6, top_p=0.9)
            sim_raw = int(out.get("after_score"))
            if 1 <= sim_raw <= 5:
                sim_val = sim_raw
            rationale = str(out.get("rationale") or "")[:300]
        except Exception as e:
            current_app.logger.warning(f"LLM simulate row error: {e}")

        delta = sim_val - base_val
        if delta > 0: improved += 1
        elif delta == 0: same += 1
        else: worse += 1
        deltas.append(delta)

        try:
            titles = "; ".join([it["title"] for it in day_interventions])
            current_app.logger.info(
                "[SIM_ROW] sub=%s metric=%s ts=%s base=%s -> sim=%s Δ=%+d day_interventions=%s reason=%s",
                sub, metric, ts_iso, base_val, sim_val, delta, titles, rationale
            )
        except Exception:
            pass

        forecast_abs.append({
            "ts": ts_iso,
            "value": int(sim_val),
            "base": int(base_val),
            "delta": int(delta),
            "rationale": rationale,
            "interventions": day_interventions,
        })

    try:
        avg_delta = (sum(deltas) / len(deltas)) if deltas else 0.0
        current_app.logger.info(
            "[SIM_SUMMARY] sub=%s metric=%s total=%s improved=%s same=%s worse=%s avg_delta=%.2f",
            sub, metric, len(real_rows), improved, same, worse, avg_delta
        )
    except Exception:
        pass

    doc = {
        "sub": sub,
        "metric": metric,
        "created_at": _now_utc(),
        "forecast_mode": "absolute_ts",
        "start_ts": real_rows[0]["ts"].isoformat(),
        "end_ts": real_rows[-1]["ts"].isoformat(),
        "forecast": forecast_abs,
    }
    mongo.db.simulations.insert_one(doc)
    doc["_id"] = str(doc["_id"])
    return _json_ok(**doc)

# ---------------- Importadores CSV ----------------
#   - sleep: CSV diario → sleep_raw
#   - stress (CEDA): CSV por minutos o diario → agrega por día → stress_raw

@api.post("/import/sleep/csv")
@requires_auth
def import_sleep_csv_all_features():
    if "file" not in request.files:
        return _json_err("Falta 'file'", 400)
    f = request.files["file"]
    if not f or not f.filename:
        return _json_err("Archivo vacío", 400)

    try:
        raw = f.read().decode("utf-8-sig", errors="ignore")
    except Exception:
        return _json_err("No se pudo leer el CSV (encoding)", 400)
    if not raw.strip():
        return _json_err("CSV vacío", 400)

    sio = io.StringIO(raw)
    try:
        reader = csv.DictReader(sio)
        headers = [h for h in (reader.fieldnames or [])]
    except Exception:
        return _json_err("No se pudo analizar cabeceras", 400)

    # Columna de fecha
    date_col = None
    lower = [h.lower().strip() for h in headers]
    for cand in ("date", "timestamp", "fecha"):
        if cand in lower:
            date_col = headers[lower.index(cand)]
            break
    if not date_col:
        return _json_err("CSV: falta columna de fecha (Date / Timestamp / Fecha)", 400)

    sub = g.current_user.get("sub")
    now = _now_utc()

    ops: List[UpdateOne] = []
    total = errors = 0
    kept_columns = [h for h in headers if h != date_col]

    for row in reader:
        total += 1
        ts_str = (row.get(date_col) or "").strip()
        if not ts_str:
            errors += 1
            continue
        ts = _parse_any_datetime(ts_str)
        if not ts:
            errors += 1
            continue

        features: Dict[str, str] = {}
        for k in headers:
            if k == date_col:
                continue
            v = row.get(k)
            if v is None:
                continue
            vv = str(v).strip()
            if vv == "":
                continue
            k_norm = " ".join(str(k).split()).strip()
            features[k_norm] = vv

        filt = {"sub": sub, "ts_str": ts_str}
        doc = {"$set": {
            "sub": sub,
            "ts_str": ts_str,
            "ts": ts,
            "source": "csv",
            "features": features,
            "ingested_at": now,
        }}
        ops.append(UpdateOne(filt, doc, upsert=True))

    if not ops:
        return _json_err("No hay filas válidas", 400)

    try:
        res = mongo.db.sleep_raw.bulk_write(ops, ordered=False)
        inserted = len(res.upserted_ids) if res.upserted_ids else 0
        updated = res.modified_count or 0
    except Exception as e:
        return _json_err(f"Error en escritura: {e}", 500)

    return _json_ok(summary={"inserted": inserted, "updated": updated, "errors": errors, "total": total, "date_column": date_col, "kept_columns": kept_columns})

@api.post("/import/stress/csv")
@requires_auth
def import_stress_csv_ceda_aggregate_daily():
    """
    Importa CSV de CEDA (estrés):
      - Soporta datos por minuto o por día (detecta timestamp/fecha).
      - Agrega por día calculando la media de columnas numéricas.
      - Guarda 1 documento por día en 'stress_raw' con ts=00:00 UTC y features=medias.
    """
    if "file" not in request.files:
        return _json_err("Falta 'file'", 400)
    f = request.files["file"]
    if not f or not f.filename:
        return _json_err("Archivo vacío", 400)

    try:
        raw = f.read().decode("utf-8-sig", errors="ignore")
    except Exception:
        return _json_err("No se pudo leer el CSV (encoding)", 400)
    if not raw.strip():
        return _json_err("CSV vacío", 400)

    sio = io.StringIO(raw)
    try:
        reader = csv.DictReader(sio)
        headers = [h for h in (reader.fieldnames or [])]
    except Exception:
        return _json_err("No se pudo analizar cabeceras", 400)

    # Localizar columna de tiempo (minutos o fecha)
    date_col = None
    lower = [h.lower().strip() for h in headers]
    for cand in ("time", "timestamp", "datetime", "date", "fecha"):
        if cand in lower:
            date_col = headers[lower.index(cand)]
            break
    if not date_col:
        return _json_err("CSV: falta columna temporal (time/timestamp/datetime/date/fecha)", 400)

    sub = g.current_user.get("sub")
    now = _now_utc()

    # Agregadores por día (sumas / conteos numéricos)
    def _to_float(s):
        try:
            return float(str(s).replace(",", "."))
        except Exception:
            return None

    agg: Dict[datetime, Dict[str, Any]] = {}
    total_rows = errors = 0
    numeric_columns_seen = set([h for h in headers if h != date_col])

    for row in reader:
        total_rows += 1
        ts_str = (row.get(date_col) or "").strip()
        if not ts_str:
            errors += 1
            continue
        ts = _parse_any_datetime(ts_str)
        if not ts:
            errors += 1
            continue

        day = datetime(ts.year, ts.month, ts.day)  # 00:00 UTC
        if day not in agg:
            agg[day] = {"sums": {}, "counts": {}, "samples": 0}
        agg[day]["samples"] += 1

        for k in headers:
            if k == date_col:
                continue
            v = row.get(k)
            if v is None or str(v).strip() == "":
                continue
            fv = _to_float(v)
            if fv is None:
                # si no es numérico, no entra en media (queda fuera)
                continue
            agg[day]["sums"][k] = agg[day]["sums"].get(k, 0.0) + fv
            agg[day]["counts"][k] = agg[day]["counts"].get(k, 0) + 1

    # Construir medias por día y escribir en stress_raw
    days_written = 0
    kept_columns: List[str] = []

    for day, st in agg.items():
        features_avg: Dict[str, float] = {}
        for k, s in st["sums"].items():
            c = st["counts"].get(k, 0)
            if c > 0:
                k_norm = " ".join(str(k).split()).strip()
                features_avg[k_norm] = round(s / c, 6)
                if k_norm not in kept_columns:
                    kept_columns.append(k_norm)

        try:
            mongo.db.stress_raw.update_one(
                {"sub": sub, "ts": day},
                {"$set": {
                    "sub": sub,
                    "ts": day,
                    "ts_str": day.isoformat(),
                    "features": features_avg,
                    "n_samples": int(st["samples"]),
                    "source": "ceda_csv_daily_mean",
                    "ingested_at": now
                }},
                upsert=True
            )
            days_written += 1
        except Exception as e:
            current_app.logger.warning(f"Error escribiendo agregado diario estrés (CEDA) {day}: {e}")

    try:
        current_app.logger.info("[STRESS_IMPORT_CEDA] sub=%s rows=%s days=%s errors=%s kept=%s",
                                sub, total_rows, days_written, errors, ",".join(sorted(kept_columns)))
    except Exception:
        pass

    if days_written == 0:
        return _json_err("No se pudo generar ningún agregado diario", 400)

    return _json_ok(summary={
        "total_rows": total_rows,
        "days_aggregated": days_written,
        "errors": errors,
        "kept_columns": kept_columns
    })

# ---------------- IA scoring (sleep / stress) ----------------

def _sleep_prompt_from_features(features: Dict[str, Any]) -> str:
    return (
        "Eres un asistente médico. Evalúa la calidad del sueño con los datos proporcionados.\n"
        "IMPORTANTE: Devuelve ÚNICAMENTE JSON (sin Markdown, sin explicaciones, sin ```), con esta forma exacta:\n"
        '{ "score": 3, "advice": "texto breve con razones y recomendaciones" }\n'
        "Escala: 1=muy pobre · 3=aceptable · 5=excelente.\n"
        "Datos:\n" + json.dumps(features, ensure_ascii=False)
    )

def _stress_prompt_from_features(features: Dict[str, Any]) -> str:
    return (
        "Eres un asistente de bienestar. Evalúa el nivel de estrés con los datos diarios agregados (medias) proporcionados.\n"
        "Devuelve ÚNICAMENTE JSON (sin Markdown ni ```) con esta forma exacta:\n"
        '{ "score": 3, "advice": "texto breve con razones y recomendaciones" }\n'
        "Escala: 1=muy alto (peor) · 3=medio · 5=bajo (mejor).\n"
        "Datos:\n" + json.dumps(features, ensure_ascii=False)
    )

@api.post("/ai/score/sleep/from_csv")
@requires_auth
def ai_score_sleep_from_csv():
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    if "ts_str" in body:
        doc = mongo.db.sleep_raw.find_one({"sub": sub, "ts_str": body["ts_str"]})
        if not doc:
            return _json_err("No existe un registro con ese ts_str", 404)
    elif "ts" in body:
        dt = _parse_any_datetime(body["ts"])
        if not dt:
            return _json_err("ts inválido", 400)
        start = datetime(dt.year, dt.month, dt.day)
        end = start + timedelta(days=1) - timedelta(microseconds=1000)
        doc = mongo.db.sleep_raw.find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}})
        if not doc:
            return _json_err("No hay datos de ese día", 404)
    else:
        doc = mongo.db.sleep_raw.find_one({"sub": sub}, sort=[("ts", -1)])
        if not doc:
            return _json_err("No hay datos importados aún", 404)

    features = doc.get("features") or {}
    prompt = _sleep_prompt_from_features(features)

    score, advice = 3, "Revisa tus hábitos de sueño."
    try:
        out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.8, top_p=0.9)
        sc = int(out.get("score"))
        adv = out.get("advice", "")
        if 1 <= sc <= 5:
            score, advice = sc, adv
        else:
            raise ValueError("score fuera de rango")
    except Exception as e:
        current_app.logger.warning(f"LLM error (sleep fila única): {e}")

    mongo.db.measurements.update_one(
        {"sub": sub, "type": "sleep", "ts": doc["ts"]},
        {"$set": {
            "sub": sub,
            "type": "sleep",
            "ts": doc["ts"],
            "value": int(score),
            "source": "ai_from_csv",
            "advice": advice,
            "scored_at": _now_utc(),
        }},
        upsert=True
    )

    try:
        used_keys = list((doc.get("features") or {}).keys())
        current_app.logger.info(
            "[AI_SCORE] metric=sleep sub=%s ts=%s ts_str=%s score=%s used_keys=%s advice=%s",
            sub, doc["ts"].isoformat() if doc.get("ts") else None, doc.get("ts_str"),
            int(score), ",".join(used_keys), (advice or "")[:200]
        )
    except Exception:
        pass

    return _json_ok(ts_str=doc.get("ts_str"), score=int(score), advice=advice, used_keys=list(features.keys()))

@api.post("/ai/score/sleep/from_csv/bulk_llm")
@requires_auth
def ai_score_sleep_from_csv_bulk_llm():
    if not os.environ.get("LLM_API_KEY"):
        return _json_err("Falta LLM_API_KEY en el servidor para usar la IA", 400)

    sub = g.current_user.get("sub")
    cur = mongo.db.sleep_raw.find({"sub": sub}, projection={"_id": 0, "ts": 1, "features": 1, "ts_str": 1}).sort("ts", 1)

    total = written = llm_errors = 0

    for doc in cur:
        total += 1
        features = doc.get("features") or {}
        prompt = _sleep_prompt_from_features(features)

        score, advice = 3, "Revisa tus hábitos de sueño."
        try:
            out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.8, top_p=0.9)
            sc = int(out.get("score")); adv = out.get("advice", "")
            if 1 <= sc <= 5: score, advice = sc, adv
            else: raise ValueError(f"score fuera de rango: {sc}")
        except Exception as e:
            llm_errors += 1
            current_app.logger.warning(f"LLM bulk row error (sleep): {e}")

        try:
            used_keys = list((features or {}).keys())
            current_app.logger.info(
                "[AI_SCORE_BULK] metric=sleep sub=%s ts=%s ts_str=%s score=%s used_keys=%s advice=%s",
                sub, doc["ts"].isoformat() if doc.get("ts") else None, doc.get("ts_str"),
                int(score), ",".join(used_keys), (advice or "")[:200]
            )
        except Exception:
            pass

        res = mongo.db.measurements.update_one(
            {"sub": sub, "type": "sleep", "ts": doc["ts"]},
            {"$set": {
                "sub": sub, "type": "sleep", "ts": doc["ts"], "value": int(score),
                "source": "ai_from_csv_bulk_llm", "advice": advice, "scored_at": _now_utc(),
            }},
            upsert=True
        )
        if res.upserted_id or res.modified_count:
            written += 1

    return _json_ok(summary={"total_rows": total, "written_measurements": written, "llm_errors": llm_errors})

@api.post("/ai/score/stress/from_csv")
@requires_auth
def ai_score_stress_from_csv():
    """
    Escoge el registro de stress_raw (CEDA agregado) por ts_str, por fecha (ts) o último;
    puntúa con IA y escribe en measurements(type=stress).
    """
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    if "ts_str" in body:
        doc = mongo.db.stress_raw.find_one({"sub": sub, "ts_str": body["ts_str"]})
        if not doc:
            return _json_err("No existe un registro con ese ts_str", 404)
    elif "ts" in body:
        dt = _parse_any_datetime(body["ts"])
        if not dt:
            return _json_err("ts inválido", 400)
        start = datetime(dt.year, dt.month, dt.day)
        end = start + timedelta(days=1) - timedelta(microseconds=1000)
        doc = mongo.db.stress_raw.find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}})
        if not doc:
            return _json_err("No hay datos de ese día", 404)
    else:
        doc = mongo.db.stress_raw.find_one({"sub": sub}, sort=[("ts", -1)])
        if not doc:
            return _json_err("No hay datos importados aún", 404)

    features = doc.get("features") or {}
    prompt = _stress_prompt_from_features(features)

    score, advice = 3, "Revisa hábitos para reducir el estrés."
    try:
        out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.8, top_p=0.9)
        sc = int(out.get("score")); adv = out.get("advice", "")
        if 1 <= sc <= 5: score, advice = sc, adv
        else: raise ValueError("score fuera de rango")
    except Exception as e:
        current_app.logger.warning(f"LLM error (stress fila única): {e}")

    mongo.db.measurements.update_one(
        {"sub": sub, "type": "stress", "ts": doc["ts"]},
        {"$set": {
            "sub": sub, "type": "stress", "ts": doc["ts"], "value": int(score),
            "source": "ai_from_csv", "advice": advice, "scored_at": _now_utc(),
        }},
        upsert=True
    )

    try:
        used_keys = list((doc.get("features") or {}).keys())
        current_app.logger.info(
            "[AI_SCORE] metric=stress sub=%s ts=%s ts_str=%s score=%s used_keys=%s advice=%s",
            sub, doc["ts"].isoformat() if doc.get("ts") else None, doc.get("ts_str"),
            int(score), ",".join(used_keys), (advice or "")[:200]
        )
    except Exception:
        pass

    return _json_ok(ts_str=doc.get("ts_str"), score=int(score), advice=advice, used_keys=list(features.keys()))

@api.post("/ai/score/stress/from_csv/bulk_llm")
@requires_auth
def ai_score_stress_from_csv_bulk_llm():
    if not os.environ.get("LLM_API_KEY"):
        return _json_err("Falta LLM_API_KEY en el servidor para usar la IA", 400)

    sub = g.current_user.get("sub")
    cur = mongo.db.stress_raw.find({"sub": sub}, projection={"_id": 0, "ts": 1, "features": 1, "ts_str": 1}).sort("ts", 1)

    total = written = llm_errors = 0

    for doc in cur:
        total += 1
        features = doc.get("features") or {}
        prompt = _stress_prompt_from_features(features)

        score, advice = 3, "Revisa hábitos para reducir el estrés."
        try:
            out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.8, top_p=0.9)
            sc = int(out.get("score")); adv = out.get("advice", "")
            if 1 <= sc <= 5: score, advice = sc, adv
            else: raise ValueError(f"score fuera de rango: {sc}")
        except Exception as e:
            llm_errors += 1
            current_app.logger.warning(f"LLM bulk row error (stress): {e}")

        try:
            used_keys = list((features or {}).keys())
            current_app.logger.info(
                "[AI_SCORE_BULK] metric=stress sub=%s ts=%s ts_str=%s score=%s used_keys=%s advice=%s",
                sub, doc["ts"].isoformat() if doc.get("ts") else None, doc.get("ts_str"),
                int(score), ",".join(used_keys), (advice or "")[:200]
            )
        except Exception:
            pass

        res = mongo.db.measurements.update_one(
            {"sub": sub, "type": "stress", "ts": doc["ts"]},
            {"$set": {
                "sub": sub, "type": "stress", "ts": doc["ts"], "value": int(score),
                "source": "ai_from_csv_bulk_llm", "advice": advice, "scored_at": _now_utc(),
            }},
            upsert=True
        )
        if res.upserted_id or res.modified_count:
            written += 1

    return _json_ok(summary={"total_rows": total, "written_measurements": written, "llm_errors": llm_errors})
