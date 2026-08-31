/**
 * api/authApi.js — Student authentication API calls
 */
import axiosInstance from './axiosInstance';

export const registerStudent = async (data) => {
  const res = await axiosInstance.post('/auth/register', data);
  return res.data;
};

export const loginStudent = async (data) => {
  const res = await axiosInstance.post('/auth/login', data);
  return res.data;
};

export const getProfile = async () => {
  const res = await axiosInstance.get('/auth/profile');
  return res.data;
};
