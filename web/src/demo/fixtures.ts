/**
 * DEMO DATA — for previewing the teacher page only.
 *
 * Nothing here is real or ever sent anywhere. When the page is connected to the
 * server this file is no longer used. Real students are added by the admin.
 */

import type { CaptureState, Lesson, Student, Teacher } from '../lib/types';
import type { StatusKey } from '../config/statuses';

export const demoTeacher: Teacher = {
  name: 'Demo Teacher',
  email: 'teacher@school.example',
};

export const demoLesson: Lesson = {
  classRef: { grade: 9, track: 'Advanced', section: 4 },
  period: 3,
  subject: 'Mathematics',
  start: '09:40',
  end: '10:25',
  room: 'Room 9-A4',
};

export const demoNextLesson: Lesson = {
  classRef: { grade: 10, track: 'General', section: 2 },
  period: 4,
  subject: 'Mathematics',
  start: '10:30',
  end: '11:15',
  room: 'Room 10-G2',
};

export const demoCapture: CaptureState = {
  kind: 'captured',
  at: '09:43',
  source: 'Board · Room 9-A4',
};

// Starting statuses so every colour is visible in the preview.
const initial: Partial<Record<number, StatusKey>> = {
  4: 'absent',
  9: 'late',
  13: 'bathroom',
  17: 'review',
  21: 'absent',
};

export const demoStudents: Student[] = Array.from({ length: 25 }, (_, i) => {
  const n = i + 1;
  return {
    id: `S-09${String(n).padStart(2, '0')}`,
    name: `Student ${String(n).padStart(2, '0')}`,
    status: initial[n] ?? 'present',
  };
});
