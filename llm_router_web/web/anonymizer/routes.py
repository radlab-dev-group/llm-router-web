# -*- coding: utf-8 -*-

"""
Flask blueprint for the text anonymization web interface.

Provides endpoints for:
* anonymization form
* anonymization processing
* chat UI
* model catalogue (proxy to the LLM‑Router `/models` endpoint)
"""

import json
import socket
from typing import Tuple, Dict

import requests

from flask import (
    Blueprint,
    current_app,
    request,
    render_template,
    jsonify,
    Response,
    stream_with_context,
    session,
)

from .constants import GENAI_MODEL_ANON

# Blueprint configuration
anonymize_bp = Blueprint(
    "anonymize_web",
    __name__,
    url_prefix="/anonymize",  # http://HOST:PORT/anonymize
    template_folder="../templates",  # templates in web/anonymize/templates
)


@anonymize_bp.route("/", methods=["GET"])
def show_form():
    """Render the anonymization form."""
    return render_template(
        "anonymize.html",
        api_host=current_app.config["LLM_ROUTER_HOST"],
        result=None,
    )


@anonymize_bp.route("/", methods=["POST"])
def process_text():
    """Send text to the external anonymization service and render the result."""
    raw_text = request.form.get("text", "")
    if not raw_text:
        return "⚠️ No text provided.", 400

    algorithm = request.form.get("algorithm", "fast")
    model_name = request.form.get("model_name", "").strip()

    router_host = current_app.config["LLM_ROUTER_HOST"].rstrip("/")
    pii_host = current_app.config["PII_SERVICE_HOST"].rstrip("/")

    # Helper to call the PII service
    def call_pii_service(text, model) -> Dict | str:
        labels = ["LOCATION", "PERSON"]
        try:
            # Analogous to pii/index.html call
            resp = requests.post(
                f"{pii_host}/predict_and_anonymize",
                json={
                    "text": text,
                    "model": model or "1-PLC: 20260417_213751",
                    "labels": labels,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data
        except Exception as e:
            return f"❌ PII Service Error: {e}"

    # Helper to call the Router service
    def call_router_service(text, model, endpoint):
        try:
            resp = requests.post(
                f"{router_host}{endpoint}",
                json={"text": text, "model_name": model or "gpt-oss:120b"},
                timeout=600,
            )
            resp.raise_for_status()
            data = resp.json()
            return data
        except Exception as e:
            return f"❌ Router Service Error: {e}"

    # Logic for the selected algorithm
    if algorithm == "pii_masking":
        result = call_pii_service(raw_text, model_name)

    elif algorithm == "fast+pii":
        # 1. Run PII first
        pii_result = call_pii_service(raw_text, model_name)
        if pii_result is str:
            pii_result = {}

        # 2. Run Fast Masker on the result of PII
        result_ft = call_router_service(
            pii_result.get("text", raw_text), model_name, "/api/fast_text_mask"
        )

        result = result_ft
        for _k, _v in pii_result.get("mappings", {}).items():
            result["mappings"][_k] = _v

    elif algorithm == "fast":
        result = call_router_service(raw_text, model_name, "/api/fast_text_mask")

    elif algorithm == "genai":
        if not GENAI_MODEL_ANON:
            return render_template(
                "anonymize_result_partial.html",
                result={"error": "genai model is not set"},
            )
        result = call_router_service(
            raw_text, model_name, "/api/anonymize_text_genai"
        )

    elif algorithm == "priv":
        return render_template(
            "anonymize_result_partial.html",
            result={"error": "priv_masker is not available yet"},
        )

    else:
        return render_template(
            "anonymize_result_partial.html",
            result={"error": f"Not supported method {algorithm}."},
        )

    return render_template(
        "anonymize_result_partial.html",
        api_host=current_app.config["LLM_ROUTER_HOST"],
        result=result,
    )


# ----------------------------------------------------------------------
# Chat UI
# ----------------------------------------------------------------------
@anonymize_bp.route("/chat", methods=["GET"])
def show_chat():
    """Render the dedicated chat page."""
    return render_template(
        "chat.html",
        api_host=current_app.config["LLM_ROUTER_HOST"],
    )


@anonymize_bp.route("/chat/message", methods=["POST"])
def chat_message():
    """Forward a chat message to the LLM‑Router and stream the reply."""
    user_msg = request.form.get("message", "")
    if not user_msg:
        return "⚠️ No message provided.", 400

    # Sprawdzenie czy rozpoczęto nowy czat
    new_chat = request.form.get("new_chat") == "true"
    if new_chat:
        session["chat_history"] = []

    algorithm = request.form.get("algorithm", "fast")
    model_name = request.form.get("model_name", "").strip()

    # Pobranie historii z sesji lub inicjalizacja nowej listy
    history = session.get("chat_history", [])
    history.append({"role": "user", "content": user_msg})

    # WAŻNE: przy domyślnej sesji cookie nie da się zapisać zmian "po streamie"
    # (nagłówki są wysyłane zanim generator skończy). Zapisujemy więc historię
    # użytkownika OD RAZU, a odpowiedź asystenta dopiszemy osobnym requestem (finalize).
    session["chat_history"] = history
    session.modified = True

    payload = {
        "stream": True,
        "anonymize": algorithm != "no_anno",
        "model": model_name,
        "messages": history,
    }

    external_url = (
        f"{current_app.config['LLM_ROUTER_HOST'].rstrip('/')}" "/v1/chat/completions"
    )

    try:
        # Use stream=True so that we can forward the chunks to the client
        resp = requests.post(
            external_url,
            json=payload,
            timeout=600,
            stream=True,
        )
        if resp.status_code >= 500:
            error_msg = (
                resp.json()
                .get("error", {})
                .get("message", f"LLM‑Router returned {resp.status_code}")
            )
            return (
                Response(
                    render_template("chat_partial.html", chat=error_msg),
                    mimetype="text/html",
                ),
                502,
            )
        resp.raise_for_status()
    except (requests.RequestException, socket.error) as exc:
        current_app.logger.exception("Chat service request failed")
        error_html = render_template(
            "chat_partial.html", chat=f"❌ Chat service error: {exc}"
        )
        return Response(error_html, mimetype="text/html"), 502

    def generate():
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            cleaned = line.strip()
            if cleaned.startswith("data:"):
                cleaned = cleaned[5:].lstrip()

            if cleaned == "[DONE]":
                continue

            if not cleaned:
                continue

            try:
                data = json.loads(cleaned)
                chunk = (
                    data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                )
            except Exception:
                chunk = cleaned

            if chunk:
                yield chunk

    return Response(stream_with_context(generate()), mimetype="text/html")


@anonymize_bp.route("/chat/finalize", methods=["POST"])
def chat_finalize():
    """
    Persist assistant response in session.

    This is required when using Flask's default cookie-based session:
    you cannot modify session after streaming starts (headers already sent).
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    assistant_msg = (payload.get("assistant") or "").strip()
    if not assistant_msg:
        return jsonify({"ok": False, "error": "Missing assistant message"}), 400

    history = session.get("chat_history", [])
    history.append({"role": "assistant", "content": assistant_msg})
    session["chat_history"] = history
    session.modified = True
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# Model catalogue – proxy to the router’s `/models` endpoint
# ----------------------------------------------------------------------
@anonymize_bp.route("/models", methods=["GET"])
def models():
    """
    Retrieve the list of available models from the external LLM‑Router.
    The frontend calls this endpoint (e.g. via `fetch`) to fill the model dropdown.
    """
    external_url = f"{current_app.config['LLM_ROUTER_HOST'].rstrip('/')}" "/models"
    try:
        resp = requests.get(external_url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        current_app.logger.error(f"Failed to fetch models: {exc}")
        return jsonify({"models": []}), 500

    try:
        data = resp.json()
    except ValueError:
        current_app.logger.error("Models endpoint returned non‑JSON.")
        return jsonify({"models": []}), 500

    models = data.get("models") or data.get("data") or []
    return jsonify({"models": models})
