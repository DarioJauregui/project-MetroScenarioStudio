export function ChartLegend(props: { showReal: boolean; hasRealData: boolean }) {
  return (
    <div className="chart-legend-strip">
      <span>
        <i className="legend-swatch predicted" />
        Viajeros previstos
      </span>
      {props.hasRealData ? (
        <span className={props.showReal ? "" : "legend-muted"}>
          <i className="legend-swatch real" />
          Viajeros reales {props.showReal ? "" : "(oculto)"}
        </span>
      ) : (
        <span className="legend-muted">
          <i className="legend-swatch real" />
          Viajeros reales no disponibles
        </span>
      )}
    </div>
  );
}
