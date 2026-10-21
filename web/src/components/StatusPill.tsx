import { getStatus, type StatusKey } from '../config/statuses';

export function StatusPill({ status }: { status: StatusKey }) {
  const def = getStatus(status);
  return (
    <span className="status-pill" style={{ background: def.tint, color: shade(def.color) }}>
      {def.label}
    </span>
  );
}

// Darken the status colour so the pill text stays readable on its light tint.
function shade(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const f = 0.5;
  const r = Math.round(((n >> 16) & 255) * f);
  const g = Math.round(((n >> 8) & 255) * f);
  const b = Math.round((n & 255) * f);
  return `rgb(${r}, ${g}, ${b})`;
}
