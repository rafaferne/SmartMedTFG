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
    
# ---------- Helpers específicos de actividad (UserExercise) ----------

def _to_float(s):
    try:
        return float(str(s).replace(",", "."))
    except Exception:
        return None

def _secs_between(start_str: str, end_str: str) -> Optional[float]:
    t1 = _parse_any_datetime(start_str)
    t2 = _parse_any_datetime(end_str)
    if not t1 or not t2:
        return None
    return max(0.0, (t2 - t1).total_seconds())

def _is_userexercise_headers(headers_lower: List[str]) -> bool:
    # Heurística: presencia de campos típicos del export "UserExercise"
    keys = set(headers_lower)
    must_any = [
        "exerciseid", "starttime","exercise_end" "activityname",
        "steps", "calories", "distance", "avghr", "averageheartrate",
        "maxhr", "maxheartrate",
        "minutesactive", "active_minutes", "mvpa_minutes",
        "metminutes", "met_min", "metmins",
        "duration", "durationsec", "duration_ms"
    ]
    # Con 2 o más claves típicas ya consideramos que es UserExercise
    hits = sum(1 for k in must_any if k in keys)
    return hits >= 2


def _norm_key(k: str) -> str:
    return " ".join(str(k).split()).strip()

def _aggregate_userexercise_daily(reader: csv.DictReader) -> Dict[datetime, Dict[str, Any]]:
    """
    Agrega un CSV de UserExercise a nivel diario.
    Estrategia:
      - sumas: steps, calories, distance (km), met_minutes, minutes_active, duration_min
      - medias: avg_hr, max_hr si llegan por fila
    """
    headers = [h for h in (reader.fieldnames or [])]
    lower = [h.lower().strip() for h in headers]

    # Localiza columnas típicas (tolerante a nombres)
    def pick(*cands):
        for c in cands:
            if c in lower:
                return headers[lower.index(c)]
        return None

    col_start = pick("starttime", "start_time", "inicio", "datetime", "time", "date")
    col_end   = pick("endtime", "end_time", "fin", "exercise_end")
    col_steps = pick("steps", "stepcount", "total_steps")
    col_cal   = pick("calories", "energy", "kcal", "energykcal")
    col_dist  = pick("distance", "distance_km", "distancia", "distance_m")
    col_avgHR = pick("avghr", "averageheartrate", "avg_hr", "hr_avg")
    col_maxHR = pick("maxhr", "maxheartrate", "hr_max")
    col_met   = pick("metminutes", "met_min", "metmins")
    col_actm  = pick("minutesactive", "active_minutes", "mvpa_minutes", "mins_active")
    col_dur   = pick("duration", "durationsec", "duration_ms")  # si no, calculamos con start/end

    agg: Dict[datetime, Dict[str, Any]] = {}
    def day_bucket(ts: datetime) -> datetime:
        return datetime(ts.year, ts.month, ts.day)

    for row in reader:
        # Fecha base: start_time si existe; si no, intenta cualquier timestamp
        ts0 = None
        if col_start and row.get(col_start):
            ts0 = _parse_any_datetime(row[col_start])
        if not ts0:
            # fallback: usa end_time o cualquier campo fecha
            any_ts = row.get(col_end) or row.get(col_start) or row.get(col_dur) or ""
            ts0 = _parse_any_datetime(any_ts) or _now_utc()

        d = day_bucket(ts0)
        if d not in agg:
            agg[d] = {
                "sums": {
                    "steps": 0.0, "calories_kcal": 0.0, "distance_km": 0.0,
                    "met_minutes": 0.0, "active_minutes": 0.0, "duration_min": 0.0
                },
                "hr_sum": 0.0, "hr_cnt": 0,
                "hrmax_sum": 0.0, "hrmax_cnt": 0,
                "samples": 0
            }
        st = agg[d]
        st["samples"] += 1

        # Sumas directas
        if col_steps:
            v = _to_float(row.get(col_steps))
            if v is not None: st["sums"]["steps"] += v

        if col_cal:
            v = _to_float(row.get(col_cal))
            if v is not None: st["sums"]["calories_kcal"] += v

        if col_dist:
            v = _to_float(row.get(col_dist))
            if v is not None:
                # Si parece metros, pásalo a km (umbral heurístico)
                st["sums"]["distance_km"] += v / 1000.0 if v > 100 else v

        if col_met:
            v = _to_float(row.get(col_met))
            if v is not None: st["sums"]["met_minutes"] += v

        if col_actm:
            v = _to_float(row.get(col_actm))
            if v is not None: st["sums"]["active_minutes"] += v

        # Duración: usa duración informada; si no, calcula con start/end
        dur_min = None
        if col_dur and row.get(col_dur):
            v = _to_float(row.get(col_dur))
            if v is not None:
                # si parece en ms o s, normaliza a minutos
                if v > 10000:     # ms
                    dur_min = v / 60000.0
                elif v > 300:     # s
                    dur_min = v / 60.0
                else:             # ya en minutos
                    dur_min = v
        if dur_min is None and col_start and col_end and row.get(col_start) and row.get(col_end):
            secs = _secs_between(row.get(col_start), row.get(col_end))
            if secs is not None:
                dur_min = secs / 60.0
        if dur_min is not None:
            st["sums"]["duration_min"] += max(0.0, dur_min)

        # Medias de FC
        if col_avgHR:
            v = _to_float(row.get(col_avgHR))
            if v is not None:
                st["hr_sum"] += v
                st["hr_cnt"] += 1

        if col_maxHR:
            v = _to_float(row.get(col_maxHR))
            if v is not None:
                st["hrmax_sum"] += v
                st["hrmax_cnt"] += 1

    # Construye features finales por día
    out: Dict[datetime, Dict[str, Any]] = {}
    for d, st in agg.items():
        feats = dict(st["sums"])
        if st["hr_cnt"] > 0:
            feats["avg_hr"] = round(st["hr_sum"] / st["hr_cnt"], 3)
        if st["hrmax_cnt"] > 0:
            feats["max_hr"] = round(st["hrmax_sum"] / st["hrmax_cnt"], 3)
        feats["samples"] = int(st["samples"])
        out[d] = feats
    return out


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

    # Devuelve features del RAW correspondiente (añadimos activity_raw)
    features = None
    raw = None
    if mtype == "sleep":
        raw = mongo.db.sleep_raw.find_one({"sub": sub, "ts": ts}, projection={"_id": 0, "features": 1})
    elif mtype == "stress":
        raw = mongo.db.stress_raw.find_one({"sub": sub, "ts": ts}, projection={"_id": 0, "features": 1})
    elif mtype == "activity":
        raw = mongo.db.activity_raw.find_one({"sub": sub, "ts": ts}, projection={"_id": 0, "features": 1})
    if raw and isinstance(raw.get("features"), dict):
        features = raw["features"]

    day_start = datetime(ts.year, ts.month, ts.day)
    day_end = day_start + timedelta(days=1) - timedelta(microseconds=1000)
    spo2 = mongo.db.spo2_raw.find_one({"sub": sub, "ts": {"$gte": day_start, "$lte": day_end}},
                                      projection={"_id": 0, "features": 1})
    if spo2 and isinstance(spo2.get("features"), dict):
        # no pisar claves existentes
        for k, v in spo2["features"].items():
            features.setdefault(k, v)

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
    elif mtype == "activity":
        raw = mongo.db.activity_raw.find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}}, projection={"_id": 0, "features": 1})
    if raw and isinstance(raw.get("features"), dict):
        features = raw["features"]
    else:
        features = {}

    spo2 = mongo.db.spo2_raw.find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}},
                                      projection={"_id": 0, "features": 1})
    if spo2 and isinstance(spo2.get("features"), dict):
        for k, v in spo2["features"].items():
            features.setdefault(k, v)

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
    Gemelo digital (sleep/stress/activity):
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

    # Features por ts desde RAW (añadimos activity_raw)
    features_by_ts: Dict[str, Dict[str, Any]] = {}
    if metric == "sleep":
        raw_col = mongo.db.sleep_raw
    elif metric == "stress":
        raw_col = mongo.db.stress_raw
    elif metric == "activity":
        raw_col = mongo.db.activity_raw
    else:
        raw_col = mongo.db.stress_raw  # fallback no intrusivo

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
#   - activity: CSV por minutos o diario → agrega por día → activity_raw

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
    Importa CSV de CEDA (estrés): minuto o día → medias diarias → stress_raw
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

    def _to_float(s):
        try:
            return float(str(s).replace(",", "."))
        except Exception:
            return None

    agg: Dict[datetime, Dict[str, Any]] = {}
    total_rows = errors = 0
    kept_columns: List[str] = []

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
                continue
            k_norm = " ".join(str(k).split()).strip()
            agg[day]["sums"][k_norm] = agg[day]["sums"].get(k_norm, 0.0) + fv
            agg[day]["counts"][k_norm] = agg[day]["counts"].get(k_norm, 0) + 1
            if k_norm not in kept_columns:
                kept_columns.append(k_norm)

    days_written = 0
    for day, st in agg.items():
        features_avg: Dict[str, float] = {}
        for k, s in st["sums"].items():
            c = st["counts"].get(k, 0)
            if c > 0:
                features_avg[k] = round(s / c, 6)

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

