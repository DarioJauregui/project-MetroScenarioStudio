import { useMemo, useState } from "react";
import { Bar, Line } from "react-chartjs-2";
import { X } from "lucide-react";

import type { ChartData } from "chart.js";
import type { PredictionRow, ScenarioComparisonRow, TemporalRow, TimeGrouping, ZoomMode } from "../../types";
import { weekdayFromLabel } from "../../utils/formatters";
import { ChartLegend } from "../charts/ChartLegend";
import { MultiCheckDropdown } from "../common/MultiCheckDropdown";

const weekdayOptions = [
  { value: 1, label: "L" },
  { value: 2, label: "M" },
  { value: 3, label: "X" },
  { value: 4, label: "J" },
  { value: 5, label: "V" },
  { value: 6, label: "S" },
  { value: 0, label: "D" },
];

const lineOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: "bottom" as const } },
};

const barOptions = {
  indexAxis: "y" as const,
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: "bottom" as const } },
};

export function ChartAnalysisModal(props: {
  chart: "temporal" | "ranking";
  temporalRows: TemporalRow[];
  timeGrouping: TimeGrouping;
  onTimeGroupingChange: (grouping: TimeGrouping) => void;
  showReal: boolean;
  onShowRealChange: (value: boolean) => void;
  hasRealData: boolean;
  comparisonRows: ScenarioComparisonRow[];
  stationRanking: PredictionRow[];
  stationComparison: ScenarioComparisonRow[];
  onClose: () => void;
  temporalChartData: (
    rows: TemporalRow[],
    comparisonRows: ScenarioComparisonRow[],
    showReal: boolean
  ) => ChartData<"line", (number | null)[], string>;
  rankingChartData: (
    rows: PredictionRow[],
    comparisonRows: ScenarioComparisonRow[]
  ) => ChartData<"bar", (number | null)[], string>;
  predictionRows: PredictionRow[];
  basePredictionRows?: PredictionRow[];
}) {
  const isTemporal = props.chart === "temporal";
  const [selectedWeekdays, setSelectedWeekdays] = useState<number[]>([1, 2, 3, 4, 5, 6, 0]);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [detailDensity, setDetailDensity] = useState<ZoomMode>("normal");

  const visibleTemporalRows = useMemo(() => {
    if (!isTemporal || props.timeGrouping !== "day") return props.temporalRows;
    return props.temporalRows.filter((row) => selectedWeekdays.includes(weekdayFromLabel(row.label)));
  }, [isTemporal, props.temporalRows, props.timeGrouping, selectedWeekdays]);

  const allDates = useMemo(() => {
    const dates = [...new Set(props.predictionRows.map((row) => row.target_date))];
    return dates.sort();
  }, [props.predictionRows]);

  const dateOptions = useMemo(() => {
    return allDates.map((d) => ({ value: d, label: d }));
  }, [allDates]);

  const filteredPredictionRows = useMemo(() => {
    return props.predictionRows.filter((row) => {
      if (selectedDates.length > 0 && !selectedDates.includes(row.target_date)) return false;
      const wd = weekdayFromLabel(row.target_date);
      return selectedWeekdays.includes(wd);
    });
  }, [props.predictionRows, selectedDates, selectedWeekdays]);

  const modalStationRanking = useMemo(() => {
    const byStation = new Map<string, PredictionRow>();
    for (const row of filteredPredictionRows) {
      const key = row.estacion;
      const current = byStation.get(key);
      if (!current) {
        byStation.set(key, { ...row });
        continue;
      }
      byStation.set(key, {
        ...current,
        y_pred: current.y_pred + row.y_pred,
        y_real:
          current.y_real !== null && current.y_real !== undefined && row.y_real !== null && row.y_real !== undefined
            ? current.y_real + row.y_real
            : current.y_real ?? row.y_real ?? null,
      });
    }
    return [...byStation.values()].sort((a, b) => b.y_pred - a.y_pred);
  }, [filteredPredictionRows]);

  const filteredBasePredictionRows = useMemo(() => {
    if (!props.basePredictionRows) return [];
    return props.basePredictionRows.filter((row) => {
      if (selectedDates.length > 0 && !selectedDates.includes(row.target_date)) return false;
      const wd = weekdayFromLabel(row.target_date);
      return selectedWeekdays.includes(wd);
    });
  }, [props.basePredictionRows, selectedDates, selectedWeekdays]);

  const modalStationComparison = useMemo(() => {
    if (!props.basePredictionRows || props.basePredictionRows.length === 0) return [];
    const baseByStation = new Map<string, number>();
    for (const row of filteredBasePredictionRows) {
      const key = row.estacion;
      const current = baseByStation.get(key) ?? 0;
      baseByStation.set(key, current + row.y_pred);
    }
    return [...baseByStation.entries()].map(([estacion, base_y_pred]) => ({
      level: "station",
      estacion,
      base_y_pred,
    })) as ScenarioComparisonRow[];
  }, [filteredBasePredictionRows, props.basePredictionRows]);

  function toggleWeekday(value: number) {
    setSelectedWeekdays((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
    );
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <section className="modal analysis-modal">
        <div className="section-heading">
          <div>
            <h2>{isTemporal ? "Analisis de evolucion temporal" : "Analisis de ranking de estaciones"}</h2>
            <p className="muted">Vista ampliada para revisar valores, series y desplazamiento con mas comodidad.</p>
          </div>
          <button type="button" className="icon-button" onClick={props.onClose} title="Cerrar">
            <X size={18} />
          </button>
        </div>
        <div className="analysis-controls">
          {isTemporal ? (
            <>
              <span>Agrupar por</span>
              <button
                type="button"
                className={props.timeGrouping === "day" ? "chip active" : "chip"}
                onClick={() => props.onTimeGroupingChange("day")}
              >
                Dia
              </button>
              <button
                type="button"
                className={props.timeGrouping === "week" ? "chip active" : "chip"}
                onClick={() => props.onTimeGroupingChange("week")}
              >
                Semana
              </button>
              <label className="switch-row">
                <input
                  type="checkbox"
                  checked={props.showReal}
                  disabled={!props.hasRealData}
                  onChange={(event) => props.onShowRealChange(event.target.checked)}
                />
                Mostrar viajeros reales
              </label>
              <span>Zoom</span>
              <button
                type="button"
                className={detailDensity === "fit" ? "chip active" : "chip"}
                onClick={() => setDetailDensity("fit")}
              >
                Ajustar
              </button>
              <button
                type="button"
                className={detailDensity === "normal" ? "chip active" : "chip"}
                onClick={() => setDetailDensity("normal")}
              >
                Normal
              </button>
              <button
                type="button"
                className={detailDensity === "detail" ? "chip active" : "chip"}
                onClick={() => setDetailDensity("detail")}
              >
                Detalle
              </button>
            </>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap", width: "100%" }}>
              <span>Filtrar por días</span>
              <MultiCheckDropdown
                label="Seleccionar días"
                options={dateOptions}
                values={selectedDates}
                onChange={setSelectedDates}
              />
              <button
                type="button"
                className="chip"
                onClick={() => setSelectedDates([])}
                disabled={selectedDates.length === 0}
              >
                Todos los días
              </button>
            </div>
          )}
        </div>
        {(isTemporal && props.timeGrouping === "day") || !isTemporal ? (
          <div className="weekday-filter">
            <span>Día de semana</span>
            {weekdayOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={selectedWeekdays.includes(option.value) ? "chip active" : "chip"}
                onClick={() => toggleWeekday(option.value)}
              >
                {option.label}
              </button>
            ))}
            <button type="button" className="chip" onClick={() => setSelectedWeekdays([1, 2, 3, 4, 5, 6, 0])}>
              Todos
            </button>
          </div>
        ) : null}
        {isTemporal ? <ChartLegend showReal={props.showReal} hasRealData={props.hasRealData} /> : null}
        <div className={isTemporal ? "analysis-chart chart-scroll-x" : "analysis-chart chart-scroll-y"}>
          {isTemporal ? (
            <div
              style={{
                minWidth:
                  detailDensity === "fit"
                    ? "100%"
                    : `${Math.max(900, visibleTemporalRows.length * (detailDensity === "detail" ? 150 : 64))}px`,
                height: "100%",
              }}
            >
              <Line
                data={props.temporalChartData(visibleTemporalRows, props.comparisonRows, props.showReal)}
                options={lineOptions}
              />
            </div>
          ) : (
            <div
              style={{
                minHeight: `${Math.max(620, modalStationRanking.length * 42)}px`,
                height: `${Math.max(620, modalStationRanking.length * 42)}px`,
              }}
            >
              <Bar
                data={props.rankingChartData(modalStationRanking, modalStationComparison)}
                options={barOptions}
              />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
