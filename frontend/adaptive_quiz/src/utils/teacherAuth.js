/**
 * utils/teacherAuth.js
 * Teacher dashboard has no login flow — a shared key (backend TEACHER_KEY env var)
 * gates the cross-student endpoints instead. Entered once via an inline form
 * (TeacherDashboard's key-gate), cached in localStorage from then on.
 */
const STORAGE_KEY = 'stemTeacherKey';

export function getTeacherKey() {
  return localStorage.getItem(STORAGE_KEY) || '';
}

export function setTeacherKey(key) {
  if (key) localStorage.setItem(STORAGE_KEY, key);
}

export function clearTeacherKey() {
  localStorage.removeItem(STORAGE_KEY);
}
