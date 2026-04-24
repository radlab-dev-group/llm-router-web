import os
import json
from flask import Flask, redirect, url_for, session

# Blueprint is located in the same package
from .routes import anonymize_bp


def create_anonymize_app() -> Flask:
    """
    A lightweight Flask application whose sole purpose is to handle
    the /anonymize endpoint.
    """
    app = Flask(
        __name__,
        # Share static resources with the main application
        static_folder=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "static")
        ),
        # Templates are located in web/anonymize/templates
        template_folder=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "templates")
        ),
    )

    # ---- Internationalization (i18n) Setup ----
    translations = {}
    trans_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "translations")
    )
    for lang in ["pl", "en"]:
        path = os.path.join(trans_dir, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                translations[lang] = json.load(f)
        except Exception as e:
            print(f"Error loading translation {lang}: {e}")
            translations[lang] = {}

    app.config["TRANSLATIONS"] = translations

    def get_text(key, **kwargs):
        """Helper function to retrieve translated text."""
        lang = session.get("lang", "pl")
        # Fallback to English if language not found, then to "NO TRANSLATION"
        texts = app.config["TRANSLATIONS"].get(
            lang, app.config["TRANSLATIONS"].get("en", {})
        )
        text = texts.get(key, "NO TRANSLATION")
        return text.format(**kwargs) if kwargs else text

    # Register the helper function as a global in Jinja2 templates
    app.jinja_env.globals.update(_=get_text)

    # ---- Configuration (environment variables) ----
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me-anonymizer")
    # Address of the external anonymizing service
    app.config["LLM_ROUTER_HOST"] = os.getenv(
        "LLM_ROUTER_HOST", "http://localhost:8000"
    )

    # Address of the PII anonymization service
    app.config["PII_SERVICE_HOST"] = os.getenv(
        "PII_SERVICE_HOST", "http://localhost:5001"
    )

    # ---- Blueprint registration ----
    app.register_blueprint(anonymize_bp)

    @app.route("/", endpoint="index")
    def root():
        # You can redirect to a form or display a short page
        return redirect(url_for("anonymize_web.show_form"))

    # ---- Simple error handlers (return JSON) ----
    @app.errorhandler(400)
    def handle_400(error):
        return {"error": error.description or "Bad request"}, 400

    @app.errorhandler(404)
    def handle_404(error):
        return {"error": "Resource not found"}, 404

    @app.errorhandler(500)
    def handle_500(error):
        return {"error": "Internal server error"}, 500

    return app