@api.post("/import/activity/csv")
@requires_auth
def import_activity_csv():
    """
    Importa CSV de Actividad:
      - Si detecta formato 'UserExercise' → agrega por día con reglas específicas
      - En otro caso → usa el agregador genérico (minutos/día → medias diarias)
    Si el CSV no trae time/timestamp/datetime/date/fecha, se usará el FINAL DEL EJERCICIO:
      endtime / end_time / fin
    Guarda en activity_raw (ts = inicio de día, UTC).
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

    # Leemos cabeceras una vez
    try:
        sniff = csv.DictReader(io.StringIO(raw))
        headers = [h for h in (sniff.fieldnames or [])]
        lower = [h.lower().strip() for h in headers]
    except Exception:
        return _json_err("No se pudo analizar cabeceras", 400)

    sub = g.current_user.get("sub")
    now = _now_utc()

    # ¿Es UserExercise?
    is_userexercise = _is_userexercise_headers(lower)

    days_written = 0
    kept_columns: List[str] = []
    errors = 0
    total_rows = 0

    if is_userexercise:
        # Agregador específico
        reader = csv.DictReader(io.StringIO(raw))
        agg = _aggregate_userexercise_daily(reader)
        total_rows = sum(v.get("samples", 0) for v in agg.values())
        try:
            for day, feats in agg.items():
                kept_columns = sorted(list({*kept_columns, *feats.keys()}))
                mongo.db.activity_raw.update_one(
                    {"sub": sub, "ts": day},
                    {"$set": {
                        "sub": sub,
                        "ts": day,
                        "ts_str": day.isoformat(),
                        "features": feats,
                        "n_samples": int(feats.get("samples", 0)),
                        "source": "activity_userexercise_daily",
                        "ingested_at": now
                    }},
                    upsert=True
                )
                days_written += 1
        except Exception as e:
            return _json_err(f"Error escribiendo agregado diario actividad (UserExercise): {e}", 500)

    else:
        # Agregador genérico con fallback a END TIME si falta fecha clásica
        try:
            reader = csv.DictReader(io.StringIO(raw))

            # 1) intenta time/timestamp/datetime/date/fecha
            date_col = None
            for cand in ("time", "timestamp", "datetime", "date", "fecha"):
                if cand in lower:
                    date_col = headers[lower.index(cand)]
                    break

            # 2) si no, usa endtime/end_time/fin como columna temporal
            end_col = None
            if not date_col:
                for cand in ("endtime", "end_time", "fin", "exercise_end"):
                    if cand in lower:
                        end_col = headers[lower.index(cand)]
                        break

            if not date_col and not end_col:
                return _json_err("CSV: falta columna temporal (time/timestamp/datetime/date/fecha) y tampoco hay endtime/end_time/fin", 400)

            def pick_ts_str(row):
                # Prioridad: date_col clásico; si no, el final del ejercicio
                return (row.get(date_col) if date_col else None) or (row.get(end_col) if end_col else None) or ""

            agg: Dict[datetime, Dict[str, Any]] = {}

            for row in reader:
                total_rows += 1
                ts_str = (pick_ts_str(row) or "").strip()
                if not ts_str:
                    errors += 1
                    continue
                ts = _parse_any_datetime(ts_str)
                if not ts:
                    errors += 1
                    continue

                day = datetime(ts.year, ts.month, ts.day)
                if day not in agg:
                    agg[day] = {"sums": {}, "counts": {}, "samples": 0}
                agg[day]["samples"] += 1

                for k in headers:
                    # Evita sumar la columna temporal sea cual sea
                    if (date_col and k == date_col) or (end_col and k == end_col):
                        continue
                    v = row.get(k)
                    if v is None or str(v).strip() == "":
                        continue
                    fv = _to_float(v)
                    if fv is None:
                        continue
                    k_norm = _norm_key(k)
                    agg[day]["sums"][k_norm] = agg[day]["sums"].get(k_norm, 0.0) + fv
                    agg[day]["counts"][k_norm] = agg[day]["counts"].get(k_norm, 0) + 1
                    if k_norm not in kept_columns:
                        kept_columns.append(k_norm)

            for day, st in agg.items():
                features_avg: Dict[str, float] = {}
                for k, s in st["sums"].items():
                    c = st["counts"].get(k, 0)
                    if c > 0:
                        features_avg[k] = round(s / c, 6)

                mongo.db.activity_raw.update_one(
                    {"sub": sub, "ts": day},
                    {"$set": {
                        "sub": sub,
                        "ts": day,
                        "ts_str": day.isoformat(),
                        "features": features_avg,
                        "n_samples": int(st["samples"]),
                        "source": "activity_csv_daily_mean",
                        "ingested_at": now
                    }},
                    upsert=True
                )
                days_written += 1

        except Exception as e:
            return _json_err(f"Error en importación genérica de actividad: {e}", 500)

    try:
        current_app.logger.info(
            "[ACTIVITY_IMPORT] sub=%s userexercise=%s days=%s rows=%s kept=%s",
            sub, is_userexercise, days_written, total_rows, len(kept_columns)
        )
    except Exception:
        pass

    if days_written == 0:
        return _json_err("No se pudo generar ningún agregado diario", 400)

    return _json_ok(summary={
        "days_aggregated": days_written,
        "total_rows": total_rows,
        "errors": errors,
        "kept_columns": kept_columns
    })


@api.post("/import/spo2/csv")
@requires_auth
def import_spo2_csv_daily_mean():
    """
    Importa uno o varios CSV de SpO₂ (oxígeno en sangre) por minuto → media diaria.
    - Acepta: "files" (lista) o "file" (único) para compatibilidad.
    - Agrega todos los CSV en memoria y escribe una única media por día.
    Guarda en 'spo2_raw' con features: { 'spo2_avg': <porcentaje> } y n_samples.
    """
    # 1) Recoger archivos (múltiple o único)
    files = request.files.getlist("files")
    if not files:
        f = request.files.get("file")
        if f:
            files = [f]
    if not files:
        return _json_err("Falta 'files' o 'file'", 400)

    def _to_f(s):
        try:
            return float(str(s).replace(",", "."))
        except Exception:
            return None

    sub = g.current_user.get("sub")
    now = _now_utc()

    # Acumuladores globales (agregan todos los ficheros)
    agg = {}  # day -> {"sum": x, "cnt": n}
    total_rows = 0
    errors = 0
    files_count = 0

    for f in files:
        if not f or not f.filename:
            continue
        try:
            raw = f.read().decode("utf-8-sig", errors="ignore")
        except Exception:
            errors += 1
            continue
        if not raw.strip():
            errors += 1
            continue

        try:
            reader = csv.DictReader(io.StringIO(raw))
            headers = [h for h in (reader.fieldnames or [])]
            lower = [h.lower().strip() for h in headers]
        except Exception:
            errors += 1
            continue

        # Columna temporal
        date_col = None
        for cand in ("time", "timestamp", "datetime", "date", "fecha"):
            if cand in lower:
                date_col = headers[lower.index(cand)]
                break
        if not date_col:
            errors += 1
            continue

        # Columna valor SpO2
        value_col = None
        for i, name in enumerate(lower):
            if any(s in name for s in ("spo2", "oxigen", "oxígeno", "oxygen", "saturation")):
                value_col = headers[i]
                break
        if not value_col and len(headers) >= 2:
            # fallback: primera no temporal
            for h in headers:
                if h != date_col:
                    value_col = h
                    break
        if not value_col:
            errors += 1
            continue

        files_count += 1

        # Recorrido del CSV
        for row in reader:
            total_rows += 1
            ts_str = (row.get(date_col) or "").strip()
            if not ts_str:
                errors += 1; continue
            ts = _parse_any_datetime(ts_str)
            if not ts:
                errors += 1; continue

            v = _to_f(row.get(value_col))
            if v is None:
                errors += 1; continue

            day = datetime(ts.year, ts.month, ts.day)
            st = agg.setdefault(day, {"sum": 0.0, "cnt": 0})
            st["sum"] += v
            st["cnt"] += 1

    # Escritura por día
    days_written = 0
    for day, st in agg.items():
        if st["cnt"] <= 0:
            continue
        avg = round(st["sum"] / st["cnt"], 3)
        mongo.db.spo2_raw.update_one(
            {"sub": sub, "ts": day},
            {"$set": {
                "sub": sub,
                "ts": day,
                "ts_str": day.isoformat(),
                "features": {"spo2_avg": avg},
                "n_samples": int(st["cnt"]),
                "source": "spo2_csv_daily_mean",
                "ingested_at": now
            }},
            upsert=True
        )
        days_written += 1

    try:
        current_app.logger.info(
            "[SPO2_IMPORT] sub=%s files=%s days=%s rows=%s errors=%s",
            sub, files_count, days_written, total_rows, errors
        )
    except Exception:
        pass

    if days_written == 0:
        return _json_err("No se pudo generar ningún agregado diario", 400)

    return _json_ok(summary={
        "files": files_count,
        "days_aggregated": days_written,
        "total_rows": total_rows,
        "errors": errors
    })


# ---------------- IA scoring (sleep / stress / activity) ----------------

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

def _activity_prompt_from_features(features: Dict[str, Any]) -> str:
    """
    Considera campos comunes de UserExercise si aparecen:
      - steps, active_minutes (o minutes_active), met_minutes, duration_min
      - calories_kcal, distance_km
      - avg_hr, max_hr
    """
    guide = (
        "Eres un coach de salud. Evalúa la ACTIVIDAD FÍSICA diaria con los datos agregados (medias/sumas por día).\n"
        "Devuelve ÚNICAMENTE JSON con esta forma exacta (sin Markdown ni ```):\n"
        '{ "score": 3, "advice": "recomendaciones breves y concretas" }\n'
        "Escala: 1=muy baja/sedentaria · 3=moderada · 5=óptima.\n\n"
        "Pautas:\n"
        "- Ten en cuenta: pasos totales, minutos activos/moderados-vigorosos, MET-minutes, duración total, calorías, distancia.\n"
        "- Usa la FC (avg_hr / max_hr) como contexto de intensidad si está disponible.\n"
        "- Si los datos son muy pobres o nulos, puntúa bajo y recomienda objetivos mínimos progresivos.\n"
        "- Si el tipo de ejercicio que se hace es 'Outdoor Walk' obvia todas las columnas cuyos datos son 0 o nulos.\n"
    )
    return guide + "\nDatos:\n" + json.dumps(features, ensure_ascii=False)


def _score_one_generic(raw_name: str, metric_type: str, prompt_fn):
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    if "ts_str" in body:
        doc = mongo.db[raw_name].find_one({"sub": sub, "ts_str": body["ts_str"]})
        if not doc:
            return _json_err("No existe un registro con ese ts_str", 404)
    elif "ts" in body:
        dt = _parse_any_datetime(body["ts"])
        if not dt:
            return _json_err("ts inválido", 400)
        start = datetime(dt.year, dt.month, dt.day)
        end = start + timedelta(days=1) - timedelta(microseconds=1000)
        doc = mongo.db[raw_name].find_one({"sub": sub, "ts": {"$gte": start, "$lte": end}})
        if not doc:
            return _json_err("No hay datos de ese día", 404)
    else:
        doc = mongo.db[raw_name].find_one({"sub": sub}, sort=[("ts", -1)])
        if not doc:
            return _json_err("No hay datos importados aún", 404)

    features = doc.get("features") or {}
    prompt = prompt_fn(features)

    score, advice = 3, "Revisa tus hábitos."
    try:
        out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.8, top_p=0.9)
        sc = int(out.get("score")); adv = out.get("advice", "")
        if 1 <= sc <= 5: score, advice = sc, adv
        else: raise ValueError("score fuera de rango")
    except Exception as e:
        current_app.logger.warning(f"LLM error ({metric_type} fila única): {e}")

    mongo.db.measurements.update_one(
        {"sub": sub, "type": metric_type, "ts": doc["ts"]},
        {"$set": {
            "sub": sub, "type": metric_type, "ts": doc["ts"], "value": int(score),
            "source": "ai_from_csv", "advice": advice, "scored_at": _now_utc(),
        }},
        upsert=True
    )

    try:
        used_keys = list((doc.get("features") or {}).keys())
        current_app.logger.info(
            "[AI_SCORE] metric=%s sub=%s ts=%s ts_str=%s score=%s used_keys=%s advice=%s",
            metric_type, sub, doc["ts"].isoformat() if doc.get("ts") else None, doc.get("ts_str"),
            int(score), ",".join(used_keys), (advice or "")[:200]
        )
    except Exception:
        pass

    return _json_ok(ts_str=doc.get("ts_str"), score=int(score), advice=advice, used_keys=list(features.keys()))

def _score_bulk_generic(raw_name: str, metric_type: str, prompt_fn):
    if not os.environ.get("LLM_API_KEY"):
        return _json_err("Falta LLM_API_KEY en el servidor para usar la IA", 400)

    sub = g.current_user.get("sub")
    cur = mongo.db[raw_name].find(
        {"sub": sub},
        projection={"_id": 0, "ts": 1, "features": 1, "ts_str": 1}
    ).sort("ts", 1)

    total = written = llm_errors = 0

    for doc in cur:
        total += 1
        features = doc.get("features") or {}
        prompt = prompt_fn(features)

        score, advice = 3, "Revisa tus hábitos."
        try:
            out = _gemini_generate_json(prompt, max_tokens=30000, temperature=0.8, top_p=0.9)
            sc = int(out.get("score")); adv = out.get("advice", "")
            if 1 <= sc <= 5: score, advice = sc, adv
            else: raise ValueError(f"score fuera de rango: {sc}")
        except Exception as e:
            llm_errors += 1
            current_app.logger.warning(f"LLM bulk row error ({metric_type}): {e}")

        try:
            used_keys = list((features or {}).keys())
            current_app.logger.info(
                "[AI_SCORE_BULK] metric=%s sub=%s ts=%s ts_str=%s score=%s used_keys=%s advice=%s",
                metric_type, sub, doc["ts"].isoformat() if doc.get("ts") else None, doc.get("ts_str"),
                int(score), ",".join(used_keys), (advice or "")[:200]
            )
        except Exception:
            pass

        res = mongo.db.measurements.update_one(
            {"sub": sub, "type": metric_type, "ts": doc["ts"]},
            {"$set": {
                "sub": sub, "type": metric_type, "ts": doc["ts"], "value": int(score),
                "source": f"ai_from_csv_bulk_llm", "advice": advice, "scored_at": _now_utc(),
            }},
            upsert=True
        )
        if res.upserted_id or res.modified_count:
            written += 1

    return _json_ok(summary={"total_rows": total, "written_measurements": written, "llm_errors": llm_errors})

@api.post("/ai/score/sleep/from_csv")
@requires_auth
def ai_score_sleep_from_csv():
    return _score_one_generic("sleep_raw", "sleep", _sleep_prompt_from_features)

@api.post("/ai/score/sleep/from_csv/bulk_llm")
@requires_auth
def ai_score_sleep_from_csv_bulk_llm():
    return _score_bulk_generic("sleep_raw", "sleep", _sleep_prompt_from_features)

@api.post("/ai/score/stress/from_csv")
@requires_auth
def ai_score_stress_from_csv():
    return _score_one_generic("stress_raw", "stress", _stress_prompt_from_features)

@api.post("/ai/score/stress/from_csv/bulk_llm")
@requires_auth
def ai_score_stress_from_csv_bulk_llm():
    return _score_bulk_generic("stress_raw", "stress", _stress_prompt_from_features)

@api.post("/ai/score/activity/from_csv")
@requires_auth
def ai_score_activity_from_csv():
    return _score_one_generic("activity_raw", "activity", _activity_prompt_from_features)

@api.post("/ai/score/activity/from_csv/bulk_llm")
@requires_auth
def ai_score_activity_from_csv_bulk_llm():
    return _score_bulk_generic("activity_raw", "activity", _activity_prompt_from_features)
