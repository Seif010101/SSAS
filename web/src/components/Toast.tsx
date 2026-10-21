import { useEffect } from 'react';

export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const t = window.setTimeout(onDone, 2600);
    return () => window.clearTimeout(t);
  }, [message, onDone]);

  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  );
}
