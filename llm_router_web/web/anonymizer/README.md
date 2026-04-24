# llm_router_web.anonymizer

**llm_router_web: anonymizer** is a Flask web interface providing tools for text anonymization and private interaction
with LLMs. It acts as a bridge between the user and the backend anonymization services (PII Service and LLM-Router).

**llm_router_web.anonymizer** is the web interface component of the
[llm-router](https://github.com/radlab-dev-group/llm-router) library.

## Features

### 🔒 Text Anonymization Form

- **Multi-Algorithm Support**:
    - `Fast Masking`: Quick placeholder replacement via LLM-Router.
    - `PII Masking`: Specialized Personally Identifiable Information detection (Location, Person).
    - `Fast + PII`: Hybrid approach applying PII masking followed by Fast Masking.
- **Advanced UI**:
    - Real-time result highlighting of `{{TAGS}}`.
    - One-click copying of both the anonymized text and the mapping JSON.
    - Synchronized scrolling between input and result panes.
- **HTMX-powered**: Asynchronous processing without full page reloads.

### 💬 Interactive Anonymized Chat

- **Streaming Responses**: Real-time text generation from the LLM.
- **Privacy Control**: Toggle anonymization on/off per message.
- **Session Management**:
    - Server-side session history.
    - Local browser storage for persistent chat lists.
    - Ability to import/export chat history as JSON.
- **AI Customization**:
    - Dynamic model selection (fetched from the Router's `/models` endpoint).
    - Custom System Prompts to define AI personality.
    - Quick Prompts modal for common tasks (Summarize, Fix Grammar, etc.).
- **UX Enhancements**: Markdown rendering, response regeneration, and keyboard shortcuts (Ctrl+Enter, Ctrl+L, etc.).

## Installation

The project uses **Python 3.11** with **virtualenv**.

```shell script
# Clone the repository
git clone https://github.com/radlab-dev-group/llm-router.git
cd llm-router/llm_router_web

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Application

### Development server

```shell script
python -m web.anonymizer
```

The UI is reachable at `http://localhost:5000/anonymize`.

### Production (Gunicorn)

```shell script
LLM_ROUTER_HOST=http://localhost:8000 \
PII_SERVICE_HOST=http://localhost:5001 \
gunicorn -w 4 -b 0.0.0.0:8082 "web.anonymizer:create_anonymize_app()"
```

## Configuration

Configuration is managed via environment variables:

| Variable                               | Description                               | Default                   |
|:---------------------------------------|:------------------------------------------|:--------------------------|
| `FLASK_SECRET_KEY`                     | Secret key for Flask session signing      | `change-me-anonymizer`    |
| `LLM_ROUTER_HOST`                      | Base URL of the LLM-Router service        | `http://localhost:8000`   |
| `PII_SERVICE_HOST`                     | Base URL of the PII anonymization service | `http://localhost:5001`   |
| `LLM_ROUTER_GENAI_MODEL_ANONYMISATION` | Model used for GenAI masking              | (defined in constants.py) |

## Endpoints Overview

All endpoints are prefixed with `/anonymize`.

| URL              | Methods | Description                                                                              |
|:-----------------|:--------|:-----------------------------------------------------------------------------------------|
| `/`              | GET     | Renders the anonymization form.                                                          |
| `/`              | POST    | Processes text based on selected algorithm (`fast`, `pii_masking`, `fast+pii`, `genai`). |
| `/chat`          | GET     | Renders the interactive chat interface.                                                  |
| `/chat/message`  | POST    | Sends a message, handles anonymization, and streams the LLM response.                    |
| `/chat/finalize` | POST    | Saves the final assistant response to the session history.                               |
| `/chat/import`   | POST    | Imports a JSON chat history into the current session.                                    |
| `/models`        | GET     | Proxy to LLM-Router to list available models.                                            |

## Development

### Project layout

```
web/
└─ anonymizer/
   ├─ templates/
   │   ├─ anonymize.html           # Main form page
   │   ├─ chat.html                # Interactive chat interface
   │   ├─ base.html                # Shared layout (Theme support)
   │   └─ anonymize_result_partial.html 
   ├─ __init__.py                  # Flask app factory
   ├─ routes.py                    # Blueprint and logic
   └─ constants.py                 # Default model names and config
```

### Adding new features

1. **New routes** – Define them in `routes.py` and register on `anonymize_bp`.
2. **Templates** – Place additional Jinja2 files in `templates/` and extend `base_anonymizer.html`.
3. **Static assets** – Add CSS/JS to the main `static/` directory; they are automatically served because the Flask app
   points to the parent static folder.
4. **Configuration** – Extend `create_anonymize_app()` to read extra environment variables as needed.

## License

`llm_router_web.anonymizer` is part of the **llm-router** project and is released under the same license
as the parent repository. See the repository’s `LICENSE` file for details.
