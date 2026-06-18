from __future__ import annotations

import copy
import csv
from functools import lru_cache
from typing import TYPE_CHECKING, Any

FALLBACK_STATIONS: list[dict[str, Any]] = [
    {"linea": "LINEA 1", "estacion": "Atarazanas", "series_id": "ATZ", "station_abbrev": "ATZ", "network_order": 1},
    {"linea": "LINEA 1", "estacion": "Guadalmedina", "series_id": "GDL1", "station_abbrev": "GDL", "network_order": 2},
    {"linea": "LINEA 1", "estacion": "El Perchel", "series_id": "PCH1", "station_abbrev": "PCH", "network_order": 3},
    {"linea": "LINEA 1", "estacion": "La Union", "series_id": "LUN", "station_abbrev": "LUN", "network_order": 4},
    {"linea": "LINEA 1", "estacion": "Barbarela", "series_id": "BBL", "station_abbrev": "BBL", "network_order": 5},
    {"linea": "LINEA 1", "estacion": "Carranque", "series_id": "CRR", "station_abbrev": "CRR", "network_order": 6},
    {"linea": "LINEA 1", "estacion": "Portada Alta", "series_id": "PTA", "station_abbrev": "PTA", "network_order": 7},
    {
        "linea": "LINEA 1",
        "estacion": "Ciudad de la Justicia",
        "series_id": "CDJ",
        "station_abbrev": "CDJ",
        "network_order": 8,
    },
    {"linea": "LINEA 1", "estacion": "Universidad", "series_id": "UNI", "station_abbrev": "UNI", "network_order": 9},
    {"linea": "LINEA 1", "estacion": "Clinico", "series_id": "CLI", "station_abbrev": "CLI", "network_order": 10},
    {"linea": "LINEA 1", "estacion": "El Consul", "series_id": "CNS", "station_abbrev": "CNS", "network_order": 11},
    {"linea": "LINEA 1", "estacion": "Paraninfo", "series_id": "PAR", "station_abbrev": "PAR", "network_order": 12},
    {
        "linea": "LINEA 1",
        "estacion": "Andalucia Tech",
        "series_id": "ATC",
        "station_abbrev": "ATC",
        "network_order": 13,
    },
    {"linea": "LINEA 2", "estacion": "Guadalmedina", "series_id": "GDL2", "station_abbrev": "GDL", "network_order": 20},
    {"linea": "LINEA 2", "estacion": "El Perchel", "series_id": "PCH2", "station_abbrev": "PCH", "network_order": 21},
    {"linea": "LINEA 2", "estacion": "La Isla", "series_id": "ISL", "station_abbrev": "ISL", "network_order": 22},
    {"linea": "LINEA 2", "estacion": "Princesa", "series_id": "PRI", "station_abbrev": "PRI", "network_order": 23},
    {"linea": "LINEA 2", "estacion": "El Torcal", "series_id": "TRC", "station_abbrev": "TRC", "network_order": 24},
    {"linea": "LINEA 2", "estacion": "La Luz-La Paz", "series_id": "LZP", "station_abbrev": "LZP", "network_order": 25},
    {"linea": "LINEA 2", "estacion": "Puerta Blanca", "series_id": "PBL", "station_abbrev": "PBL", "network_order": 26},
    {
        "linea": "LINEA 2",
        "estacion": "Palacio de los Deportes",
        "series_id": "PLD",
        "station_abbrev": "PLD",
        "network_order": 27,
    },
]


if TYPE_CHECKING:
    from pathlib import Path


@lru_cache(maxsize=16)
def _load_station_catalog_cached(models_root: Path) -> list[dict[str, Any]]:
    csv_path = models_root / "artifacts" / "daily_modeling" / "future_forecasts" / "future_forecast_series.csv"
    if csv_path.exists():
        return _load_from_future_forecast(csv_path)
    return FALLBACK_STATIONS


def load_station_catalog(models_root: Path) -> list[dict[str, Any]]:
    return copy.deepcopy(_load_station_catalog_cached(models_root))


def _load_from_future_forecast(path: Path) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            if not row.get("series_id") or row["series_id"] in seen:
                continue
            if row.get("model_variant") == "baseline_simple":
                continue
            seen[row["series_id"]] = {
                "linea": row.get("linea") or "",
                "estacion": row.get("estacion") or row.get("series_label") or "",
                "series_id": row["series_id"],
                "station_abbrev": row.get("station_abbrev") or row.get("series_label") or row["series_id"],
                "network_order": int(float(row.get("network_order") or len(seen) + 1)),
            }
    return sorted(seen.values(), key=lambda item: (item["network_order"], item["series_id"])) or FALLBACK_STATIONS
