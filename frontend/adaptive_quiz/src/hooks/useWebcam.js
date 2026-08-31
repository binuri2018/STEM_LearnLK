/**
 * hooks/useWebcam.js
 * Custom hook that continuously captures webcam frames in the background.
 * Periodically POSTs JPEG frames to POST /api/detect-emotion (Python backend using model/best.pt).
 * Returns: { videoRef, currentExpression, isWebcamActive, error }
 *
 * The webcam runs silently in the background the entire time the assessment
 * is active. The latest detected expression is always available via
 * `currentExpression` for use when submitting each answer.
 *
 * Env: VITE_API_URL (default …/api), or set VITE_DETECT_EMOTION_URL to the full detect URL.
 * To use the standalone ML service instead: VITE_DETECT_EMOTION_URL=http://localhost:8000/detect-emotion
 */
import { useEffect, useRef, useState, useCallback } from 'react';

// Default: Python STEM API — POST …/api/detect-emotion (uses backend/model/best.pt)
const API_BASE = import.meta.env.VITE_API_URL || '/api/adaptive-quiz';
const EMOTION_DETECT_URL =
  import.meta.env.VITE_DETECT_EMOTION_URL ||
  `${API_BASE.replace(/\/$/, '')}/detect-emotion`;

// How often (ms) to sample a frame and call the emotion endpoint.
// CPU YOLO inference is slow, so poll gently and never overlap requests.
const CAPTURE_INTERVAL_MS  = 3000;
// Smoothing: keep a rolling buffer of the last N frames
const EXPRESSION_BUFFER_SIZE = 5;
// Minimum frames in agreement before updating the displayed expression (2 = faster feedback)
const MIN_AGREEMENT          = 2;
// Minimum model confidence to accept a frame (valence detectors on 320×240 often peak ~0.15–0.55)
const MIN_CONFIDENCE         = 0.15;

const useWebcam = (isActive = true) => {
  const videoRef          = useRef(null);
  const canvasRef         = useRef(null);
  const intervalRef       = useRef(null);
  const streamRef         = useRef(null);
  const expressionBuffer  = useRef([]); // rolling window for smoothing
  const inFlightRef       = useRef(false); // skip a tick if the last request is still pending

  const [currentExpression, setCurrentExpression] = useState('neutral');
  const [isWebcamActive,    setIsWebcamActive]     = useState(false);
  const [error,             setError]              = useState(null);

  // ── Start webcam stream ────────────────────────────────────────────────────
  const startWebcam = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 320, height: 240, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsWebcamActive(true);
      setError(null);
    } catch (err) {
      console.warn('⚠️  Webcam unavailable:', err.message);
      setError(err.message);
      setIsWebcamActive(false);
    }
  }, []);

  // ── Capture a frame and detect emotion ────────────────────────────────────
  const captureAndDetect = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current) return;
    if (inFlightRef.current) return; // previous frame still being analysed — skip
    const video  = videoRef.current;
    const canvas = canvasRef.current;
    const ctx    = canvas.getContext('2d');

    canvas.width  = video.videoWidth  || 320;
    canvas.height = video.videoHeight || 240;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Convert frame to base64
    // Slightly higher quality helps small-face emotion boxes vs heavy JPEG blur
    const frameB64 = canvas.toDataURL('image/jpeg', 0.82).split(',')[1];

    inFlightRef.current = true;
    try {
      // POST frame to FastAPI /detect-emotion (abort if it takes too long)
      const token = localStorage.getItem('stemToken');
      const ctrl = new AbortController();
      const kill = setTimeout(() => ctrl.abort(), 12000);
      const res = await fetch(EMOTION_DETECT_URL, {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body:    JSON.stringify({ frame: frameB64 }),
        signal:  ctrl.signal,
      });
      clearTimeout(kill);
      if (res.ok) {
        const data       = await res.json();
        const rawExpr    = data.detectedExpression || 'neutral';
        const confidence = typeof data.confidence === 'number' ? data.confidence : 1.0;

        // Reject low-confidence frames — noisy predictions degrade behavioral signals
        if (confidence < MIN_CONFIDENCE) return;

        // Rolling window majority vote: only surface an expression when ≥3/5 frames agree.
        // This eliminates single-frame noise (lighting change, head turn, blink) from
        // influencing the cognitive load calculation.
        const buf = expressionBuffer.current;
        buf.push(rawExpr);
        if (buf.length > EXPRESSION_BUFFER_SIZE) buf.shift();

        const counts = buf.reduce((acc, e) => { acc[e] = (acc[e] || 0) + 1; return acc; }, {});
        const [dominant, votes] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
        if (votes >= MIN_AGREEMENT) {
          setCurrentExpression(dominant);
        }
      } else {
        console.warn(`[useWebcam] /detect-emotion returned ${res.status}; keeping last expression`);
      }
    } catch (err) {
      // If ML service is down / slow, keep last known expression — don't crash
      console.warn('[useWebcam] frame capture failed:', err.message);
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  // ── Stop webcam stream ─────────────────────────────────────────────────────
  const stopWebcam = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setIsWebcamActive(false);
  }, []);

  // ── Lifecycle: start/stop based on isActive prop ──────────────────────────
  useEffect(() => {
    // Create off-screen canvas for frame capture
    canvasRef.current = document.createElement('canvas');

    if (!isActive) {
      stopWebcam();
      return undefined;
    }

    let cancelled = false;

    startWebcam().then(() => {
      if (cancelled) return;
      intervalRef.current = setInterval(captureAndDetect, CAPTURE_INTERVAL_MS);
    });

    return () => {
      cancelled = true;
      stopWebcam();
    };
  }, [isActive, startWebcam, stopWebcam, captureAndDetect]);

  return { videoRef, currentExpression, isWebcamActive, error };
};

export default useWebcam;
