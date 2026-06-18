from __future__ import annotations

import logging

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.training.daily import build_and_persist_daily_training_datasets
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    settings = load_settings(PROJECT_ROOT)
    configure_logging(str(settings.get("logging", {}).get("level", "INFO")))
    logger = logging.getLogger("metro_demand_models.scripts.build_daily_training_dataset")

    manifest = build_and_persist_daily_training_datasets(settings)
    logger.info("Daily training datasets generated: %s", len(manifest["datasets"]))
    for dataset_payload in manifest["datasets"]:
        logger.info(
            "Built %s | rows=%s | series=%s | path=%s",
            dataset_payload["variant"]
            + "/"
            + dataset_payload["series_policy"]
            + f"/h{dataset_payload['horizon_days']}",
            dataset_payload["row_count"],
            dataset_payload["series_count"],
            dataset_payload["dataset_path"],
        )
    logger.info("Feature catalog: %s", manifest["feature_catalog_path"])
    logger.info("Panel diagnostics: %s", manifest["panel_diagnostics_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
