import './GamificationBar.css';

const GamificationBar = ({ hp, xp, level, onRecharge }) => {
  return (
    <div className="gamification-container">
      {/* Mental Energy (HP) */}
      <div className="stat-item hp-section">
        <div className="stat-label">
          <span>⚡ Mental Energy</span>
          <span className="stat-value">{Math.round(hp)}%</span>
        </div>
        <div className="stat-bar-bg">
          <div 
            className="stat-bar-fill hp-fill" 
            style={{ width: `${hp}%`, backgroundColor: hp > 50 ? '#22c55e' : hp > 25 ? '#f59e0b' : '#ef4444' }}
          ></div>
        </div>
      </div>

      {/* Experience (XP) */}
      <div className="stat-item xp-section">
        <div className="stat-label">
          <span>🏆 STEM Rank: Level {level}</span>
          <span className="stat-value">{xp} XP</span>
        </div>
        <div className="stat-bar-bg">
          <div 
            className="stat-bar-fill xp-fill" 
            style={{ width: `${(xp % 100)}%` }}
          ></div>
        </div>
      </div>

      {/* Manual Recharge Button */}
      <button className="recharge-btn" onClick={onRecharge} title="Take a Brain Break to Restore Energy">
        🧩 Recharge
      </button>
    </div>
  );
};

export default GamificationBar;
