import { SCHOOL } from '../../config/school';
import type { Lesson } from '../../lib/types';

export function NextLesson({ lesson }: { lesson: Lesson }) {
  return (
    <p className="next-lesson">
      Next: <strong>Period {lesson.period}</strong> · {SCHOOL.classShortLabel(lesson.classRef)} · {lesson.subject} ·{' '}
      {lesson.start} – {lesson.end} · {lesson.room}
    </p>
  );
}
