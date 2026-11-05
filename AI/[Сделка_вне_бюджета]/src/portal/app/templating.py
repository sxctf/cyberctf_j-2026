import json
from pathlib import Path
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["tojson"] = lambda v: Markup(json.dumps(v))
