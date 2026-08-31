/**
 * components/assessment/Timer.jsx
 * Displays elapsed time for the current question.
 * Turns amber when > 20s and red when > 30s (high response time threshold).
 */
import { formatTime } from '../../utils/quizLogic';
import './Timer.css';

const Timer = ({ elapsed }) => {
  const colorClass = elapsed >= 30 ? 'danger' : elapsed >= 20 ? 'warning' : 'normal';

  return (
    <div className={`timer-badge ${colorClass}`}>
      <span className="timer-icon">⏱</span>
      <span className="timer-display">{formatTime(elapsed)}</span>
    </div>
  );
};

export default Timer;
