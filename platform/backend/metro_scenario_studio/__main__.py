from __future__ import annotations

import uvicorn

from metro_scenario_studio.api.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
