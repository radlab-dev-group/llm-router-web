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
import requests

from flask import (
    Blueprint,
    current_app,
    request,
    render_template,
    jsonify,
    Response,
    stream_with_context,
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
    endpoint_map = {
        "fast": "/api/fast_text_mask",
        "genai": "/api/anonymize_text_genai",
        "priv": "/api/anonymize_text_priv_masker",
    }
    model_name = request.form.get("model_name", "").strip()

    if algorithm == "genai" and not GENAI_MODEL_ANON:
        return render_template(
            "anonymize_result_partial.html",
            api_host=current_app.config["LLM_ROUTER_HOST"],
            result={"error": "genai model is not set"},
        )
    if algorithm == "priv":
        return render_template(
            "anonymize_result_partial.html",
            api_host=current_app.config["LLM_ROUTER_HOST"],
            result={"error": "priv_masker is not available yet"},
        )
    if algorithm not in endpoint_map:
        return render_template(
            "anonymize_result_partial.html",
            api_host=current_app.config["LLM_ROUTER_HOST"],
            result={
                "error": f"Not supported method {algorithm}.\nSupported: [fast, genai, priv]"
            },
        )

    endpoint = endpoint_map[algorithm]
    external_url = f"{current_app.config['LLM_ROUTER_HOST'].rstrip('/')}{endpoint}"

    try:
        resp = requests.post(
            external_url,
            json={"text": raw_text, "model_name": model_name or "gpt-oss:120b"},
            timeout=600,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"❌ Connection error with the anonymization service: {exc}", 502

    try:
        data = resp.json()
        result = data.get("text", resp.text)
    except ValueError:
        result = resp.text

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

    algorithm = request.form.get("algorithm", "fast")
    model_name = request.form.get("model_name", "").strip()

    payload = {
        "stream": True,  # <--- enable streaming
        "anonymize": algorithm != "no_anno",
        "model": model_name or "google/gemma-3-12b-it",
        "messages": [{"role": "user", "content": user_msg}],
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
            # Render a simple error block – it will be streamed as a single chunk
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

        # --------------------------------------------------------------
        # Stream the response back to the browser as plain HTML chunks.
        # Each chunk is rendered with ``chat_partial.html``.
        # --------------------------------------------------------------

        # --------------------------------------------------------------
        # Strumieniowanie odpowiedzi – zwracamy **tylko** tekst (bez HTML)
        # --------------------------------------------------------------

    def generate():
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            # Usuwamy prefiks „data:” typowy dla SSE
            cleaned = line.strip()
            if cleaned.startswith("data:"):
                cleaned = cleaned[5:].lstrip()

            # Ignorujemy końcowy znacznik „[DONE]”
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
                # Gdyby nie był to JSON – traktujemy całą linię jako tekst
                chunk = cleaned

            if chunk:
                # Zwracamy sam tekst – klient dokleja go do jednego <pre>
                yield chunk

    return Response(stream_with_context(generate()), mimetype="text/html")


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
        # Return an empty list with a 500 status so the client can handle it.
        current_app.logger.error(f"Failed to fetch models: {exc}")
        return jsonify({"models": []}), 500

    try:
        data = resp.json()
    except ValueError:
        # Non‑JSON response – treat as empty list.
        current_app.logger.error("Models endpoint returned non‑JSON.")
        return jsonify({"models": []}), 500

    # The router may return either {"data": [...]} or {"models": [...]}
    models = data.get("models") or data.get("data") or []
    return jsonify({"models": models})
