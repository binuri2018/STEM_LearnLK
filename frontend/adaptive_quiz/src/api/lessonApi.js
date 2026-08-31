/**
 * api/lessonApi.js — Lesson data API calls
 */
import axiosInstance from './axiosInstance';

export const getAllLessons = async () => {
  const res = await axiosInstance.get('/lessons');
  return res.data;
};

export const getLessonById = async (lessonId) => {
  const res = await axiosInstance.get(`/lessons/${lessonId}`);
  return res.data;
};
