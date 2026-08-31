/**
 * hooks/useTimer.js
 * Custom hook that manages a per-question countdown/elapsed timer.
 * Returns elapsed seconds and exposes start/reset controls.
 */
import { useState, useEffect, useRef, useCallback } from 'react';

const useTimer = () => {
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const intervalRef = useRef(null);

  const start = useCallback(() => {
    setElapsed(0);
    setRunning(true);
  }, []);

  const stop = useCallback(() => {
    setRunning(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
    return elapsed; // return final elapsed time
  }, [elapsed]);

  const reset = useCallback(() => {
    setElapsed(0);
    setRunning(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [running]);

  return { elapsed, running, start, stop, reset };
};

export default useTimer;
