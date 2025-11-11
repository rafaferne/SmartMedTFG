import os
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv
from extensions import mongo

load_dotenv()

def create_app():
    app = Flask(__name__)

    app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://mongo:27017/flask_tutorial")
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")

    FRONT = os.getenv("FRONT_ORIGIN", "http://localhost:5173")
    CORS(app, resources={
        r"/api/*": {
            "origins": [FRONT],
            "methods": ["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
            "allow_headers": ["Authorization","Content-Type"],
            "expose_headers": ["Authorization"],
            "max_age": 86400,
        }
    })

    # Inicializar extensiones
    mongo.init_app(app)
    with app.app_context():
        mongo.db.users.create_index("sub", unique=True)
        mongo.db.measurements.create_index([("sub",1),("type",1),("ts",1)], unique=True)
        mongo.db.ai_calls.create_index([("sub", 1), ("type", 1)], unique=True)
        mongo.db.ai_cache.create_index([("sub", 1), ("type", 1), ("hash", 1)])
        mongo.db.simulations.create_index([("sub", 1), ("type", 1), ("created_at", -1)])


    # Blueprints
    from routes import api
    app.register_blueprint(api, url_prefix="/api")

    # Manejadores de errores
    from auth import AuthError, handle_auth_error
    app.register_error_handler(AuthError, handle_auth_error)

    @app.errorhandler(Exception)
    def handle_any_error(e):
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Unhandled error: %s", e)
        return jsonify(ok=False, error="internal_error"), 500

    # Diagnóstico rápido (temporal)
    @app.get("/api/__diag")
    def diag():
        import socket
        auth0 = os.getenv("AUTH0_DOMAIN", "")
        audience = os.getenv("AUTH0_AUDIENCE", "")
        try:
            resolved = socket.gethostbyname(auth0.split("/")[0]) if auth0 else "missing"
        except Exception as ex:
            resolved = f"DNS error: {ex}"
        return jsonify(ok=True, front_origin=FRONT, auth0_domain=auth0,
                       audience=audience, dns_resolved=resolved)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
