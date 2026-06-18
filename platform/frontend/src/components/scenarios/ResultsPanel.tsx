import { useEffect, useMemo, useState } from "react";
import { Bar, Line } from "react-chartjs-2";
import { BarChart3, Maximize2, CircleAlert, Info } from "lucide-react";

import type {
  ExecutionResult,
  PredictionRow,
  ResultsTab,
  ScenarioComparisonRow,
  SortDirection,
  TemporalRow,
  TimeGrouping,
} from "../../types";
import {
  weekdayName,
  formatNumber,
  temporalChartData,
  rankingChartData,
} from "../../utils/formatters";
import { ChartLegend } from "../charts/ChartLegend";
import { ChartAnalysisModal } from "../modals/ChartAnalysisModal";
import { MultiCheckDropdown } from "../common/MultiCheckDropdown";
import { InteractiveDetailTable } from "./InteractiveDetailTable";
import { DataTable } from "../common/DataTable";
import { MiniKpi } from "../common/MiniKpi";
import { SectionTitle } from "../common/SectionTitle";

const dataLeakageUrl = "https://www.ibm.com/think/topics/data-leakage-machine-learning";

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

export function ResultsPanel(props: {
  result: ExecutionResult | null;
  networkTotal: number;
  comparisonNetwork?: ScenarioComparisonRow;
  confidence: string;
  activeTab: ResultsTab;
  onTabChange: (tab: ResultsTab) => void;
  temporalRows: TemporalRow[];
  timeGrouping: TimeGrouping;
  onTimeGroupingChange: (grouping: TimeGrouping) => void;
  stationRanking: PredictionRow[];
  comparisonRows: ScenarioComparisonRow[];
  detailRows: PredictionRow[];
  detailFilter: string;
  onDetailFilterChange: (value: string) => void;
  detailSort: { key: keyof PredictionRow; direction: SortDirection };
  onDetailSort: (sort: { key: keyof PredictionRow; direction: SortDirection }) => void;
  comparisonBaseResult?: ExecutionResult | null;
}) {
  const [aggregation, setAggregation] = useState("days");
  const [selectedResultDates, setSelectedResultDates] = useState<string[]>([]);
  const [showReal, setShowReal] = useState(true);
  const [analysisChart, setAnalysisChart] = useState<"temporal" | "ranking" | null>(null);

  const resultExecutionId = props.result?.execution.id ?? null;
  const hasRealData = props.temporalRows.some((row) => row.y_real !== null && row.y_real !== undefined);
  const stationComparison = props.comparisonRows.filter((row) => row.level === "station");

  const resultDates = useMemo(() => {
    const dates = [...new Set((props.result?.prediction_rows ?? []).map((row) => row.target_date))];
    return dates.sort();
  }, [props.result]);

  const activeDates = selectedResultDates.length ? selectedResultDates : resultDates;

  const filteredDetailByDate = useMemo(
    () => props.detailRows.filter((row) => !activeDates.length || activeDates.includes(row.target_date)),
    [activeDates, props.detailRows]
  );

  const aggregateRows = useMemo(() => {
    if (!props.result) return [];
    const rows = props.result.aggregates.filter(
      (row) => !row.target_date || !activeDates.length || activeDates.includes(row.target_date)
    );
    if (aggregation === "days") return rows.filter((row) => row.level === "network_date");
    if (aggregation === "lines") return rows.filter((row) => row.level === "line");
    if (aggregation === "stations") return rows.filter((row) => row.level === "station");
    return filteredDetailByDate;
  }, [activeDates, aggregation, filteredDetailByDate, props.result]);

  const dateOptions = resultDates.map((dateValue) => ({
    value: dateValue,
    label: `${dateValue} (${weekdayName(dateValue)})`,
  }));

  const leakageWarning = props.result?.execution?.warnings?.includes("historical_evaluation_leakage_risk") ?? false;

  useEffect(() => {
    setAggregation("days");
    setSelectedResultDates([]);
    setAnalysisChart(null);
    setShowReal(true);
  }, [resultExecutionId]);

  return (
    <section className="results-panel">
      <div className="results-header">
        <SectionTitle
          icon={<BarChart3 size={19} />}
          title="Resultados"
          subtitle="Visualizaciones tras ejecutar la predicción"
        />
        <div className="result-kpis">
          {props.result ? (
            <>
              <MiniKpi label="Viajes previstos" value={formatNumber(props.networkTotal)} prominent />
              <MiniKpi
                label="vs base"
                value={props.comparisonNetwork ? formatNumber(props.comparisonNetwork.delta_abs) : "Sin comparar"}
              />
              <MiniKpi label="Cobertura" value={props.confidence} />
            </>
          ) : null}
        </div>
      </div>
      {!props.result ? (
        <div className="empty-state">
          <Info size={28} />
          <p>Ejecuta una predicción para ver tarjetas, gráficos y desglose interactivo.</p>
        </div>
      ) : (
        <>
          {leakageWarning ? (
            <div className="historical-warning">
              <CircleAlert size={18} />
              <span>
                Rango evaluado con datos historicos disponibles. Puede existir riesgo de data leakage si se interpreta
                como prediccion operativa.
                <a href={dataLeakageUrl} target="_blank" rel="noreferrer">
                  {" "}
                  Ver explicacion
                </a>
              </span>
            </div>
          ) : null}
          <div className="charts-grid">
            <div className="chart-card chart-card-wide">
              <div className="chart-card-title">
                <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                  <h3>Evolucion temporal</h3>
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button
                      type="button"
                      className={props.timeGrouping === "day" ? "chip active" : "chip"}
                      onClick={() => props.onTimeGroupingChange("day")}
                    >
                      Día
                    </button>
                    <button
                      type="button"
                      className={props.timeGrouping === "week" ? "chip active" : "chip"}
                      onClick={() => props.onTimeGroupingChange("week")}
                    >
                      Semana
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setAnalysisChart("temporal")}
                  title="Analizar evolucion temporal"
                >
                  <Maximize2 size={16} />
                </button>
              </div>
              <ChartLegend showReal={showReal} hasRealData={hasRealData} />
              <div className="chart-block chart-preview">
                <div style={{ height: "100%" }}>
                  <Line
                    data={temporalChartData(props.temporalRows, props.comparisonRows, showReal)}
                    options={lineOptions}
                  />
                </div>
              </div>
            </div>
            <div className="chart-card">
              <div className="chart-card-title">
                <h3>Ranking estaciones</h3>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setAnalysisChart("ranking")}
                  title="Analizar ranking de estaciones"
                >
                  <Maximize2 size={16} />
                </button>
              </div>
              <div className="chart-block chart-preview">
                <div style={{ height: "100%" }}>
                  <Bar data={rankingChartData(props.stationRanking, stationComparison)} options={barOptions} />
                </div>
              </div>
            </div>
          </div>
          {analysisChart ? (
            <ChartAnalysisModal
              chart={analysisChart}
              temporalRows={props.temporalRows}
              timeGrouping={props.timeGrouping}
              onTimeGroupingChange={props.onTimeGroupingChange}
              showReal={showReal}
              onShowRealChange={setShowReal}
              hasRealData={hasRealData}
              comparisonRows={props.comparisonRows}
              stationRanking={props.stationRanking}
              stationComparison={stationComparison}
              onClose={() => setAnalysisChart(null)}
              temporalChartData={temporalChartData}
              rankingChartData={rankingChartData}
              predictionRows={props.result?.prediction_rows ?? []}
              basePredictionRows={props.comparisonBaseResult?.prediction_rows ?? []}
            />
          ) : null}
          <details className="result-table-details">
            <summary>Ver tabla de resultados</summary>
            <div className="table-controls">
              <label>
                Agregacion
                <select value={aggregation} onChange={(event) => setAggregation(event.target.value)}>
                  <option value="days">Solo dias</option>
                  <option value="lines">Lineas</option>
                  <option value="stations">Estaciones</option>
                  <option value="station_line">Detalle linea-estacion</option>
                </select>
              </label>
              <MultiCheckDropdown
                label="Dias"
                options={dateOptions}
                values={selectedResultDates}
                onChange={setSelectedResultDates}
              />
              <button type="button" onClick={() => setSelectedResultDates([])}>
                Todos los dias
              </button>
            </div>
            {aggregation === "station_line" ? (
              <InteractiveDetailTable
                rows={filteredDetailByDate}
                filter={props.detailFilter}
                onFilterChange={props.onDetailFilterChange}
                sort={props.detailSort}
                onSort={props.onDetailSort}
              />
            ) : (
              <DataTable
                rows={aggregateRows}
                columns={
                  aggregation === "days"
                    ? ["target_date", "y_pred", "y_real", "pct_error"]
                    : ["linea", "estacion", "y_pred", "y_real", "pct_error"]
                }
              />
            )}
          </details>
        </>
      )}
    </section>
  );
}
