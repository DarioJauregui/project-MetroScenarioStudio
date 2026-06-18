from __future__ import annotations

from _bootstrap import bootstrap_src_path


PROJECT_ROOT = bootstrap_src_path()

from metro_demand_models.utils.environment import main


if __name__ == "__main__":
    raise SystemExit(main(PROJECT_ROOT))
