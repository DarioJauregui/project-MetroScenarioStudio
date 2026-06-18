from __future__ import annotations

import argparse
import subprocess
import sys

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.utils.tracking import build_tracking_uri


def main() -> int:
    parser = argparse.ArgumentParser(description="Start a local MLflow UI instance.")
    parser.add_argument("--host", help="Host for the local MLflow UI.")
    parser.add_argument("--port", type=int, help="Port for the local MLflow UI.")
    args = parser.parse_args()

    settings = load_settings(PROJECT_ROOT)
    mlflow_settings = settings.get("mlflow", {})
    host = args.host or str(mlflow_settings.get("ui_host", "127.0.0.1"))
    port = args.port or int(mlflow_settings.get("ui_port", 5000))
    tracking_uri = build_tracking_uri(settings)

    command = [
        sys.executable,
        "-m",
        "mlflow",
        "ui",
        "--backend-store-uri",
        tracking_uri,
        "--host",
        host,
        "--port",
        str(port),
    ]

    print(f"Starting MLflow UI at http://{host}:{port}")
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
