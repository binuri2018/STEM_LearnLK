/**
 * api/studyPlanApi.js — Student-customized weekly study timetable, persisted per lesson.
 */
import axiosInstance from './axiosInstance';

// Fetch the student's saved custom plan for a lesson. Resolves to null if none exists yet.
export const getStudyPlan = async (lessonId) => {
  try {
    const res = await axiosInstance.get(`/study-plan/${lessonId}`);
    return res.data.data;
  } catch (err) {
    if (err.response?.status === 404) return null;
    throw err;
  }
};

// Save (create or overwrite) the student's custom plan for a lesson.
export const saveStudyPlan = async (lessonId, { schedule, intensity, weeklyMinutes, weekRangeLabel }) => {
  const res = await axiosInstance.put(`/study-plan/${lessonId}`, { schedule, intensity, weeklyMinutes, weekRangeLabel });
  return res.data.data;
};

// Discard the saved custom plan — the report page falls back to the auto-generated one.
export const resetStudyPlan = async (lessonId) => {
  const res = await axiosInstance.delete(`/study-plan/${lessonId}`);
  return res.data;
};
