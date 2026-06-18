from __future__ import annotations

from pathlib import Path

from metro_demand_models.configuration import Settings, get_path


def ensure_tracking_directory(settings: Settings) -> Path:
    tracking_directory = get_path(settings, "mlruns_dir")
    tracking_directory.mkdir(parents=True, exist_ok=True)
    return tracking_directory


def build_tracking_uri(settings: Settings) -> str:
    configured_uri = str(settings.get("mlflow", {}).get("tracking_uri", "")).strip()
    if configured_uri:
        return configured_uri

    return ensure_tracking_directory(settings).resolve().as_uri()


def configure_mlflow_tracking(settings: Settings) -> str:
    import mlflow

    tracking_uri = build_tracking_uri(settings)
    mlflow.set_tracking_uri(tracking_uri)
    return tracking_uri
