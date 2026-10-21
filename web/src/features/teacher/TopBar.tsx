import { SCHOOL } from '../../config/school';
import type { Teacher } from '../../lib/types';
import { CheckCircleIcon } from '../../components/Icons';

export function TopBar({ teacher, onSignOut }: { teacher: Teacher; onSignOut: () => void }) {
  const initials = teacher.name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          <CheckCircleIcon className="brand-icon" />
        </div>
        <p className="brand-name">
          {SCHOOL.appName} <span className="brand-role">· Teacher</span>
        </p>
      </div>
      <button type="button" className="avatar-btn" onClick={onSignOut} title={`Signed in as ${teacher.email}`}>
        <span className="avatar" aria-hidden="true">
          {initials}
        </span>
        Sign out
      </button>
    </header>
  );
}
