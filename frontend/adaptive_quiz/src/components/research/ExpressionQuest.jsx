import { useState, useEffect, useCallback } from 'react';
import './ExpressionQuest.css';

const QUEST_TARGETS = [
  { emotion: 'happy', label: 'Give me a BIG SMILE!', icon: '😊' },
  { emotion: 'surprised', label: 'Look SURPRISED!', icon: '😲' },
  { emotion: 'neutral', label: 'Take a deep breath and look CALM.', icon: '🧘' }
];

const ExpressionQuest = ({ isOpen, currentExpression, onWin, avatarSpeak }) => {
  const [target, setTarget] = useState(null);
  const [progress, setProgress] = useState(0);
  const [isSuccess, setIsSuccess] = useState(false);

  useEffect(() => {
    if (isOpen) {
      const randomTarget = QUEST_TARGETS[Math.floor(Math.random() * QUEST_TARGETS.length)];
      setTarget(randomTarget);
      setProgress(0);
      setIsSuccess(false);
      avatarSpeak(randomTarget.label);
    }
  }, [isOpen, avatarSpeak]);

  const handleWin = useCallback(() => {
    setIsSuccess(true);
    avatarSpeak("Wonderful! I detect a great shift in your energy. You are ready!");
    setTimeout(onWin, 2000);
  }, [avatarSpeak, onWin]);

  useEffect(() => {
    if (!isOpen || !target || isSuccess) return;

    if (currentExpression === target.emotion) {
      // Progressively fill up to ensure they hold the expression
      const timer = setInterval(() => {
        setProgress(prev => {
          if (prev >= 100) {
            clearInterval(timer);
            handleWin();
            return 100;
          }
          return prev + 10;
        });
      }, 100);
      return () => clearInterval(timer);
    } else {
      // Decay progress if they stop the expression
      const timer = setInterval(() => {
        setProgress(prev => Math.max(0, prev - 5));
      }, 100);
      return () => clearInterval(timer);
    }
  }, [currentExpression, target, isOpen, isSuccess, handleWin]);

  if (!isOpen || !target) return null;

  return (
    <div className="puzzle-overlay">
      <div className="puzzle-modal expression-quest">
        <div className="quest-header">
          <h2>🎭 Expression Quest: Sync Your Mood</h2>
          <p>Match the expression to calibrate your focus!</p>
        </div>

        <div className="quest-display">
          <div className="target-icon">{target.icon}</div>
          <div className="target-instruction">{target.label}</div>
          
          <div className="detection-gauge">
            <div className="gauge-fill" style={{ width: `${progress}%` }}></div>
            <div className="current-detected">
              Detected: <span>{currentExpression || 'Detecting...'}</span>
            </div>
          </div>
        </div>

        <div className="quest-status">
          {progress > 0 ? (progress >= 100 ? "SUCCESS!" : "HOLD IT...") : "Awaiting Expression..."}
        </div>
      </div>
    </div>
  );
};

export default ExpressionQuest;
