# -*- coding: utf-8 -*-

"""
Flask blueprint for the text anonymization web interface.

This module defines the routing logic for the anonymization web application,
providing a bridge between the user interface and the backend services
(PII Service and LLM-Router). It handles text processing requests,
maintains chat sessions, and provides a model catalogue.

Endpoints provided:
    - /: GET (show form), POST (process anonymization)
    - /chat: GET (show chat UI)
    - /chat/message: POST (handle and stream chat messages)
    - /chat/finalize: POST (save assistant response to session)
    - /chat/import: POST (import chat history)
    - /models: GET (fetch available models)
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
    redirect,
    url_for,
)

from .constants import GENAI_MODEL_ANON, DEFAULT_PII_MODEL_NAME


def _t(key):
    """Helper function to translate strings within routes.py"""
    lang = session.get("lang", "pl")
    translations = current_app.config.get("TRANSLATIONS", {})
    texts = translations.get(lang, translations.get("en", {}))
    return texts.get(key, f"NO TRANSLATION: {key}")


# Blueprint configuration
anonymize_bp = Blueprint(
    "anonymize_web",
    __name__,
    url_prefix="/anonymize",
    template_folder="../templates",
)


@anonymize_bp.route("/", methods=["GET"])
def show_form():
    """
    Render the main anonymization input form.

    Returns:
        The rendered 'anonymize.html' template containing the text input
        and algorithm selection options.
    """
    return render_template(
        "anonymize.html",
        api_host=current_app.config["LLM_ROUTER_HOST"],
        result=None,
    )


@anonymize_bp.route("/privacy", methods=["GET"])
def show_privacy():
    """
    Render the privacy policy page.
    """
    return render_template("privacy.html")


@anonymize_bp.route("/terms", methods=["GET"])
def show_terms():
    """
    Render the terms of service page.
    """
    return render_template("terms.html")


@anonymize_bp.route("/set_lang/<lang>", methods=["GET"])
def set_lang(lang):
    """
    Change the application language and redirect back to the previous page.
    """
    if lang not in ["pl", "en"]:
        lang = "pl"
    session["lang"] = lang
    return redirect(request.referrer or url_for("anonymize_web.show_form"))


@anonymize_bp.route("/", methods=["POST"])
def process_text():
    """
    Process the submitted text for anonymization based on the selected algorithm.

    This method extracts the text, chosen algorithm, and model name from the
    request form. Depending on the algorithm, it delegates the task to
    the PII service or the LLM-Router.

    Returns:
        A rendered 'anonymize_result_partial.html' template containing
        the anonymized text and the mapping of original values to masks.
    """
    raw_text = request.form.get("text", "")
    if not raw_text:
        return "⚠️ No text provided.", 400

    algorithm = request.form.get("algorithm", "fast")
    model_name = request.form.get("model_name", "").strip()

    router_host = current_app.config["LLM_ROUTER_HOST"].rstrip("/")
    pii_host = current_app.config["PII_SERVICE_HOST"].rstrip("/")

    def call_pii_service(text: str, model: str) -> Dict | str:
        """
        Helper to call the PII (Personally Identifiable Information) service.

        Args:
            text (str): The text to be anonymized.
            model (str): The PII model name to use.

        Returns:
            Dict: The response from the PII service containing anonymized text
                  and mappings if successful.
            str: An error message if the request fails.
        """
        labels = ["LOCATION", "PERSON"]
        try:
            # Analogous to pii/index.html call
            resp = requests.post(
                f"{pii_host}/predict_and_anonymize",
                json={
                    "text": text,
                    "model": model or DEFAULT_PII_MODEL_NAME,
                    "labels": labels,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return f"❌ PII Service Error: {e}"

    def call_router_service(text: str, model: str, endpoint: str):
        """
        Helper to call the LLM-Router service.

        Args:
            text (str): The text to process.
            model (str): The model name to use.
            endpoint (str): The specific API endpoint on the router.

        Returns:
            Dict: The JSON response from the router service.
            str: An error message if the request fails.
        """
        try:
            resp = requests.post(
                f"{router_host}{endpoint}",
                json={"text": text, "model_name": model or "gpt-oss:120b"},
                timeout=600,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return f"❌ Router Service Error: {e}"

    # Logic for the selected algorithm
    if algorithm == "pii_masking":
        result = call_pii_service(raw_text, model_name)

    elif algorithm == "fast+pii":
        pii_result = call_pii_service(raw_text, model_name)
        if isinstance(pii_result, str):
            pii_result = {}

        result_ft = call_router_service(
            pii_result.get("text", raw_text), model_name, "/api/fast_text_mask"
        )

        result = result_ft
        for _k, _v in pii_result.get("mappings", {}).items():
            result.setdefault("mappings", {})[_k] = _v
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

    else:
        return render_template(
            "anonymize_result_partial.html",
            result={"error": f"Not supported method {algorithm}."},
        )

    _p_map = {}
    if isinstance(result, dict):
        for _k, _v in result.get("mappings", {}).items():
            key = _k if _k.startswith("{") else "{" + _k + "}"
            _p_map[key] = _v
        result["mappings"] = _p_map

    return render_template(
        "anonymize_result_partial.html",
        api_host=current_app.config["LLM_ROUTER_HOST"],
        result=result,
    )


@anonymize_bp.route("/chat", methods=["GET"])
def show_chat():
    """
    Render the dedicated chat interface page.

    Returns:
        The rendered 'chat.html' template.
    """
    return render_template(
        "chat.html", api_host=current_app.config["LLM_ROUTER_HOST"]
    )


@anonymize_bp.route("/chat/message", methods=["POST"])
def chat_message():
    """
    Forward a chat message to the LLM-Router and stream the response back.

    This method handles user input, manages the session-based chat history,
    and implements a streaming response using a generator to ensure
    the UI updates in real-time.

    Returns:
        A streaming Response object containing the LLM's output.
    """
    user_msg = request.form.get("message", "")
    if not user_msg:
        return "⚠️ No message provided.", 400

    system_prompt = request.form.get("system_prompt", "").strip()

    # Check if a new chat has been started
    new_chat = request.form.get("new_chat") == "true"
    if new_chat:
        session["chat_history"] = []

    algorithm = request.form.get("algorithm", "fast")
    model_name = request.form.get("model_name", "").strip()

    # Retrieve history from session or initialize a new list
    history = session.get("chat_history", [])
    history.append({"role": "user", "content": user_msg})

    # IMPORTANT: With the default cookie-based session, it is not possible to
    # save changes "after the stream" (because headers are sent before
    # the generator finishes). Therefore, we save the user's history
    # IMMEDIATELY, and the assistant's response will be added via a
    # separate request (finalize).
    session["chat_history"] = history
    session.modified = True

    # Build the payload for the LLM-Router.
    # If a system prompt is provided, prepend it as a message with role "system".
    payload_messages = []
    if system_prompt:
        payload_messages.append({"role": "system", "content": system_prompt})
    payload_messages.extend(history)

    payload = {
        "stream": True,
        "anonymize": algorithm != "no_anno",
        "model": model_name,
        "messages": payload_messages,
    }

    external_url = (
        f"{current_app.config['LLM_ROUTER_HOST'].rstrip('/')}/v1/chat/completions"
    )

    try:
        resp = requests.post(external_url, json=payload, timeout=600, stream=True)
        resp.raise_for_status()
    except Exception as exc:
        return (
            Response(
                render_template(
                    "chat_partial.html", chat=f"❌ Chat service error: {exc}"
                ),
                mimetype="text/html",
            ),
            502,
        )

    def generate():
        """
        Generator that parses the LLM-Router's SSE stream and yields text chunks.

        Yields:
            str: A chunk of text from the LLM response.
        """
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            cleaned = line.strip()
            if cleaned.startswith("data:"):
                cleaned = cleaned[5:].lstrip()
            if cleaned == "[DONE]" or not cleaned:
                continue
            try:
                data = json.loads(cleaned)
                chunk = (
                    data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                )
            except:
                chunk = cleaned

            if chunk:
                yield chunk

    return Response(stream_with_context(generate()), mimetype="text/html")


@anonymize_bp.route("/chat/finalize", methods=["POST"])
def chat_finalize():
    """
    Persist the final assistant response in the session.

    This is required when using Flask's default cookie-based session:
    you cannot modify the session after streaming starts because the
    HTTP headers have already been sent to the client.

    Returns:
        A JSON response indicating whether the history was successfully updated.
    """
    try:
        payload = request.get_json(force=True) or {}
    except:
        payload = {}

    assistant_msg = (payload.get("assistant") or "").strip()
    if not assistant_msg:
        return jsonify({"ok": False, "error": "Missing assistant message"}), 400

    history = session.get("chat_history", [])
    history.append({"role": "assistant", "content": assistant_msg})
    session["chat_history"] = history
    session.modified = True
    return jsonify({"ok": True})


@anonymize_bp.route("/chat/import", methods=["POST"])
def import_chat():
    """
    Import chat history from a JSON payload and save it to the session.

    Args:
        JSON payload containing a 'history' list of messages.

    Returns:
        A JSON response indicating success or a specific error if the
        payload format is invalid.
    """
    try:
        data = request.get_json(force=True) or {}
        history = data.get("history")
        if not isinstance(history, list):
            return jsonify({"ok": False, "error": "History must be a list"}), 400
        session["chat_history"] = history
        session.modified = True
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@anonymize_bp.route("/models", methods=["GET"])
def models():
    """
    Retrieve the list of models from the configured external LLM router.

    The handler builds the target URL from the Flask application config
    ``LLM_ROUTER_HOST`` and performs a GET request with a 10‑second timeout.
    If the request succeeds and returns JSON, the function extracts the
    ``models`` list (or falls back to ``data``) and returns it in a JSON
    response with HTTP status 200.  If any exception occurs during the
    request or processing, the endpoint returns an empty ``models`` list
    with HTTP status 500.

    Returns
        Flask response
            JSON object ``{"models": [...]}`` where the value is a list of
            model identifiers.  Status code 200 on success, 500 on failure.

    Raises
        Exception
            Any exception raised while contacting the external service or
            parsing its response results in a 500 response.
    """
    external_url = f"{current_app.config['LLM_ROUTER_HOST'].rstrip('/')}/models"
    try:
        resp = requests.get(external_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models") or data.get("data") or []
        return jsonify({"models": models})
    except Exception:
        return jsonify({"models": []}), 500
