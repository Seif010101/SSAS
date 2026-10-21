import { STATUSES, type StatusKey } from '../../config/statuses';
import { StatusDot } from '../../components/StatusDot';

interface Props {
  counts: Record<StatusKey, number>;
  active: StatusKey | 'all';
  onSelect: (key: StatusKey | 'all') => void;
}

/** One tile per status. Tapping a tile filters the list (tap again to clear). */
export function Counters({ counts, active, onSelect }: Props) {
  return (
    <div className="counters">
      {STATUSES.map((s) => (
        <button
          key={s.key}
          type="button"
          className="counter"
          aria-pressed={active === s.key}
          onClick={() => onSelect(active === s.key ? 'all' : s.key)}
        >
          <span className="counter-top">
            <StatusDot status={s.key} size={10} />
            {s.label}
          </span>
          <span className="counter-value">{counts[s.key]}</span>
        </button>
      ))}
    </div>
  );
}
