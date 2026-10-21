import { useCallback, useMemo, useState } from 'react';
import { STATUSES, getStatus, type StatusKey } from '../../config/statuses';
import type { CaptureState, Lesson, Student, Teacher } from '../../lib/types';
import { SearchIcon } from '../../components/Icons';
import { Toast } from '../../components/Toast';
import { TopBar } from './TopBar';
import { LessonHeader } from './LessonHeader';
import { Counters } from './Counters';
import { StudentList } from './StudentList';
import { StatusSheet } from './StatusSheet';
import { Legend } from './Legend';
import { NextLesson } from './NextLesson';

interface Props {
  teacher: Teacher;
  lesson: Lesson;
  capture: CaptureState;
  next?: Lesson;
  students: Student[];
  onChangeStudent: (id: string, status: StatusKey, note: string) => void;
  onSignOut: () => void;
}

type Filter = StatusKey | 'all';

export function ClassDashboard({ teacher, lesson, capture, next, students, onChangeStudent, onSignOut }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const counts = useMemo(() => {
    const c = Object.fromEntries(STATUSES.map((s) => [s.key, 0])) as Record<StatusKey, number>;
    for (const s of students) c[s.status] += 1;
    return c;
  }, [students]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return students.filter(
      (s) =>
        (filter === 'all' || s.status === filter) &&
        (q === '' || s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)),
    );
  }, [students, filter, query]);

  const openStudent = students.find((s) => s.id === openId) ?? null;
  const closeSheet = useCallback(() => setOpenId(null), []);
  const clearToast = useCallback(() => setToast(null), []);

  return (
    <div className="page">
      <TopBar teacher={teacher} onSignOut={onSignOut} />

      <LessonHeader lesson={lesson} capture={capture} />

      <h2 className="section-title">
        Summary · {students.length} students
      </h2>
      <Counters counts={counts} active={filter} onSelect={setFilter} />

      <div className="toolbar">
        <div className="search">
          <SearchIcon className="search-icon" />
          <label htmlFor="search" className="visually-hidden">
            Search students
          </label>
          <input
            id="search"
            className="input"
            type="search"
            placeholder="Search by name or ID"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            dir="auto"
          />
        </div>
        <p className="filter-status" aria-live="polite">
          {filter === 'all' ? (
            <>Showing all students · tap a box above to filter</>
          ) : (
            <>
              Showing <strong>{getStatus(filter).label}</strong> · {visible.length}
              <button type="button" className="link-btn" onClick={() => setFilter('all')}>
                Show all
              </button>
            </>
          )}
        </p>
      </div>

      <StudentList students={visible} onOpen={(s) => setOpenId(s.id)} />

      <Legend />
      {next && <NextLesson lesson={next} />}

      {openStudent && (
        <StatusSheet
          student={openStudent}
          onClose={closeSheet}
          onSave={(status, note) => {
            onChangeStudent(openStudent.id, status, note);
            setOpenId(null);
            setToast(`${openStudent.name}: ${getStatus(status).label} (preview — not sent)`);
          }}
        />
      )}
      {toast && <Toast message={toast} onDone={clearToast} />}
    </div>
  );
}
