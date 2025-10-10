from flask import Blueprint, jsonify, request, g, current_app
from datetime import datetime, timedelta
from extensions import mongo
from auth import requires_auth, requires_permission, requires_any_permission
import os, requests, json, re
import hashlib, time, base64
from flask import current_app


# Simple cooldown (segundos) por usuario/tipo para no spamear al LLM
AI_COOLDOWN_SECONDS = int(os.getenv("AI_COOLDOWN_SECONDS", "8"))

def _cooldown_key(sub: str, mtype: str) -> dict:
    return {"sub": sub, "type": mtype}

def _check_and_touch_cooldown(sub: str, mtype: str):
    """
    Devuelve (ok, retry_after). Si ok=False, significa que el usuario está
    en cooldown y debe esperar retry_after segundos.
    """
    now = datetime.utcnow()
    doc = mongo.db.ai_calls.find_one(_cooldown_key(sub, mtype), {"_id": 0, "last": 1})
    if doc and doc.get("last"):
        elapsed = (now - doc["last"]).total_seconds()
        if elapsed < AI_COOLDOWN_SECONDS:
            return False, int(AI_COOLDOWN_SECONDS - elapsed + 0.5)
    # actualiza/crea marca de tiempo
    mongo.db.ai_calls.update_one(_cooldown_key(sub, mtype), {"$set": {"last": now}}, upsert=True)
    return True, 0

