import type { Student } from '../../lib/types';
import { StatusDot } from '../../components/StatusDot';
import { StatusPill } from '../../components/StatusPill';
import { ChevronIcon } from '../../components/Icons';

interface Props {
  students: Student[];
  onOpen: (student: Student) => void;
}

export function StudentList({ students, onOpen }: Props) {
  if (students.length === 0) {
    return (
      <div className="student-list">
        <p className="empty">No students match this filter.</p>
      </div>
    );
  }

  return (
    <ul className="student-list" aria-label="Students">
      {students.map((s) => (
        <li key={s.id}>
          <button type="button" className="student-row" onClick={() => onOpen(s)}>
            <StatusDot status={s.status} size={16} />
            <span className="student-main">
              <span className="student-name" dir="auto">
                {s.name}
              </span>
              <span className="student-id">
                {s.id}
                {s.note ? ` · ${s.note}` : ''}
              </span>
            </span>
            <StatusPill status={s.status} />
            <ChevronIcon className="chevron" />
          </button>
        </li>
      ))}
    </ul>
  );
}
