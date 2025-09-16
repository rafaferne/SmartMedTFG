import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from extensions import mongo

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Config
    app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://mongo:27017/flask_tutorial")
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")

    # CORS solo para /api/* desde tu front
    CORS(app, resources={r"/api/*": {"origins": os.getenv("FRONT_ORIGIN", "http://localhost:5173")}})

    # Extensiones
    mongo.init_app(app)

    # Índices
    with app.app_context():
        mongo.db.users.create_index("sub", unique=True)

    # Blueprints 
    from routes import api
    app.register_blueprint(api, url_prefix="/api")

    # Manejador de errores de Auth
    from auth import AuthError, handle_auth_error
    app.register_error_handler(AuthError, handle_auth_error)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