def _hash_payload(payload: dict) -> str:
    m = hashlib.sha256()
    m.update(json.dumps(payload or {}, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return m.hexdigest()

def _check_dedupe(sub: str, mtype: str, payload_hash: str, window_min=10):
    """
    Evita recalcular lo mismo: si hay una entrada idéntica en los últimos N minutos,
    devuelve (True, score) y podemos reusar la nota.
    """
    since = datetime.utcnow() - timedelta(minutes=window_min)
    doc = mongo.db.ai_cache.find_one(
        {"sub": sub, "type": mtype, "hash": payload_hash, "ts": {"$gte": since}},
        {"_id": 0, "score": 1}
    )
    if doc:
        return True, doc["score"]
    return False, None

def _store_dedupe(sub: str, mtype: str, payload_hash: str, score: int):
    mongo.db.ai_cache.update_one(
        {"sub": sub, "type": mtype, "hash": payload_hash},
        {"$set": {"sub": sub, "type": mtype, "hash": payload_hash, "score": score, "ts": datetime.utcnow()}},
        upsert=True
    )


api = Blueprint("api", __name__)

@api.get("/ping")
def ping():
    return jsonify(ok=True, msg="pong")

@api.get("/user")
@requires_auth
def user():
    # Simplemente prueba de endpoint protegido
    return jsonify(ok=True, msg="Acceso con token válido")

@api.get("/me")
@requires_auth
def me():
    sub = g.current_user.get("sub")
    doc = mongo.db.users.find_one({"sub": sub}, {"_id": 0})
    if not doc:
        return jsonify({"sub": sub, "profileComplete": False, "profile": {}})
    return jsonify(doc)

@api.post("/me/sync")
@requires_auth
def me_sync():
    """Upsert básico tras login para asegurar registro local."""
    payload = g.current_user or {}
    sub = payload.get("sub")
    if not sub:
        return jsonify(error="missing_sub"), 400

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or payload.get("email") or "").strip().lower() or None
    name  = (data.get("name")  or payload.get("name")  or "").strip()          or None
    picture = data.get("picture") or payload.get("picture") or None

    set_doc = {"sub": sub, "updated_at": datetime.utcnow()}
    if email:   set_doc["email"] = email
    if name:    set_doc["name"] = name
    if picture: set_doc["picture"] = picture

    mongo.db.users.update_one(
        {"sub": sub},
        {"$set": set_doc,
         "$setOnInsert": {"profile": {}, "profileComplete": False, "created_at": datetime.utcnow()}},
        upsert=True,
    )
    return jsonify(ok=True)


@api.put("/me/profile")
@requires_auth
def me_profile_update():
    sub = g.current_user.get("sub")
    if not sub:
        return jsonify(ok=False, error="missing_sub"), 401

    body = request.get_json(silent=True) or {}

    def bad(msg): 
        return jsonify(ok=False, error=msg), 400

    # Normaliza entradas
    birthdate = body.get("birthdate") or None
    sex       = body.get("sex") or None
    height_cm = body.get("height_cm")
    weight_kg = body.get("weight_kg")
    notes     = body.get("notes") or ""

    if birthdate:
        try:
            datetime.strptime(birthdate, "%Y-%m-%d")
        except (TypeError, ValueError):
            return bad("birthdate debe ser YYYY-MM-DD")

    allowed_sex = {"male", "female", "other", "prefer_not_say", None}
    if sex not in allowed_sex:
        return bad("sex inválido")

    def to_float_or_none(x):
        if x in (None, "", "null"):
            return None
        try:
            return float(x)
        except (TypeError, ValueError):
            return "invalid"

    height_cm = to_float_or_none(height_cm)
    weight_kg = to_float_or_none(weight_kg)
    if height_cm == "invalid": return bad("height_cm debe ser numérico")
    if weight_kg == "invalid": return bad("weight_kg debe ser numérico")

    if height_cm is not None and not (40 <= height_cm <= 300):
        return bad("height_cm fuera de rango (40-300)")
    if weight_kg is not None and not (1 <= weight_kg <= 600):
        return bad("weight_kg fuera de rango (1-600)")

    profile_update = {"notes": notes}
    if birthdate is not None: profile_update["birthdate"] = birthdate
    if sex is not None:       profile_update["sex"] = sex
    if height_cm is not None: profile_update["height_cm"] = height_cm
    if weight_kg is not None: profile_update["weight_kg"] = weight_kg

    update_doc = {"updated_at": datetime.utcnow(), "profileComplete": True, "profile": profile_update}
    res = mongo.db.users.update_one({"sub": sub}, {"$set": update_doc})
    if res.matched_count == 0:
        mongo.db.users.update_one(
            {"sub": sub},
            {"$set": {**update_doc, "created_at": datetime.utcnow(), "sub": sub}},
            upsert=True,
        )

    doc = mongo.db.users.find_one({"sub": sub}, {"_id": 0})
    return jsonify(ok=True, user=doc)


@api.get("/admin/users")
@requires_permission("read:users")
def list_users_admin():
    users = list(mongo.db.users.find({}, {"_id": 0}).limit(50))
    return jsonify(ok=True, users=users)

@api.put("/admin/users/profile")
@requires_permission("manage:profiles")
def admin_update_profile():
    return jsonify(ok=True)

@api.get("/reports")
@requires_any_permission("read:reports", "read:users")
def reports():
    return jsonify(ok=True, items=[])

@api.get("/me/permissions")
@requires_auth
def my_permissions():
    perms = (g.current_user or {}).get("permissions", [])
    return jsonify(ok=True, permissions=perms)



@api.post("/metrics/ingest")
@requires_auth
def metrics_ingest():

    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}
    mtype = (body.get("type") or "").strip()
    if not mtype:
        return jsonify(ok=False, error="missing type"), 400

    value = body.get("value")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify(ok=False, error="value must be numeric"), 400

    ts_str = body.get("ts")
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return jsonify(ok=False, error="ts must be ISO 8601"), 400
    else:
        ts = datetime.utcnow()

    mongo.db.measurements.insert_one({
        "sub": sub,
        "type": mtype,
        "value": value,
        "ts": ts,  # UTC naive en servidor
        "ingested_at": datetime.utcnow(),
    })
    return jsonify(ok=True)

