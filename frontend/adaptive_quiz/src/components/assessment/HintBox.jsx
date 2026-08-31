/**
 * components/assessment/HintBox.jsx
 * Displayed when the student is struggling (needs_hint state or confused/frustrated expression).
 */
import './HintBox.css';

const HintBox = ({ hint, visible, type = 'hint' }) => {
  if (!visible) return null;

  const isSupport = type === 'support';
  const icon = isSupport ? '💬' : '💡';
  const title = isSupport ? 'Student Supporter' : 'Hint';
  const boxClass = isSupport ? 'hint-box support-mode' : 'hint-box';

  const handleSpeak = () => {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(hint);
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className={boxClass}>
      <div className="hint-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="hint-icon">{icon}</span>
          <span className="hint-title">{title}</span>
        </div>
        <button 
          className="btn-speak" 
          onClick={handleSpeak}
          title="Listen"
          style={{ 
            background: 'transparent', border: 'none', cursor: 'pointer', 
            fontSize: '16px', opacity: 0.7, padding: '4px' 
          }}
        >
          🔊
        </button>
      </div>
      <p className="hint-text">{hint}</p>
    </div>
  );
};

export default HintBox;
