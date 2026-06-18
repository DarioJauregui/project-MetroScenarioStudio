from __future__ import annotations

from typing import TYPE_CHECKING

from metro_scenario_studio.domain.schemas import AggregateRow, PredictionRow

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date


def aggregate_prediction_rows(rows: list[PredictionRow]) -> list[AggregateRow]:
    aggregates: list[AggregateRow] = []
    aggregates.append(_aggregate(rows, level="network", target_date=None))
    aggregates.extend(
        _aggregate(
            [row for row in rows if row.linea == linea],
            level="line",
            linea=linea,
        )
        for linea in sorted({row.linea for row in rows})
    )
    aggregates.extend(
        _aggregate(
            [row for row in rows if row.target_date == target_date],
            level="network_date",
            target_date=target_date,
        )
        for target_date in sorted({row.target_date for row in rows})
    )
    aggregates.extend(
        _aggregate(
            [row for row in rows if row.linea == linea and row.target_date == target_date],
            level="line_date",
            target_date=target_date,
            linea=linea,
        )
        for target_date in sorted({row.target_date for row in rows})
        for linea in sorted({row.linea for row in rows})
        if any(row.linea == linea and row.target_date == target_date for row in rows)
    )
    aggregates.extend(
        _aggregate(
            [row for row in rows if row.estacion == estacion],
            level="station",
            estacion=estacion,
        )
        for estacion in sorted({row.estacion for row in rows})
    )
    return aggregates


def _aggregate(
    rows: Iterable[PredictionRow],
    *,
    level: str,
    target_date: date | None = None,
    linea: str | None = None,
    estacion: str | None = None,
) -> AggregateRow:
    row_list = list(rows)
    y_pred = round(sum(row.y_pred for row in row_list), 6)
    real_values = [row.y_real for row in row_list if row.y_real is not None]
    y_real = round(sum(real_values), 6) if real_values else None
    abs_error = None
    pct_error = None
    if y_real is not None:
        abs_error = round(abs(y_pred - y_real), 6)
        pct_error = round(abs_error / y_real, 12) if y_real != 0 else None

    return AggregateRow(
        level=level,
        target_date=target_date,
        linea=linea,
        estacion=estacion,
        y_pred=y_pred,
        y_real=y_real,
        real_available=y_real is not None,
        abs_error=abs_error,
        pct_error=pct_error,
    )