# --- Serie por minutos (ventana configurable) ---
@api.get("/metrics/series")
@requires_auth
def metrics_series():
    sub = g.current_user.get("sub")
    mtype = request.args.get("type", "heart_rate")
    try:
        minutes = int(request.args.get("minutes", 60))
    except ValueError:
        minutes = 60
    minutes = max(1, min(minutes, 24*60))  # hasta 24h

    # límite temporal
    end = datetime.utcnow().replace(second=0, microsecond=0)
    start = end - timedelta(minutes=minutes-1)  # p.ej. 60 puntos: [t-59 ... t]

    # Trae datos de la ventana
    cur = mongo.db.measurements.find(
        {"sub": sub, "type": mtype, "ts": {"$gte": start, "$lte": end}},
        {"_id": 0, "ts": 1, "value": 1}
    ).sort("ts", 1)

    # Bin por minuto (redondeando a minuto inferior) y rellenar huecos
    by_minute = {}
    for doc in cur:
        ts = doc["ts"].replace(second=0, microsecond=0)
        # Si hay múltiples registros en el mismo minuto, nos quedamos con el último
        by_minute[ts] = float(doc["value"])

    # Construye serie completa minuto a minuto
    points = []
    t = start
    while t <= end:
        val = by_minute.get(t, None)
        points.append({"t": t.isoformat() + "Z", "v": val})
        t += timedelta(minutes=1)

    return jsonify(ok=True, type=mtype, start=start.isoformat()+"Z", end=end.isoformat()+"Z", points=points)


def _call_llm(prompt: str, model: str = None, max_tokens: int = 160, max_retries: int = 1):
    """
    Cliente mínimo para Gemini v1 (sin system_instruction ni structured outputs).
    Env requeridas:
      LLM_API_BASE=https://generativelanguage.googleapis.com/v1
      LLM_MODEL=gemini-1.5-flash-latest
      LLM_API_KEY=...
    """
    api_key  = os.getenv("LLM_API_KEY", "")
    model    = model or os.getenv("LLM_MODEL", "gemini-1.5-flash-latest")
    timeout  = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))

    if not api_key:
        raise RuntimeError("LLM_API_KEY vacío")

    # Usa query param para la clave (evita problemas con cabeceras en algunos proxies)
    headers = {"Content-Type": "application/json"}

    instruction = (
        "Eres un asistente médico. "
        "Lee los datos y devuelve SOLO un JSON válido con esta forma exacta: "
        '{"score": <entero 1..5>, "rationale": "<texto breve>"} '
        "No añadas nada más."
    )

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{ "text": instruction + "\n\n" + prompt }]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_tokens
        }
    }

    attempt, backoff = 0, 1.5
    while True:
        try:
            resp = requests.post(headers=headers, json=payload, timeout=timeout)
            if resp.status_code in (429, 503) and attempt < max_retries:
                ra = resp.headers.get("Retry-After")
                wait_s = float(ra) if ra else backoff * (2 ** attempt)
                wait_s = min(wait_s, 10.0)
                current_app.logger.warning("Gemini %s; retry in %.1fs", resp.status_code, wait_s)
                time.sleep(wait_s); attempt += 1; continue

            # Logea cuerpo si no es 2xx para ver EXACTO qué devuelve
            if not resp.ok:
                current_app.logger.error("Gemini HTTP %s body: %s", resp.status_code, resp.text)
            resp.raise_for_status()

            data = resp.json()

            # Candidatos
            cands = data.get("candidates") or []
            if not cands:
                current_app.logger.error("Gemini sin candidates: %s", data)
                raise RuntimeError("Respuesta Gemini inesperada (sin candidates)")

            parts = (cands[0].get("content") or {}).get("parts") or []

            # 1) parts[].text
            texts = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
            if texts:
                return "\n".join(texts).strip()

            # 2) parts[].inlineData (b64)
            for p in parts:
                if isinstance(p, dict) and "inlineData" in p:
                    inline = p["inlineData"]
                    if inline.get("data"):
                        try:
                            decoded = base64.b64decode(inline["data"]).decode("utf-8", errors="ignore")
                            return decoded
                        except Exception:
                            pass

            # 3) functionCall.args (JSON)
            for p in parts:
                if isinstance(p, dict) and "functionCall" in p:
                    args = (p["functionCall"] or {}).get("args")
                    if isinstance(args, dict):
                        return json.dumps(args, ensure_ascii=False)

            current_app.logger.error("Gemini sin parts utilizables: %s", parts)
            raise RuntimeError("Respuesta Gemini inesperada (sin parts.text)")
        except requests.HTTPError:
            raise
        except Exception as e:
            current_app.logger.exception("Gemini call error: %s", e)
            raise


