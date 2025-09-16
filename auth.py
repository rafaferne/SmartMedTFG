import os
import json
from functools import wraps
from urllib.request import urlopen

import jwt
from flask import request, jsonify, g
from dotenv import load_dotenv

load_dotenv()

AUTH0_DOMAIN   = os.getenv("AUTH0_DOMAIN", "")
API_IDENTIFIER = os.getenv("AUTH0_AUDIENCE", "")
ALGORITHMS     = ["RS256"]

class AuthError(Exception):
    def __init__(self, error, status_code=401):
        self.error = error
        self.status_code = status_code

def handle_auth_error(ex):
    resp = jsonify(ex.error)
    resp.status_code = ex.status_code
    return resp

def get_token_auth_header():
    auth = request.headers.get("Authorization", None)
    if not auth:
        raise AuthError({"code": "authorization_header_missing",
                         "description": "Falta cabecera Authorization"}, 401)
    parts = auth.split()
    if parts[0].lower() != "bearer":
        raise AuthError({"code": "invalid_header",
                         "description": "La cabecera debe empezar con Bearer"}, 401)
    if len(parts) == 1:
        raise AuthError({"code": "invalid_header",
                         "description": "Token no encontrado"}, 401)
    if len(parts) > 2:
        raise AuthError({"code": "invalid_header",
                         "description": "Formato 'Bearer <token>'"}, 401)
    return parts[1]

def requires_auth(f):
    """Valida Access Token de Auth0 (RS256) y deja el payload en g.current_user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_auth_header()

        jwks = json.loads(urlopen(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json").read())
        unverified_header = jwt.get_unverified_header(token)

        rsa_key = {}
        for key in jwks.get("keys", []):
            if key.get("kid") == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n":   key["n"],
                    "e":   key["e"],
                }
                break

        if not rsa_key:
            raise AuthError({"code": "invalid_header",
                             "description": "No se encontró clave válida (kid) para el token"}, 401)

        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=API_IDENTIFIER,
                issuer=f"https://{AUTH0_DOMAIN}/",
            )
        except jwt.ExpiredSignatureError:
            raise AuthError({"code": "token_expired", "description": "Token expirado"}, 401)
        except (jwt.InvalidAudienceError, jwt.InvalidIssuerError, jwt.InvalidTokenError):
            raise AuthError({"code": "invalid_claims",
                             "description": "audience/issuer inválidos o token inválido"}, 401)

        g.current_user = payload
        return f(*args, **kwargs)
    return decorated
