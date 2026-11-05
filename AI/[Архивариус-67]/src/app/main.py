from app import create_app
from app.config import get_settings


app = create_app()


def run() -> None:
    settings = get_settings()
    app.run(host=settings.host, port=settings.port, debug=False)


if __name__ == "__main__":
    run()