def _sleep_prompt(profile: dict, payload: dict) -> str:
    """
    profile: {sex, height_cm, weight_kg, birthdate}
    payload: {hours, awakenings, deep_minutes, rem_minutes, quality, notes}
    """
    sex = profile.get("sex")
    birthdate = profile.get("birthdate")
    height = profile.get("height_cm")
    weight = profile.get("weight_kg")
    notes = (payload.get("notes") or "").strip()

    hours = payload.get("hours")
    awakenings = payload.get("awakenings")
    deep = payload.get("deep_minutes")
    rem = payload.get("rem_minutes")
    quality = payload.get("quality")

    return f"""
        Evalúa un episodio de SUEÑO y devuelve JSON con 'score' (1..5) y 'rationale' (breve).
        Ten en cuenta perfil y dato subjetivo si existe, pero prioriza medidas objetivas.

        PERFIL:
        - sexo: {sex}
        - altura_cm: {height}
        - peso_kg: {weight}
        - nacimiento: {birthdate}

        EPISODIO:
        - horas_totales: {hours}
        - despertares: {awakenings}
        - minutos_profundo: {deep}
        - minutos_REM: {rem}
        - calidad_subjetiva_1a5: {quality}
        - notas: {notes}

        CRITERIOS (guía, pero ajusta al contexto):
        - 1 = muy pobre: <5h, muchos despertares, casi sin profundo/REM.
        - 3 = aceptable: 6-7h, despertares moderados, algo de profundo y REM.
        - 5 = excelente: 7-9h, pocos despertares, buen reparto profundo/REM.

        Responde SOLO con JSON:
        {{"score": 1-5, "rationale": "texto corto"}}
        """

def _activity_prompt(profile: dict, payload: dict) -> str:
    """
    payload: { minutes, intensity: 'low|moderate|vigorous', steps, hr_zone_minutes, notes }
    """
    sex = profile.get("sex")
    birthdate = profile.get("birthdate")
    height = profile.get("height_cm")
    weight = profile.get("weight_kg")
    notes = (payload.get("notes") or "").strip()

    minutes = payload.get("minutes")
    intensity = payload.get("intensity")
    steps = payload.get("steps")
    hr_zone_minutes = payload.get("hr_zone_minutes") #heart rate

    return f"""
        Evalúa la ACTIVIDAD FÍSICA del día y devuelve JSON con 'score' (1..5) y 'rationale' (breve).
        Considera perfil y volumen/intensidad.

        PERFIL:
        - sexo: {sex}
        - altura_cm: {height}
        - peso_kg: {weight}
        - nacimiento: {birthdate}

        ACTIVIDAD:
        - minutos_totales: {minutes}
        - intensidad: {intensity}
        - pasos: {steps}
        - minutos_zona_cardiaca: {hr_zone_minutes}
        - notas: {notes}

        CRITERIOS (referencia general):
        - 1 = muy bajo: inactividad casi total.
        - 3 = razonable: ~30 min moderados y/o ~6k pasos.
        - 5 = muy alto: ≥60 min moderados/vigorosos y/o >10k pasos (si no hay contraindicaciones).

        Responde SOLO con JSON:
        {{"score": 1-5, "rationale": "texto corto"}}
        """

def _get_profile_for(sub: str) -> dict:
    doc = mongo.db.users.find_one({"sub": sub}, {"_id": 0})
    if not doc:
        return {}
    prof = doc.get("profile", {})
    return {
        "sex": prof.get("sex"),
        "height_cm": prof.get("height_cm"),
        "weight_kg": prof.get("weight_kg"),
        "birthdate": prof.get("birthdate"),
    }

