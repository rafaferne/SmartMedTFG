import os, json, time
from functools import wraps
from urllib.request import urlopen, URLError

import jwt
from flask import request, jsonify, g, current_app
from dotenv import load_dotenv
from jwt.algorithms import RSAAlgorithm

load_dotenv()

AUTH0_DOMAIN   = os.getenv("AUTH0_DOMAIN", "")
API_IDENTIFIER = os.getenv("AUTH0_AUDIENCE", "")
ALGORITHMS     = ["RS256"]

# Cache simple del JWKS para evitar pedirlo en cada request
_JWKS_CACHE = {"keys": []}
_JWKS_TS = 0
_JWKS_TTL = 600 

class AuthError(Exception):
    def __init__(self, error, status_code=401):
        self.error = error
        self.status_code = status_code

def handle_auth_error(ex):
    current_app.logger.warning(f"[AuthError {ex.status_code}] {ex.error}")
    resp = jsonify(ex.error)
    resp.status_code = ex.status_code
    return resp

def get_token_auth_header():
    auth = request.headers.get("Authorization", None)
    if not auth:
        raise AuthError({"code":"authorization_header_missing","description":"Falta cabecera Authorization"}, 401)
    parts = auth.split()
    if parts[0].lower() != "bearer":
        raise AuthError({"code":"invalid_header","description":"Debe empezar con Bearer"}, 401)
    if len(parts) == 1:
        raise AuthError({"code":"invalid_header","description":"Token no encontrado"}, 401)
    if len(parts) > 2:
        raise AuthError({"code":"invalid_header","description":"Formato 'Bearer <token>'"}, 401)
    return parts[1]

def _get_jwks():
    global _JWKS_CACHE, _JWKS_TS
    now = time.time()
    if _JWKS_CACHE.get("keys") and (now - _JWKS_TS) < _JWKS_TTL:
        return _JWKS_CACHE
    if not AUTH0_DOMAIN:
        raise AuthError({"code":"misconfigured","description":"AUTH0_DOMAIN vacío"}, 500)
    try:
        with urlopen(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json", timeout=5) as resp:
            _JWKS_CACHE = json.loads(resp.read())
            _JWKS_TS = now
            return _JWKS_CACHE
    except (URLError, Exception) as e:
        # 503 legible (CORS se aplicará)
        raise AuthError({"code":"jwks_unreachable","description":f"No se pudo obtener JWKS: {e}"}, 503)


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_IDENTIFIER:
            raise AuthError({"code":"misconfigured","description":"AUTH0_AUDIENCE vacío"}, 500)

        token = get_token_auth_header()
        jwks = _get_jwks()

        try:
            unverified = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise AuthError({"code":"invalid_token","description":"Token mal formado"}, 401)

        # Buscar la clave JWK por kid
        jwk_key = next(
            (k for k in jwks.get("keys", []) if k.get("kid") == unverified.get("kid")),
            None
        )
        if not jwk_key:
            raise AuthError({"code":"invalid_header","description":"No se encontró clave válida (kid)"}, 401)

        try:
            public_key = RSAAlgorithm.from_jwk(json.dumps(jwk_key))
        except Exception as e:
            raise AuthError({"code":"invalid_jwk","description":f"Clave JWK inválida: {e}"}, 401)

        try:
            payload = jwt.decode(
                token,
                key=public_key,
                algorithms=ALGORITHMS,
                audience=API_IDENTIFIER,
                issuer=f"https://{AUTH0_DOMAIN}/",
            )
        except jwt.ExpiredSignatureError:
            raise AuthError({"code":"token_expired","description":"Token expirado"}, 401)
        except (jwt.InvalidAudienceError, jwt.InvalidIssuerError, jwt.InvalidTokenError):
            raise AuthError({"code":"invalid_claims","description":"aud/iss inválidos o token inválido"}, 401)

        g.current_user = payload
        return f(*args, **kwargs)
    return decorated


def _get_permissions_from_token():
    # Auth0 añade 'permissions' si activaste "Add Permissions in the Access Token"
    from flask import g
    perms = (g.current_user or {}).get("permissions")
    if perms is None:
        # Si no vienen, será porque no activaste la opción en Auth0
        # o porque estás usando un token sin audience. Lo tratamos como lista vacía.
        perms = []
    return set(perms)

def requires_permission(*required):
    """Requiere que el token tenga TODOS los permisos indicados."""
    def wrapper(f):
        @wraps(f)
        @requires_auth
        def decorated(*args, **kwargs):
            perms = _get_permissions_from_token()
            missing = [p for p in required if p not in perms]
            if missing:
                raise AuthError({
                    "code": "insufficient_permissions",
                    "description": f"Faltan permisos: {', '.join(missing)}"
                }, 403)
            return f(*args, **kwargs)
        return decorated
    return wrapper

def requires_any_permission(*candidates):
    """Requiere que el token tenga AL MENOS uno de los permisos indicados."""
    def wrapper(f):
        @wraps(f)
        @requires_auth
        def decorated(*args, **kwargs):
            perms = _get_permissions_from_token()
            if not any(p in perms for p in candidates):
                raise AuthError({
                    "code": "insufficient_permissions",
                    "description": f"Se requiere alguno de: {', '.join(candidates)}"
                }, 403)
            return f(*args, **kwargs)
        return decorated
    return wrapper

