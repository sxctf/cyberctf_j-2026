from flask import Blueprint, render_template

from app.config import get_settings


pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    settings = get_settings()
    return render_template(
        "index.html",
        agent_name=settings.agent_name,
        console_title=settings.console_title,
        experiment_name=settings.experiment_name,
    )