def _store_scored_point(sub: str, mtype: str, score: int):
    now = datetime.utcnow().replace(second=0, microsecond=0)
    mongo.db.measurements.update_one(
        { "sub": sub, "type": mtype, "ts": now},
        { "$set":{
            "sub": sub, "type": mtype, "ts": now, 
            "value": score,"ingested_at": datetime.utcnow(),
        }},
        upsert=True
    )
    return now

def _clamp_score(val):
    try:
        score = int(val)
        return max(1, min(5, score))
    except (TypeError, ValueError):
        return None

@api.post("/ai/score/sleep")
@requires_auth
def ai_score_sleep():
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    ok, retry_after = _check_and_touch_cooldown(sub, "sleep")
    if not ok:
        return jsonify(ok=False, error="rate_limited", retry_after=retry_after), 429

    ph = _hash_payload(body)
    hit, cached_score = _check_dedupe(sub, "sleep", ph)
    if hit:
        ts = _store_scored_point(sub, "sleep", cached_score)
        return jsonify(ok=True, type="sleep", score=cached_score, ts=ts.isoformat()+"Z", cached=True)


    profile = _get_profile_for(sub)
    prompt = _sleep_prompt(profile, body)

    try:
        content = _call_llm(prompt, max_tokens=180)
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 503
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            ra = e.response.headers.get("Retry-After")
            return jsonify(ok=False, error="llm_rate_limited", retry_after=float(ra) if ra else None), 429
        return jsonify(ok=False, error="llm_http_error", details=getattr(e.response, "text", "")), 502
    except Exception as e:
        return jsonify(ok=False, error="llm_unavailable", details=str(e)), 503
    
    try:
        parsed = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.S)
        if not m: return jsonify(ok=False, error="llm_invalid_json", raw=content), 502
        parsed = json.loads(m.group(0))
    
    score = _clamp_score(parsed.get("score"))
    if(score is None):
        return jsonify(ok=False, error="LLM_missing_score", raw=content), 502
    
    _store_dedupe(sub, "sleep", ph, score)
    ts = _store_scored_point(sub, "sleep", score)
    return jsonify(ok=True, type="sleep", score=score,  ts=ts.isoformat()+"Z", rationale=parsed.get("rationale"))


@api.post("/ai/score/activity")
@requires_auth
def ai_score_activity():
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    ok, retry_after = _check_and_touch_cooldown(sub, "activity")
    if not ok:
        return jsonify(ok=False, error="rate_limited", retry_after=retry_after), 429

    ph = _hash_payload(body)
    hit, cached_score = _check_dedupe(sub, "activity", ph)
    if hit:
        ts = _store_scored_point(sub, "activity", cached_score)
        return jsonify(ok=True, type="activity", score=cached_score, ts=ts.isoformat()+"Z", cached=True)


    profile = _get_profile_for(sub)
    prompt = _activity_prompt(profile, body)

    try:
        content = _call_llm(prompt, max_tokens=180)
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 503
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            ra = e.response.headers.get("Retry-After")
            return jsonify(ok=False, error="llm_rate_limited", retry_after=float(ra) if ra else None), 429
        return jsonify(ok=False, error="llm_http_error", details=getattr(e.response, "text", "")), 502
    except Exception as e:
        return jsonify(ok=False, error="llm_unavailable", details=str(e)), 503
    
    try:
        parsed = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.S)
        if not m: return jsonify(ok=False, error="llm_invalid_json", raw=content), 502
        parsed = json.loads(m.group(0))

    score = _clamp_score(parsed.get("score"))
    if(score is None):
        return jsonify(ok=False, error="LLM_missing_score", raw=content), 502
    
    _store_dedupe(sub, "activity", ph, score)
    ts = _store_scored_point(sub, "activity", score)
    return jsonify(ok=True, type="activity", score=score, ts=ts.isoformat()+"Z", rationale=parsed.get("rationale"))