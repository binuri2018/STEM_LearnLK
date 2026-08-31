/**
 * api/axiosInstance.js
 * Configured Axios instance.
 * Attaches JWT token from localStorage to every request automatically.
 */

import axios from 'axios';

// Merged STEM_LearnLK backend: quiz API lives under /api/adaptive-quiz.
const API_URL = import.meta.env.VITE_API_URL || '/api/adaptive-quiz';

const axiosInstance = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 20000, // never let a slow/stuck backend call trap the UI
});

// Request interceptor — attach Bearer token if present
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('stemToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — handle 401 globally
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // A 401 from login/register just means "wrong credentials" — let the page show
    // its own error instead of wiping the form and force-navigating away.
    const url = error.config?.url || '';
    const isAuthAttempt = url.includes('/auth/login') || url.includes('/auth/register');

    if (error.response?.status === 401 && !isAuthAttempt) {
      localStorage.removeItem('stemToken');
      localStorage.removeItem('stemStudent');
      if (window.location.pathname !== '/login') {
        window.alert('Your session has expired. Please log in again — any unsaved progress in this assessment was lost.');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;
