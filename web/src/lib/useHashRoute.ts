import { useEffect, useState } from 'react';

/** Minimal hash router: "#/class" → "class". Enough until the app needs real routing. */
export function useHashRoute(fallback: string): [string, (route: string) => void] {
  const read = () => window.location.hash.replace(/^#\/?/, '') || fallback;
  const [route, setRoute] = useState(read);

  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const navigate = (next: string) => {
    window.location.hash = `/${next}`;
  };
  return [route, navigate];
}
