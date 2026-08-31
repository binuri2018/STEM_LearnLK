/**
 * api/responseApi.js — Student response and report API calls
 */
import axiosInstance from './axiosInstance';

// Save a single response
export const saveResponse = async (responseData) => {
  const res = await axiosInstance.post('/responses', responseData);
  return res.data;
};

// Save all responses at end of assessment
export const saveBulkResponses = async (responses) => {
  const res = await axiosInstance.post('/responses/bulk', { responses });
  return res.data;
};

// Predict learning state via backend proxy → FastAPI
export const predictLearningState = async (features) => {
  const res = await axiosInstance.post('/predict-learning-state', features);
  return res.data;
};

// Get the final assessment report
export const getReport = async (studentId, lessonId, sessionId = '') => {
  const params = sessionId ? `?sessionId=${sessionId}` : '';
  const res = await axiosInstance.get(`/reports/${studentId}/${lessonId}${params}`);
  return res.data;
};

// Get all past reports for a student (history)
export const getStudentHistory = async (studentId) => {
  const res = await axiosInstance.get(`/reports/history/${studentId}`);
  return res.data;
};

// Get per-session progress timeline for a student + lesson
export const getProgressOverTime = async (studentId, lessonId) => {
  const res = await axiosInstance.get(`/reports/progress/${studentId}/${lessonId}`);
  return res.data;
};
