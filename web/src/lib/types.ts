import type { StatusKey } from '../config/statuses';

export interface ClassRef {
  grade: number;
  track: string;
  section: number;
}

export interface Lesson {
  classRef: ClassRef;
  period: number;
  subject: string;
  /** "HH:MM" */
  start: string;
  /** "HH:MM" */
  end: string;
  room: string;
}

export type CaptureState =
  | { kind: 'captured'; at: string; source: string }
  | { kind: 'waiting'; opensAt: string }
  | { kind: 'no-data'; reason: string };

export interface Student {
  id: string;
  name: string;
  status: StatusKey;
  note?: string;
}

export interface Teacher {
  name: string;
  email: string;
}
