from __future__ import annotations

from typing import Any

import pandas as pd


DEFAULT_SHARED_STATION_ABBREVIATIONS = {"GDL", "PCH"}
DEFAULT_STATION_ABBREVIATION_ALIASES = {
    "PBI": "PBL",
}


def normalize_station_abbrev(
    value: Any,
    *,
    aliases: dict[str, str] | None = None,
) -> str:
    text = str(value or "").strip().upper()
    lookup = {
        **DEFAULT_STATION_ABBREVIATION_ALIASES,
        **{str(key).upper(): str(target).upper() for key, target in (aliases or {}).items()},
    }
    return lookup.get(text, text)


def fallback_station_abbrev(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", " ")
    tokens = [token for token in text.split() if token]
    if not tokens:
        return "UNK"
    if len(tokens) == 1:
        return tokens[0][:4]
    return "".join(token[0] for token in tokens[:4])


def infer_shared_station_abbreviations(stations: pd.DataFrame) -> set[str]:
    if stations.empty or not {"station_abbrev", "linea"}.issubset(stations.columns):
        return set(DEFAULT_SHARED_STATION_ABBREVIATIONS)

    working = stations[["station_abbrev", "linea"]].dropna().copy()
    working["station_abbrev"] = working["station_abbrev"].map(normalize_station_abbrev)
    shared = working.groupby("station_abbrev")["linea"].nunique().loc[lambda counts: counts > 1].index
    return set(DEFAULT_SHARED_STATION_ABBREVIATIONS).union(set(shared))


def build_station_series_label(
    *,
    linea: Any,
    station_abbrev: Any,
    shared_station_abbreviations: set[str] | None = None,
) -> str:
    normalized_abbrev = normalize_station_abbrev(station_abbrev)
    line_suffix = "".join(character for character in str(linea) if character.isdigit())
    shared_abbreviations = shared_station_abbreviations or DEFAULT_SHARED_STATION_ABBREVIATIONS
    if normalized_abbrev in shared_abbreviations and line_suffix:
        return f"{normalized_abbrev}{line_suffix}"
    return normalized_abbrev
