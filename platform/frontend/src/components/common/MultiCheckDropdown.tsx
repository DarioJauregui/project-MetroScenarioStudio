export function MultiCheckDropdown(props: {
  label: string;
  options: Array<{ value: string; label: string }>;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  function toggle(value: string) {
    const next = props.values.includes(value)
      ? props.values.filter((item) => item !== value)
      : [...props.values, value];
    props.onChange(next);
  }
  const selectedLabels = props.options
    .filter((option) => props.values.includes(option.value))
    .map((option) => option.label);
  return (
    <details className="multi-dropdown">
      <summary>
        <span>{props.label}</span>
        <strong>{selectedLabels.length ? selectedLabels.join(", ") : "Seleccionar"}</strong>
      </summary>
      <div className="multi-dropdown-menu">
        {props.options.map((option) => (
          <label key={option.value} className="check-option">
            <input
              type="checkbox"
              checked={props.values.includes(option.value)}
              onChange={() => toggle(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </details>
  );
}
