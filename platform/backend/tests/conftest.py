from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metro_scenario_studio.api.main import create_app
from metro_scenario_studio.core.config import Settings


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )


@pytest.fixture
def client(test_settings) -> TestClient:
    return TestClient(create_app(test_settings))
