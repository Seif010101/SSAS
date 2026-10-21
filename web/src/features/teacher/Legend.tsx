import { STATUSES } from '../../config/statuses';
import { StatusDot } from '../../components/StatusDot';

export function Legend() {
  return (
    <details className="legend">
      <summary>What do the colours mean?</summary>
      <ul>
        {STATUSES.map((s) => (
          <li key={s.key}>
            <StatusDot status={s.key} size={14} />
            <div>
              <strong>{s.label}</strong>
              <span>{s.description}</span>
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}
