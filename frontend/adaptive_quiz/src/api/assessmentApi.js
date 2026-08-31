/**
 * api/assessmentApi.js — Assessment questions API calls
 */
import axiosInstance from './axiosInstance';

export const getAssessmentQuestions = async (lessonId) => {
  const res = await axiosInstance.get(`/assessments/${lessonId}`);
  return res.data;
};

export const getQuestionsByLevel = async (lessonId, level) => {
  const res = await axiosInstance.get(`/assessments/${lessonId}/level/${level}`);
  return res.data;
};

// Returns questions reordered so weak-area concepts appear first within each level.
// Falls back to normal ordering when no previous session exists.
export const getAdaptiveAssessmentQuestions = async (lessonId, studentId) => {
  const res = await axiosInstance.get(`/assessments/${lessonId}/adaptive/${studentId}`);
  return res.data;
};
