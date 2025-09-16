from flask import Blueprint, jsonify, request, g
from datetime import datetime
import pandas as pd

from auth import requires_auth
from extensions import mongo

api = Blueprint("api", __name__)

@api.get("/ping")
def ping():
    return jsonify(ok=True, msg="pong")

@api.get("/user")
@requires_auth
def user():
    return jsonify(ok=True, msg="Acceso con token válido")

@api.post("/file_upload")
@requires_auth
def file_upload():
    file = request.files.get("archivo")
    if not file:
        return ("No file", 400)
    name = (file.filename or "").lower()
    if name.endswith(".tsv"):
        df = pd.read_csv(file, sep="\t")
    elif name.endswith(".csv"):
        df = pd.read_csv(file)
    elif name.endswith(".xlsx"):
        df = pd.read_excel(file, engine="openpyxl")
    else:
        return ("Formato no soportado", 415)
    return jsonify(preview=df.head(5).to_dict(orient="records"))

# ---------- Perfil del usuario (Mongo) ----------

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
        return jsonify(error="sub missing from token"), 400

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or payload.get("email") or "").strip().lower() or None
    name  = (data.get("name")  or payload.get("name")  or "").strip()          or None
    picture = (data.get("picture") or payload.get("picture") or None)

    set_doc = {"sub": sub, "updated_at": datetime.utcnow()}
    if email:   set_doc["email"] = email
    if name:    set_doc["name"] = name
    if picture: set_doc["picture"] = picture

    mongo.db.users.update_one(
        {"sub": sub},
        {
            "$set": set_doc,
            "$setOnInsert": {
                "profile": {},
                "profileComplete": False,
                "created_at": datetime.utcnow(),
            },
        },
        upsert=True,
    )
    return jsonify(ok=True)

@api.put("/me/profile")
@requires_auth
def me_profile_update():
    sub = g.current_user.get("sub")
    body = request.get_json(silent=True) or {}

    def err(msg): return jsonify(ok=False, error=msg), 400

    birthdate = body.get("birthdate")  # "YYYY-MM-DD" o None
    sex       = body.get("sex")        # "male"|"female"|"other"|"prefer_not_say"
    height_cm = body.get("height_cm")
    weight_kg = body.get("weight_kg")
    notes     = body.get("notes", "")

    # Validaciones básicas
    if birthdate:
        try:
            datetime.strptime(birthdate, "%Y-%m-%d")
        except ValueError:
            return err("birthdate debe ser YYYY-MM-DD")

    allowed_sex = {"male", "female", "other", "prefer_not_say", None}
    if sex not in allowed_sex:
        return err("sex inválido")

    def is_num(x):
        if x in (None, ""):
            return True
        try:
            float(x)
            return True
        except (TypeError, ValueError):
            return False

    if not is_num(height_cm): return err("height_cm inválido")
    if not is_num(weight_kg): return err("weight_kg inválido")

    if height_cm not in (None, ""):
        height_cm = float(height_cm)
        if not (40 <= height_cm <= 300):
            return err("height_cm fuera de rango (40-300)")
    else:
        height_cm = None

    if weight_kg not in (None, ""):
        weight_kg = float(weight_kg)
        if not (1 <= weight_kg <= 600):
            return err("weight_kg fuera de rango (1-600)")
    else:
        weight_kg = None

    # Construir update
    profile_update = {}
    for k, v in {
        "birthdate": birthdate,
        "sex": sex,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "notes": notes,
    }.items():
        if v is not None:
            profile_update[k] = v

    update_doc = {"updated_at": datetime.utcnow()}
    if profile_update:
        update_doc["profile"] = profile_update
        update_doc["profileComplete"] = True

    res = mongo.db.users.update_one({"sub": sub}, {"$set": update_doc})

    if res.matched_count == 0:
        mongo.db.users.update_one(
            {"sub": sub},
            {
                "$set": {
                    "profile": profile_update,
                    "profileComplete": True,
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

    doc = mongo.db.users.find_one({"sub": sub}, {"_id": 0})
    return jsonify(ok=True, user=doc)
