/**
 * School-specific wording. Change these for another school or another use.
 */

export const SCHOOL = {
  appName: 'SSAS',
  appTagline: 'Smart Student Attendance',
  /** How a class is written, e.g. "Grade 9 · Advanced · Section 4" (non-breaking spaces keep "Section 4" together). */
  classLabel: (c: { grade: number; track: string; section: number }) =>
    `Grade\u00a0${c.grade} · ${c.track} · Section\u00a0${c.section}`,
  /** Short form used in small places, e.g. "9 Advanced 4". */
  classShortLabel: (c: { grade: number; track: string; section: number }) =>
    `${c.grade} ${c.track} ${c.section}`,
} as const;
