/**
 * components/assessment/LevelProgressBar.jsx
 * Shows overall progress: which level the student is on and
 * how many questions have been answered out of the total.
 */
import './LevelProgressBar.css';

const LEVELS = [
  { num: 1, label: 'Basic' },
  { num: 2, label: 'Concept' },
  { num: 3, label: 'Advanced' },
];

const LevelProgressBar = ({ currentLevel, answeredCount, totalQuestions }) => {
  const overallPct = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0;

  return (
    <div className="level-progress">
      {/* Level steps */}
      <div className="level-steps">
        {LEVELS.map((lvl, idx) => (
          <div key={lvl.num} className="level-step-wrapper">
            <div className={`level-step ${currentLevel === lvl.num ? 'active' : ''} ${currentLevel > lvl.num ? 'done' : ''}`}>
              {currentLevel > lvl.num ? '✓' : lvl.num}
            </div>
            <span className="level-step-label">{lvl.label}</span>
            {idx < LEVELS.length - 1 && (
              <div className={`level-connector ${currentLevel > lvl.num ? 'done' : ''}`} />
            )}
          </div>
        ))}
      </div>

      {/* Overall progress bar */}
      <div className="overall-progress">
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${overallPct}%` }} />
        </div>
        <span className="progress-text">{answeredCount} / {totalQuestions} Questions</span>
      </div>
    </div>
  );
};

export default LevelProgressBar;
