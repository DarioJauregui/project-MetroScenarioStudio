from __future__ import annotations

import logging

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.inference.daily import (
    run_daily_inference_smoke,
    save_daily_inference_smoke_outputs,
)
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    settings = load_settings(PROJECT_ROOT)
    configure_logging(str(settings.get("logging", {}).get("level", "INFO")))
    logger = logging.getLogger("metro_demand_models.scripts.run_daily_inference_smoke")

    predictions = run_daily_inference_smoke(settings)
    output_paths = save_daily_inference_smoke_outputs(settings, predictions)
    logger.info("Smoke inference rows: %s", len(predictions))
    for name, path in output_paths.items():
        logger.info("%s: %s", name, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
