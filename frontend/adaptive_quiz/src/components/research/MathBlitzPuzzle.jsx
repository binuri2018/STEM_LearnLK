import { useState, useEffect, useCallback } from 'react';
import './MathBlitzPuzzle.css';

const MathBlitzPuzzle = ({ isOpen, onWin, onFail, avatarSpeak }) => {
  const [problem, setProblem] = useState({ q: '', a: 0, options: [] });
  const [score, setScore] = useState(0);
  const [timeLeft, setTimeLeft] = useState(5);
  const [gameState, setGameState] = useState('playing'); // playing, result

  const generateProblem = useCallback(() => {
    const ops = ['+', '-', '*'];
    const op = ops[Math.floor(Math.random() * 2)]; // Stick to + and - for speed
    const num1 = Math.floor(Math.random() * 20) + 1;
    const num2 = Math.floor(Math.random() * 20) + 1;
    
    let answer;
    if (op === '+') answer = num1 + num2;
    else answer = Math.max(num1, num2) - Math.min(num1, num2); // Ensure positive

    const options = [
      answer,
      answer + (Math.random() > 0.5 ? 2 : -2),
      answer + (Math.random() > 0.5 ? 5 : -5)
    ].sort(() => Math.random() - 0.5);

    setProblem({ q: `${op === '-' ? Math.max(num1, num2) : num1} ${op} ${op === '-' ? Math.min(num1, num2) : num2} = ?`, a: answer, options });
    setTimeLeft(5);
  }, []);

  const handleWin = useCallback(() => {
    setGameState('result');
    avatarSpeak("Lightning fast! Your logic circuits are fully charged.");
    setTimeout(onWin, 1500);
  }, [avatarSpeak, onWin]);

  const handleFail = useCallback(() => {
    setGameState('result');
    avatarSpeak("Too slow! Let's get back to the test and try again later.");
    setTimeout(onFail, 1500);
  }, [avatarSpeak, onFail]);

  useEffect(() => {
    if (isOpen && gameState === 'playing') {
      generateProblem();
    }
  }, [isOpen, gameState, generateProblem]);

  useEffect(() => {
    if (!isOpen || gameState !== 'playing') return;

    if (timeLeft <= 0) {
      handleFail();
      return;
    }

    const timer = setInterval(() => setTimeLeft(prev => prev - 1), 1000);
    return () => clearInterval(timer);
  }, [timeLeft, isOpen, gameState, handleFail]);

  const handleAnswer = (val) => {
    if (val === problem.a) {
      const newScore = score + 1;
      setScore(newScore);
      if (newScore >= 3) {
        handleWin();
      } else {
        generateProblem();
      }
    } else {
      handleFail();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="puzzle-overlay">
      <div className="puzzle-modal math-blitz">
        <div className="puzzle-header">
          <h2>⚡ Math Blitz: Speed Round</h2>
          <p>Solve 3 problems quickly to recharge!</p>
        </div>

        <div className="math-display">
          <div className="timer-bar">
            <div className="timer-fill" style={{ width: `${(timeLeft / 5) * 100}%` }}></div>
          </div>
          <div className="equation">{problem.q}</div>
        </div>

        <div className="math-options">
          {problem.options.map((opt, i) => (
            <button key={i} className="math-btn" onClick={() => handleAnswer(opt)}>
              {opt}
            </button>
          ))}
        </div>

        <div className="puzzle-status">
          Solved: {score} / 3
        </div>
      </div>
    </div>
  );
};

export default MathBlitzPuzzle;
