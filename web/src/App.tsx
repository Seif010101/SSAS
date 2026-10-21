import { useState } from 'react';
import type { StatusKey } from './config/statuses';
import type { Student } from './lib/types';
import { useHashRoute } from './lib/useHashRoute';
import { LoginPage } from './features/teacher/LoginPage';
import { ClassDashboard } from './features/teacher/ClassDashboard';
import { NoClassPage } from './features/teacher/NoClassPage';
// Preview data — replaced by the server API in a later phase.
import { demoCapture, demoLesson, demoNextLesson, demoStudents, demoTeacher } from './demo/fixtures';

/**
 * Routes (preview):
 *   #/login     teacher sign-in
 *   #/class     the class the teacher is teaching now
 *   #/no-class  what a teacher sees between periods
 */
export function App() {
  const [route, navigate] = useHashRoute('login');
  const [students, setStudents] = useState<Student[]>(demoStudents);

  const changeStudent = (id: string, status: StatusKey, note: string) =>
    setStudents((list) => list.map((s) => (s.id === id ? { ...s, status, note: note || undefined } : s)));

  const signOut = () => navigate('login');

  switch (route) {
    case 'class':
      return (
        <ClassDashboard
          teacher={demoTeacher}
          lesson={demoLesson}
          capture={demoCapture}
          next={demoNextLesson}
          students={students}
          onChangeStudent={changeStudent}
          onSignOut={signOut}
        />
      );
    case 'no-class':
      return <NoClassPage teacher={demoTeacher} next={demoNextLesson} onSignOut={signOut} />;
    default:
      return <LoginPage defaultEmail={demoTeacher.email} onSignIn={() => navigate('class')} />;
  }
}
