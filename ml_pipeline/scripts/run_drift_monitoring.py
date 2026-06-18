from __future__ import annotations

import logging
from _bootstrap import PROJECT_ROOT, bootstrap_src_path

bootstrap_src_path()

from metro_demand_models.monitoring.drift_detection import run_drift_monitoring
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    configure_logging("INFO")
    logger = logging.getLogger("metro_demand_models.scripts.run_drift_monitoring")

    logger.info("Initializing daily model drift monitoring...")
    try:
        run_drift_monitoring(PROJECT_ROOT)
        logger.info("Drift monitoring complete. Report saved.")
        return 0
    except Exception as e:
        logger.error("Failed to run drift monitoring: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
