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
)

from .constants import GENAI_MODEL_ANON, DEFAULT_PII_MODEL_NAME

# Blueprint configuration
anonymize_bp = Blueprint(
    "anonymize_web",
    __name__,
    url_prefix="/anonymize",  # http://HOST:PORT/anonymize
    template_folder="../templates",  # templates in web/anonymize/templates
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
            data = resp.json()
            return data
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
            data = resp.json()
            return data
        except Exception as e:
            return f"❌ Router Service Error: {e}"

    # Logic for the selected algorithm
    if algorithm == "pii_masking":
        result = call_pii_service(raw_text, model_name)

        print(result)
        print(result)
        print(result)

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

    _p_map = {}
    for _k, _v in result.get("mappings", {}).items():
        if not _k.startswith("{"):
            _k = "{" + _k + "}"
        _p_map[_k] = _v
    result["mappings"] = _p_map

    # print(json.dumps(result, indent=2, ensure_ascii=False))
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
    """
    Render the dedicated chat interface page.

    Returns:
        The rendered 'chat.html' template.
    """
    return render_template(
        "chat.html",
        api_host=current_app.config["LLM_ROUTER_HOST"],
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
                .get("message", f"LLM-Router returned {resp.status_code}")
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
    Persist the final assistant response in the session.

    This is required when using Flask's default cookie-based session:
    you cannot modify the session after streaming starts because the
    HTTP headers have already been sent to the client.

    Returns:
        A JSON response indicating whether the history was successfully updated.
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

        # Basic validation of message structure
        for msg in history:
            if (
                not isinstance(msg, dict)
                or "role" not in msg
                or "content" not in msg
            ):
                return jsonify({"ok": False, "error": "Invalid message format"}), 400

        session["chat_history"] = history
        session.modified = True
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------------------------
# Model catalogue – proxy to the router’s `/models` endpoint
# ----------------------------------------------------------------------
@anonymize_bp.route("/models", methods=["GET"])
def models():
    """
    Retrieve the list of available models from the external LLM-Router.

    The frontend calls this endpoint (e.g. via `fetch`) to dynamically
    populate the model selection dropdown menus.

    Returns:
        A JSON response containing the list of available model names.
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
        current_app.logger.error("Models endpoint returned non-JSON.")
        return jsonify({"models": []}), 500

    models = data.get("models") or data.get("data") or []
    return jsonify({"models": models})
