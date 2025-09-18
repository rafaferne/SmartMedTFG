from flask import Blueprint, jsonify, request, g
from datetime import datetime
from auth import requires_auth
from extensions import mongo

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
