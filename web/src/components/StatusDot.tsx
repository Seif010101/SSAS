import { getStatus, type StatusKey } from '../config/statuses';

interface Props {
  status: StatusKey;
  size?: number;
}

/** Coloured circle for a status. Decorative: the status label is always shown next to it. */
export function StatusDot({ status, size = 14 }: Props) {
  const def = getStatus(status);
  const style =
    def.shape === 'outline'
      ? { width: size, height: size, border: `3px solid ${def.color}`, background: '#fff' }
      : { width: size, height: size, background: def.color };
  return <span className="dot" style={style} aria-hidden="true" />;
}
