import { SCHOOL } from '../../config/school';
import type { CaptureState, Lesson } from '../../lib/types';
import { AlertIcon, CheckCircleIcon, ClockIcon } from '../../components/Icons';

export function LessonHeader({ lesson, capture }: { lesson: Lesson; capture: CaptureState }) {
  return (
    <section className="card lesson" aria-labelledby="lesson-class">
      <p className="lesson-period">
        Period {lesson.period} · {lesson.subject}
      </p>
      <h1 id="lesson-class" className="lesson-class">
        {SCHOOL.classLabel(lesson.classRef)}
      </h1>
      <div className="lesson-meta">
        <span>
          {lesson.start} – {lesson.end}
        </span>
        <span>{lesson.room}</span>
      </div>
      <CaptureBanner capture={capture} />
      <p className="edit-note">You can edit this class only during this period.</p>
    </section>
  );
}

function CaptureBanner({ capture }: { capture: CaptureState }) {
  switch (capture.kind) {
    case 'captured':
      return (
        <div className="capture capture-ok">
          <CheckCircleIcon className="capture-icon" />
          <span>
            Attendance taken at <strong>{capture.at}</strong> by {capture.source}.
          </span>
        </div>
      );
    case 'waiting':
      return (
        <div className="capture capture-wait">
          <ClockIcon className="capture-icon" />
          <span>
            The board will take attendance at <strong>{capture.opensAt}</strong>. Please keep everyone inside until then.
          </span>
        </div>
      );
    case 'no-data':
      return (
        <div className="capture capture-nodata">
          <AlertIcon className="capture-icon" />
          <span>
            No attendance from the board ({capture.reason}). Please mark the class below.
          </span>
        </div>
      );
  }
}
