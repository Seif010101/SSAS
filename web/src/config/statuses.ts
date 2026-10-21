/**
 * Attendance statuses shown on the teacher page.
 *
 * This is the single place to rename a status, change its colour or add a new
 * one for another school: the list, the counters, the legend and the status
 * picker are all generated from it.
 */

export type StatusKey = 'present' | 'late' | 'bathroom' | 'escaped' | 'absent' | 'review';

export interface StatusDef {
  key: StatusKey;
  /** Text shown next to the dot (colour is never the only cue). */
  label: string;
  /** One-line explanation for the legend and the status picker. */
  description: string;
  /** Dot colour. */
  color: string;
  /** Soft background for the status pill. */
  tint: string;
  /** 'outline' draws a ring instead of a filled dot (used for "not decided yet"). */
  shape: 'filled' | 'outline';
  /** Whether a teacher can pick this status for a student. */
  teacherCanSet: boolean;
}

export const STATUSES: readonly StatusDef[] = [
  {
    key: 'present',
    label: 'Present',
    description: 'In class — recognised by the board or confirmed by you.',
    color: '#16a34a',
    tint: '#dcfce7',
    shape: 'filled',
    teacherCanSet: true,
  },
  {
    key: 'late',
    label: 'Late / Outside',
    description: 'Arrived late or was outside when attendance was taken.',
    color: '#f97316',
    tint: '#ffedd5',
    shape: 'filled',
    teacherCanSet: true,
  },
  {
    key: 'bathroom',
    label: 'Bathroom',
    description: 'Excused — went to the bathroom.',
    color: '#eab308',
    tint: '#fef9c3',
    shape: 'filled',
    teacherCanSet: true,
  },
  {
    key: 'escaped',
    label: 'Escaped',
    description: 'Left the class without permission.',
    color: '#dc2626',
    tint: '#fee2e2',
    shape: 'filled',
    teacherCanSet: true,
  },
  {
    key: 'absent',
    label: 'Absent',
    description: 'Not in class.',
    color: '#6b7280',
    tint: '#f3f4f6',
    shape: 'filled',
    teacherCanSet: true,
  },
  {
    key: 'review',
    label: 'Needs review',
    description: 'The board was not sure — please confirm this student.',
    color: '#2563eb',
    tint: '#dbeafe',
    shape: 'outline',
    teacherCanSet: false,
  },
];

const BY_KEY = new Map(STATUSES.map((s) => [s.key, s]));

export function getStatus(key: StatusKey): StatusDef {
  const status = BY_KEY.get(key);
  if (!status) throw new Error(`Unknown status: ${key}`);
  return status;
}

export const TEACHER_STATUSES = STATUSES.filter((s) => s.teacherCanSet);
