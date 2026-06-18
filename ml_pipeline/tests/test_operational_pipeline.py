from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd

from metro_demand_models.configuration import load_settings
from metro_demand_models.data.operations import build_operational_datasets


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_operational_datasets_from_minimal_workbooks(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    interim_dir = tmp_path / "interim" / "operations"
    processed_dir = tmp_path / "processed" / "operations"
    reports_dir = tmp_path / "validation" / "reports" / "operations"
    raw_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    stations_master_path = tmp_path / "stations_master.parquet"
    pd.DataFrame(
        [
            {
                "linea": "LINEA 1",
                "estacion": "Andalucia Tech",
                "station_abbrev": "TCH",
                "station_join_key": "andalucia tech",
                "station_group": "Andalucia Tech",
                "station_display_name": "Andalucía Tech",
            },
            {
                "linea": "LINEA 2",
                "estacion": "Puerta Blanca",
                "station_abbrev": "PBI",
                "station_join_key": "puerta blanca",
                "station_group": "Puerta Blanca",
                "station_display_name": "Puerta Blanca",
            },
            {
                "linea": "LINEA 2",
                "estacion": "Palacio de los Deportes",
                "station_abbrev": "PDD",
                "station_join_key": "palacio de los deportes",
                "station_group": "Palacio de los Deportes",
                "station_display_name": "Palacio de los Deportes",
            },
            {
                "linea": "LINEA 1",
                "estacion": "Perchel",
                "station_abbrev": "PCH",
                "station_join_key": "perchel",
                "station_group": "Perchel",
                "station_display_name": "El Perchel",
            },
            {
                "linea": "LINEA 2",
                "estacion": "Perchel",
                "station_abbrev": "PCH",
                "station_join_key": "perchel",
                "station_group": "Perchel",
                "station_display_name": "El Perchel",
            },
        ]
    ).to_parquet(stations_master_path, index=False)

    _write_services_workbook(raw_dir / "Servicios Hist Test.xlsx")
    _write_events_workbook(raw_dir / "Calendario_Eventos.xlsx")
    _write_incidents_workbook(raw_dir / "Incidencias_Historico.xlsx")

    settings = deepcopy(load_settings(PROJECT_ROOT))
    settings["resolved_paths"]["raw_data_dir"] = str(raw_dir)
    settings["resolved_paths"]["stations_master_file"] = str(stations_master_path)
    settings["resolved_paths"]["interim_operations_dir"] = str(interim_dir)
    settings["resolved_paths"]["processed_operations_dir"] = str(processed_dir)
    settings["resolved_paths"]["operations_reports_dir"] = str(reports_dir)

    artifacts = build_operational_datasets(settings)

    events_report = pd.read_csv(artifacts.output_paths["events_mapping_report"])
    incidents_normalized = pd.read_parquet(artifacts.output_paths["incidents_normalized"])
    services_line_daily = pd.read_parquet(artifacts.output_paths["services_line_daily"])
    events_station_impact = pd.read_parquet(artifacts.output_paths["events_station_impact"])
    events_phase2a = pd.read_parquet(artifacts.output_paths["events_phase2a_series_daily"])

    assert services_line_daily["linea"].tolist() == ["LINEA 1", "LINEA 2"]
    assert "normalized_text_match_only" in set(events_report["notes"].dropna())
    assert "PBL" in set(events_station_impact["station_abbrev"])
    assert "PBL" in set(incidents_normalized["mapped_station_abbrev"].dropna())
    assert incidents_normalized["impact_scope"].tolist() == ["line", "station"]
    perchel_rows = events_phase2a[events_phase2a["station_join_key"] == "perchel"]
    assert set(perchel_rows["linea"]) == {"LINEA 1", "LINEA 2"}
    assert set(perchel_rows["shared_station_group_propagated"]) == {True}
    assert set(perchel_rows["deduplication_weight"]) == {0.5}
    assert set(perchel_rows["active_event_count_deduplicated"]) == {0.5}
    assert Path(artifacts.output_paths["inspection_summary"]).exists()


def _write_services_workbook(path: Path) -> None:
    services = pd.DataFrame(
        [
            {
                "servicio": "s1",
                "archivo_xml_planificado": "S1_26_V01",
                "archivo_xml_usado": "S1_26_V01",
                "fecha": pd.Timestamp("2026-01-10"),
                "Inicio Serv Comercial": "06:25:00",
                "Fin L1 Serv Comercial": "23:30:00",
                "Fin L2 Serv Comercial": "23:35:00",
                "Descripción Servicio": "Servicio regular",
                "evento": None,
                "Demanda extraordinaria": None,
                "Comentarios": None,
                "Comentarios para ING": None,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        services.to_excel(writer, sheet_name="Resumen_Servicios", index=False)


def _write_events_workbook(path: Path) -> None:
    events = pd.DataFrame(
        [
            {
                "ID": 1,
                "Título": "Concierto nocturno",
                "Categoria": "MÚSICA",
                "Hora Inicio": pd.Timestamp("2026-01-10 22:30:00"),
                "Hora Fin": pd.Timestamp("2026-01-10 00:30:00"),
                "Ubicación": "Inacua Málaga",
                "Aforo": "4.200",
                "Url Detalle Evento": "https://example.com",
                "Comentarios": None,
                "StartDay": "SÁBADO",
                "EndDay": "DOMINGO",
            },
            {
                "ID": 2,
                "Título": "Evento de red",
                "Categoria": "OTROS",
                "Hora Inicio": pd.Timestamp("2026-01-11 10:00:00"),
                "Hora Fin": pd.Timestamp("2026-01-11 13:00:00"),
                "Ubicación": "Metro de Málaga",
                "Aforo": "Por definir",
                "Url Detalle Evento": None,
                "Comentarios": None,
                "StartDay": "DOMINGO",
                "EndDay": "DOMINGO",
            },
            {
                "ID": 3,
                "Título": "Evento en intercambiador",
                "Categoria": "OTROS",
                "Hora Inicio": pd.Timestamp("2026-01-11 11:00:00"),
                "Hora Fin": pd.Timestamp("2026-01-11 12:00:00"),
                "Ubicación": "Perchel",
                "Aforo": "500",
                "Url Detalle Evento": None,
                "Comentarios": None,
                "StartDay": "DOMINGO",
                "EndDay": "DOMINGO",
            },
        ]
    )
    locations = pd.DataFrame(
        [
            {"Ubicaciones": "INACUA Málaga", "TyC": None, "PBL": None, "TCH": None, "PDD": 1},
            {"Ubicaciones": "Metro de Málaga", "TyC": 1, "PBL": 1, "TCH": 1, "PDD": None},
            {"Ubicaciones": "Perchel", "TyC": None, "PBL": None, "TCH": None, "PDD": None, "PCH": 1},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        events.to_excel(writer, sheet_name="Eventos", index=False)
        locations.to_excel(writer, sheet_name="Ubicaciones", index=False)


def _write_incidents_workbook(path: Path) -> None:
    incidents = pd.DataFrame(
        [
            {
                "ID": 10,
                "Tipo Agente": None,
                "Tipo Incidencia": "Afectación Servicio Trenes",
                "Incidencias asociadas": None,
                "Grupo": "INCIDENTES",
                "Subgrupo": "Retrasos",
                "Familia": "Operación",
                "Código": 290,
                "Fecha Origen Inc": pd.Timestamp("2026-01-10"),
                "Hora Inicio": "22:00",
                "Hora Fin": "22:15",
                "Localización": "LÍNEA 2",
                "Sublocalización": "TRAMO PBI-PDD",
                "Tipo Localización": "TÚNEL",
                "Descripción": "Retraso en línea.",
                "Tiempo de retraso (en minutos)": "15:00",
                "Afección al servicio": "RETRASOS",
                "Sistema": "UNIDAD DE TREN",
                "Subsistema": "UT 3001",
            },
            {
                "ID": 11,
                "Tipo Agente": None,
                "Tipo Incidencia": "Afectación Servicio Trenes",
                "Incidencias asociadas": None,
                "Grupo": "INCIDENTES",
                "Subgrupo": "Puerta",
                "Familia": "Operación",
                "Código": 291,
                "Fecha Origen Inc": pd.Timestamp("2026-01-11"),
                "Hora Inicio": "23:05",
                "Hora Fin": "00:05",
                "Localización": "PBL - PUERTA BLANCA",
                "Sublocalización": "ANDEN",
                "Tipo Localización": "ESTACIÓN",
                "Descripción": "Incidencia en andén.",
                "Tiempo de retraso (en minutos)": "01:30",
                "Afección al servicio": "RETRASOS",
                "Sistema": "UNIDAD DE TREN",
                "Subsistema": "UT 3002",
            },
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        incidents.to_excel(writer, sheet_name="Incidencias", index=False)
