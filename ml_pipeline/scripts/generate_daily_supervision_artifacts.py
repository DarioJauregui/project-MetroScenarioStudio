from __future__ import annotations

import logging

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.evaluation.supervision import (
    generate_daily_supervision_artifacts,
)
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    settings = load_settings(PROJECT_ROOT)
    configure_logging(str(settings.get("logging", {}).get("level", "INFO")))
    logger = logging.getLogger("metro_demand_models.scripts.generate_daily_supervision_artifacts")

    outputs = generate_daily_supervision_artifacts(settings)
    for name, path in outputs.items():
        logger.info("%s: %s", name, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
