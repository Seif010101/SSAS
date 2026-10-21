import { useState } from 'react';
import { TEACHER_STATUSES, getStatus, type StatusKey } from '../../config/statuses';
import type { Student } from '../../lib/types';
import { BottomSheet } from '../../components/BottomSheet';
import { StatusDot } from '../../components/StatusDot';

interface Props {
  student: Student;
  onClose: () => void;
  onSave: (status: StatusKey, note: string) => void;
}

/** Lets the teacher change one student's status and add a short note. */
export function StatusSheet({ student, onClose, onSave }: Props) {
  // A student still "under review" has no teacher choice yet.
  const [status, setStatus] = useState<StatusKey | null>(
    getStatus(student.status).teacherCanSet ? student.status : null,
  );
  const [note, setNote] = useState(student.note ?? '');
  const titleId = `sheet-title-${student.id}`;

  return (
    <BottomSheet labelledBy={titleId} onClose={onClose}>
      <div className="sheet-header">
        <StatusDot status={student.status} size={18} />
        <div>
          <h2 id={titleId} dir="auto">
            {student.name}
          </h2>
          <p>
            {student.id} · now: {getStatus(student.status).label}
          </p>
        </div>
      </div>

      <fieldset className="option-list">
        <legend className="visually-hidden">Choose a status</legend>
        {TEACHER_STATUSES.map((s) => (
          <label key={s.key} className="option">
            <input
              type="radio"
              name="status"
              value={s.key}
              checked={status === s.key}
              onChange={() => setStatus(s.key)}
            />
            <StatusDot status={s.key} size={14} />
            <div>
              <strong>{s.label}</strong>
              <span>{s.description}</span>
            </div>
          </label>
        ))}
      </fieldset>

      <div className="field">
        <label htmlFor="note">Note (optional)</label>
        <textarea
          id="note"
          className="input"
          placeholder="e.g. went to the clinic"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          dir="auto"
        />
      </div>

      <div className="sheet-actions">
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={status === null}
          onClick={() => status && onSave(status, note.trim())}
        >
          Save
        </button>
      </div>
    </BottomSheet>
  );
}
