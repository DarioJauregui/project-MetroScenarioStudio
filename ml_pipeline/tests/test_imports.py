from __future__ import annotations

import importlib


MODULES = [
    "metro_demand_models",
    "metro_demand_models.configuration",
    "metro_demand_models.data",
    "metro_demand_models.data.contracts",
    "metro_demand_models.data.inspection",
    "metro_demand_models.data.io",
    "metro_demand_models.data.modeling",
    "metro_demand_models.data.operations",
    "metro_demand_models.data.operations.common",
    "metro_demand_models.data.operations.events",
    "metro_demand_models.data.operations.incidents",
    "metro_demand_models.data.operations.pipeline",
    "metro_demand_models.data.operations.services",
    "metro_demand_models.data.validation",
    "metro_demand_models.features",
    "metro_demand_models.features.daily",
    "metro_demand_models.models",
    "metro_demand_models.models.baselines",
    "metro_demand_models.models.tabular",
    "metro_demand_models.training",
    "metro_demand_models.training.daily",
    "metro_demand_models.evaluation",
    "metro_demand_models.evaluation.daily",
    "metro_demand_models.evaluation.supervision",
    "metro_demand_models.inference",
    "metro_demand_models.inference.daily",
    "metro_demand_models.deployment",
    "metro_demand_models.utils",
    "metro_demand_models.utils.environment",
    "metro_demand_models.utils.logging",
    "metro_demand_models.utils.stations",
    "metro_demand_models.utils.tracking",
]


def test_core_modules_import() -> None:
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        assert module is not None
