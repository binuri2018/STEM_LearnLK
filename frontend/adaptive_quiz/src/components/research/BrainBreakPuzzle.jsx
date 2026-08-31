import { useState, useEffect, useCallback } from 'react';
import './BrainBreakPuzzle.css';

const STEM_ICONS = ['⚛️', '🧬', '🧪', '🔭'];

const BrainBreakPuzzle = ({ isOpen, onWin, onFail, avatarSpeak }) => {
  const [sequence, setSequence] = useState([]);
  const [userSequence, setUserSequence] = useState([]);
  const [isPlayingSequence, setIsPlayingSequence] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const [gameState, setGameState] = useState('intro'); // intro, playing, user_turn, result

  const startNewGame = useCallback(() => {
    const newSeq = Array.from({ length: 3 }, () => Math.floor(Math.random() * STEM_ICONS.length));
    setSequence(newSeq);
    setUserSequence([]);
    setGameState('playing');
    avatarSpeak("Watch the pattern closely...");
  }, [avatarSpeak]);

  useEffect(() => {
    if (isOpen && gameState === 'intro') {
      const timer = setTimeout(startNewGame, 1500);
      return () => clearTimeout(timer);
    }
  }, [isOpen, gameState, startNewGame]);

  // Play sequence animation
  useEffect(() => {
    if (gameState === 'playing') {
      setIsPlayingSequence(true);
      let idx = 0;
      const interval = setInterval(() => {
        setHighlightIdx(sequence[idx]);
        setTimeout(() => setHighlightIdx(-1), 600);
        
        idx++;
        if (idx >= sequence.length) {
          clearInterval(interval);
          setTimeout(() => {
            setIsPlayingSequence(false);
            setGameState('user_turn');
            avatarSpeak("Your turn! Repeat the pattern.");
          }, 800);
        }
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [gameState, sequence, avatarSpeak]);

  const handleIconClick = (idx) => {
    if (gameState !== 'user_turn' || isPlayingSequence) return;

    const newUsers = [...userSequence, idx];
    setUserSequence(newUsers);

    // Check if correct so far
    if (idx !== sequence[newUsers.length - 1]) {
      setGameState('result');
      avatarSpeak("Not quite! Let's get back to the assessment.");
      setTimeout(onFail, 2000);
      return;
    }

    // Check if finished
    if (newUsers.length === sequence.length) {
      setGameState('result');
      avatarSpeak("Perfect! Your energy is restored! 🔋");
      setTimeout(onWin, 2000);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="puzzle-overlay">
      <div className="puzzle-modal">
        <div className="puzzle-header">
          <h2>🧠 Brain Break: STEM Recharge</h2>
          <p>Match the pattern to restore your Mental Energy!</p>
        </div>

        <div className="puzzle-board">
          {STEM_ICONS.map((icon, idx) => (
            <button 
              key={idx}
              className={`puzzle-btn ${highlightIdx === idx ? 'highlight' : ''}`}
              onClick={() => handleIconClick(idx)}
              disabled={gameState !== 'user_turn'}
            >
              <span className="icon">{icon}</span>
            </button>
          ))}
        </div>

        <div className="puzzle-status">
          {gameState === 'playing' && "Avatar is thinking..."}
          {gameState === 'user_turn' && `Step ${userSequence.length + 1} of ${sequence.length}`}
          {gameState === 'result' && "Recharging..."}
        </div>
      </div>
    </div>
  );
};

export default BrainBreakPuzzle;
