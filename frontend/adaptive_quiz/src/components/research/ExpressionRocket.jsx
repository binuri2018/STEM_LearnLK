import { useState, useEffect, useRef, useCallback } from 'react';
import './ExpressionRocket.css';

const ExpressionRocket = ({ isOpen, currentExpression, onWin, avatarSpeak }) => {
  const [rocketPos, setRocketPos] = useState(50); // 0 (top) to 100 (bottom)
  const [stars, setStars] = useState([]);
  const [score, setScore] = useState(0);
  const [gameActive, setGameActive] = useState(false);
  const requestRef = useRef();

  // Initialize Game
  useEffect(() => {
    if (isOpen) {
      setScore(0);
      setRocketPos(50);
      setStars([]);
      setGameActive(true);
      avatarSpeak("Smile to Fly! Catch 10 Knowledge Stars to recharge!");
    } else {
      setGameActive(false);
    }
  }, [isOpen, avatarSpeak]);

  // Rocket Control via Expression
  useEffect(() => {
    if (!gameActive) return;

    const moveRocket = () => {
      setRocketPos(prev => {
        // Smile makes you fly up (0), Neutral/Other makes you fall (100)
        const target = currentExpression === 'happy' ? 10 : 90;
        const diff = target - prev;
        return prev + (diff * 0.1); // Smooth transition
      });
      requestRef.current = requestAnimationFrame(moveRocket);
    };

    requestRef.current = requestAnimationFrame(moveRocket);
    return () => cancelAnimationFrame(requestRef.current);
  }, [currentExpression, gameActive]);

  // Star Spawning & Collision
  useEffect(() => {
    if (!gameActive) return;

    const spawnInterval = setInterval(() => {
      setStars(prev => [
        ...prev.filter(s => s.x > -10), // Cleanup old stars
        { id: Math.random(), x: 100, y: Math.random() * 80 + 10, icon: ['⚛️', '🧬', '🧪'][Math.floor(Math.random() * 3)] }
      ]);
    }, 1000);

    const moveInterval = setInterval(() => {
      setStars(prev => prev.map(s => ({ ...s, x: s.x - 2 })));
    }, 50);

    return () => {
      clearInterval(spawnInterval);
      clearInterval(moveInterval);
    };
  }, [gameActive]);

  const handleWin = useCallback(() => {
    setGameActive(false);
    avatarSpeak("Orbit reached! Energy restored.");
    setTimeout(onWin, 1500);
  }, [avatarSpeak, onWin]);

  // Collision Detection
  useEffect(() => {
    const hitStar = stars.find(s => s.x < 25 && s.x > 15 && Math.abs(s.y - rocketPos) < 15);
    if (hitStar) {
      setScore(prev => {
        const next = prev + 1;
        if (next >= 10) handleWin();
        return next;
      });
      setStars(prev => prev.filter(s => s.id !== hitStar.id));
    }
  }, [stars, rocketPos, handleWin]);

  if (!isOpen) return null;

  return (
    <div className="puzzle-overlay">
      <div className="puzzle-modal rocket-game">
        <div className="game-header">
          <h2>🚀 Expression Rocket</h2>
          <p>Smile Wide to Fly Up | Relax to Fall</p>
        </div>

        <div className="space-stage">
          {/* Rocket */}
          <div 
            className={`rocket-entity ${currentExpression === 'happy' ? 'thrusting' : ''}`}
            style={{ top: `${rocketPos}%` }}
          >
            🚀
            {currentExpression === 'happy' && <div className="exhaust">🔥</div>}
          </div>

          {/* Stars */}
          {stars.map(star => (
            <div key={star.id} className="science-star" style={{ left: `${star.x}%`, top: `${star.y}%` }}>
              {star.icon}
            </div>
          ))}

          {/* HUD */}
          <div className="game-hud">
            Stars: {score} / 10
            <div className="expression-indicator">
              Expression: <span>{currentExpression || 'Searching...'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExpressionRocket;
