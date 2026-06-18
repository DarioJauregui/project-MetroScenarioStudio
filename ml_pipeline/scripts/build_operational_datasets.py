from __future__ import annotations

import json

from _bootstrap import bootstrap_src_path


PROJECT_ROOT = bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.data.operations import build_operational_datasets


def main() -> None:
    settings = load_settings(PROJECT_ROOT)
    artifacts = build_operational_datasets(settings)
    print(json.dumps(artifacts.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
