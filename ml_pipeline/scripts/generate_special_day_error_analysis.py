from __future__ import annotations

import logging

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.evaluation.special_days import (
    generate_special_day_error_analysis,
)
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    settings = load_settings(PROJECT_ROOT)
    configure_logging(str(settings.get("logging", {}).get("level", "INFO")))
    logger = logging.getLogger("metro_demand_models.scripts.generate_special_day_error_analysis")

    outputs = generate_special_day_error_analysis(settings)
    for name, path in outputs.items():
        logger.info("%s: %s", name, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
