from flask import Flask

from app.routes.api import api_bp
from app.routes.pages import pages_bp
from app.services import state_store


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config["JSON_AS_ASCII"] = False

    state_store.initialize_state()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    return app
