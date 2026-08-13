import os
import json
import logging
import secrets
import requests

from urllib.parse import urlparse
from flask import Flask, redirect, url_for, session

from .routes import anonymize_bp


def _check_host_availability(
    host: str, path: str, label: str, timeout: float = 3.0
) -> None:
    """
    Check if an external service host is reachable.

    Logs INFO on success or WARNING on failure. Never raises — the app
    starts regardless of the result.
    """
    parsed = urlparse(host)
    if not parsed.scheme or not parsed.netloc:
        logging.warning("  %s: skipping check — invalid URL format: %r", label, host)
        return

    base_url = host.rstrip("/")
    target = (
        f"{base_url}{path}"
        if path.startswith("/")
        else f"{base_url}/{path.lstrip('/')}"
    )

    try:
        resp = requests.get(target, timeout=timeout)
        # Any status < 500 means the server is responding
        # (4xx = reachable, auth-required, etc.)
        logging.info("  %s (%s): OK (HTTP %d)", label, target, resp.status_code)
    except requests.exceptions.ConnectionError:
        logging.warning(
            "  %s (%s): NOT REACHABLE — connection refused", label, target
        )
    except requests.exceptions.Timeout:
        logging.warning(
            "  %s (%s): NOT REACHABLE — timeout after %.0fs", label, target, timeout
        )
    except Exception as exc:
        # SSL errors, malformed URLs etc. — treat as reachable (connection succeeded)
        status = "?"
        if hasattr(exc, "response") and exc.response is not None:
            status = str(exc.response.status_code)
        logging.info("  %s (%s): OK (HTTP %s)", label, target, status)


def create_anonymize_app() -> Flask:
    """
    A lightweight Flask application whose sole purpose is to handle
    the /anonymize endpoint.
    """
    app = Flask(
        __name__,
        # Share static resources with the main application
        static_folder=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "static")
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

    _secret = os.getenv("FLASK_SECRET_KEY")
    if not _secret:
        logging.warning(
            "FLASK_SECRET_KEY is not set! Using auto-generated key — "
            "sessions will be invalidated on restart."
        )
        _secret = secrets.token_hex(32)
    app.config["SECRET_KEY"] = _secret

    # Address of the llm-router API
    app.config["LLM_ROUTER_HOST"] = os.getenv(
        "LLM_ROUTER_HOST", "http://localhost:8000"
    ).rstrip("/")

    # Address of the llm-router-services API
    app.config["LLM_ROUTER_SERVICES_HOST"] = os.getenv(
        "LLM_ROUTER_SERVICES_HOST", "http://localhost:5000"
    ).rstrip("/")

    # API key for authenticating requests to the LLM-Router service
    app.config["LLM_ROUTER_API_KEY"] = os.getenv("LLM_ROUTER_API_KEY", "")

    app.register_blueprint(anonymize_bp)

    @app.route("/", endpoint="index")
    def root():
        # You can redirect to a form or display a short page
        return redirect(url_for("anonymize_web.show_form"))

    @app.errorhandler(400)
    def handle_400(error):
        return {"error": error.description or "Bad request"}, 400

    @app.errorhandler(404)
    def handle_404(error):
        return {"error": "Resource not found"}, 404

    @app.errorhandler(500)
    def handle_500(error):
        return {"error": "Internal server error"}, 500

    # Check external service availability at startup
    logging.info("Checking external service availability:")
    _check_host_availability(
        app.config["LLM_ROUTER_SERVICES_HOST"], "/api/maskers/pii", "PII Masker"
    )
    _check_host_availability(app.config["LLM_ROUTER_HOST"], "/models", "LLM Router")

    return app
