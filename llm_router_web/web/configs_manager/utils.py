import io
import json
import requests

from flask import send_file
from datetime import datetime
from sqlalchemy import func, inspect, text

from .models import db, Config, ConfigVersion, Model, Family


def to_json(config_id: int) -> dict:
    """Serialize a configuration to a JSON‑compatible dict."""
    cfg = Config.query.get_or_404(config_id)

    # Discover all families from the Family table (one source of truth)
    families = [f.name for f in Family.query.filter_by(config_id=cfg.id).order_by(Family.name)]
    if not families:
        return {"active_models": {}}

    out = {}
    active_models = {fam: [] for fam in families}
    out["active_models"] = active_models

    # Group models by family name
    for fam_name in families:
        fam_obj = next((f for f in cfg.families if f.name == fam_name), None)
        if not fam_obj:
            continue
        out[fam_name] = {}
        for m in fam_obj.models:
            providers = []
            for p in m.providers:
                if p.enabled:
                    providers.append(
                        {
                            "id": p.provider_id,
                            "api_host": p.api_host,
                            "api_token": p.api_token,
                            "api_type": p.api_type,
                            "input_size": p.input_size,
                            "model_path": p.model_path,
                            **(
                                {"weight": p.weight}
                                if p.api_type == "vllm" or p.weight != 1.0
                                else {}
                            ),
                        }
                    )
            out[fam_name][m.name] = {"providers": providers}

            # Collect active models by their is_active flag
            if m.is_active:
                active_models[fam_name].append(m.name)

    return out


def snapshot_version(config_id: int, note: str = ""):
    """Create a snapshot of the current config state as a new ConfigVersion."""
    payload = to_json(config_id)
    last = (
        db.session.query(func.max(ConfigVersion.version))
        .filter_by(config_id=config_id)
        .scalar()
        or 0
    )
    v = ConfigVersion(
        config_id=config_id,
        version=last + 1,
        note=note,
        json_blob=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    db.session.add(v)

    cfg = Config.query.get(config_id)
    if cfg:
        cfg.updated_at = datetime.utcnow()
        db.session.add(cfg)

    db.session.commit()


def export_config_to_file(config_id: int):
    """Utility used by the export endpoint – returns a Flask file response."""
    payload = to_json(config_id)
    buf = io.BytesIO(
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    )
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name="models-config.json",
    )


# ---- Discovery Logic (inspired by llm-router CLI) --------------------

PROVIDER_DEFINITIONS = [
    {
        "api_type": "ollama",
        "ports": [11434, 18765],
        "health_path": "/",
        "models_path": "/api/tags",
        "fetch_type": "ollama",
    },
    {
        "api_type": "vllm",
        "ports": [8000, 7000],
        "health_path": "/health",
        "models_path": "/v1/models",
        "fetch_type": "openai_style",
    },
    {
        "api_type": "lmstudio",
        "ports": [1234, 1235],
        "health_path": "/",
        "models_path": "/v1/models",
        "fetch_type": "openai_style",
    },
    {
        "api_type": "llamacpp",
        "ports": [8080],
        "health_path": "/health",
        "models_path": "/v1/models",
        "fetch_type": "openai_style",
    },
    {
        "api_type": "koboldcpp",
        "ports": [5001],
        "health_path": "/",
        "models_path": "/api/v1/models",
        "fetch_type": "openai_style",
    },
    {
        "api_type": "tabbyapi",
        "ports": [8080],
        "health_path": "/health",
        "models_path": "/v1/models",
        "fetch_type": "openai_style",
    },
]


def discover_host(host: str, timeout: float = 1.0):
    """
    Scan a host for local LLM providers and return found models.
    """
    results = []
    for prov in PROVIDER_DEFINITIONS:
        for port in prov["ports"]:
            api_type = prov["api_type"]
            health_url = f"http://{host}:{port}{prov['health_path']}"
            try:
                resp = requests.get(health_url, timeout=timeout)
                if resp.status_code >= 500:
                    continue

                models_url = f"http://{host}:{port}{prov['models_path']}"
                models_resp = requests.get(models_url, timeout=2.0)
                models_resp.raise_for_status()
                data = models_resp.json()

                found_models = []
                if prov["fetch_type"] == "ollama":
                    for m in data.get("models", []):
                        found_models.append(m["name"])
                else:
                    for m in data.get("data", []):
                        found_models.append(m["id"])

                if found_models:
                    results.append(
                        {
                            "api_type": api_type,
                            "host": host,
                            "port": port,
                            "models": found_models,
                        }
                    )
            except Exception:
                continue
    return results


def _ensure_provider_order_column():
    """
    SQLite does not support automatic migrations. When the code first runs
    against an existing DB the ``order`` column may be missing – this adds it
    if required.
    """
    engine = db.get_engine()
    inspector = inspect(engine)

    # ----------------------------------------------------------------------
    # If the ``provider`` table does not exist yet (first start‑up), simply
    # return – ``db.create_all()`` will create the whole schema later.
    # ----------------------------------------------------------------------
    if not inspector.has_table("provider"):
        return

    current_columns = [c["name"] for c in inspector.get_columns("provider")]
    if "order" not in current_columns:
        with engine.connect() as conn:
            conn.execute(
                text(
                    'ALTER TABLE provider ADD COLUMN "order" INTEGER NOT NULL DEFAULT 0'
                )
            )
        # Refresh SQLAlchemy's metadata so the new column is recognised.
        db.metadata.clear()
        db.metadata.reflect(bind=engine)
