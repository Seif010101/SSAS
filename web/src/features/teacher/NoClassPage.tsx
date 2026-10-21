import type { Lesson, Teacher } from '../../lib/types';
import { CalendarIcon } from '../../components/Icons';
import { TopBar } from './TopBar';
import { NextLesson } from './NextLesson';

interface Props {
  teacher: Teacher;
  next?: Lesson;
  onSignOut: () => void;
}

/** Shown when the timetable has no class for this teacher right now. */
export function NoClassPage({ teacher, next, onSignOut }: Props) {
  return (
    <div className="page">
      <TopBar teacher={teacher} onSignOut={onSignOut} />
      <main className="card no-class">
        <div className="no-class-icon">
          <CalendarIcon className="capture-icon" />
        </div>
        <h1>No class right now</h1>
        <p>Your class page opens automatically when your next period starts.</p>
      </main>
      {next && <NextLesson lesson={next} />}
    </div>
  );
}
