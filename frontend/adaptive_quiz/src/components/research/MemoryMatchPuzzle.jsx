import { useState, useEffect, useCallback } from 'react';
import './MemoryMatchPuzzle.css';

const STEM_ICONS = ['⚛️', '🧬', '🧪', '🔭'];

const MemoryMatchPuzzle = ({ isOpen, onWin, avatarSpeak }) => {
  const [cards, setCards] = useState([]);
  const [flipped, setFlipped] = useState([]);
  const [matched, setMatched] = useState([]);
  const [disabled, setDisabled] = useState(false);

  const initializeGame = useCallback(() => {
    const pairIcons = [...STEM_ICONS, ...STEM_ICONS];
    const shuffled = pairIcons
      .sort(() => Math.random() - 0.5)
      .map((icon, index) => ({ id: index, icon, isFlipped: false }));
    setCards(shuffled);
    setFlipped([]);
    setMatched([]);
    setDisabled(false);
    avatarSpeak("Find the matching pairs to recharge your mind!");
  }, [avatarSpeak]);

  useEffect(() => {
    if (isOpen && cards.length === 0) {
      initializeGame();
    }
  }, [isOpen, cards.length, initializeGame]);

  const handleCardClick = (card) => {
    if (disabled || flipped.includes(card.id) || matched.includes(card.id)) return;

    const newFlipped = [...flipped, card.id];
    setFlipped(newFlipped);

    if (newFlipped.length === 2) {
      setDisabled(true);
      const [firstId, secondId] = newFlipped;
      const firstCard = cards.find(c => c.id === firstId);
      const secondCard = cards.find(c => c.id === secondId);

      if (firstCard.icon === secondCard.icon) {
        setMatched(prev => [...prev, firstId, secondId]);
        setFlipped([]);
        setDisabled(false);
      } else {
        setTimeout(() => {
          setFlipped([]);
          setDisabled(false);
        }, 1000);
      }
    }
  };

  useEffect(() => {
    if (matched.length === STEM_ICONS.length * 2 && matched.length > 0) {
      avatarSpeak("Excellent focus! Your mental battery is full.");
      setTimeout(onWin, 1500);
    }
  }, [matched, onWin, avatarSpeak]);

  if (!isOpen) return null;

  return (
    <div className="puzzle-overlay">
      <div className="puzzle-modal memory-match">
        <div className="puzzle-header">
          <h2>🧬 Neural Match: STEM Pairs</h2>
          <p>Sync the patterns to restore focus!</p>
        </div>

        <div className="memory-grid">
          {cards.map(card => {
            const isFlipped = flipped.includes(card.id) || matched.includes(card.id);
            const isMatched = matched.includes(card.id);
            
            return (
              <div 
                key={card.id} 
                className={`memory-card ${isFlipped ? 'flipped' : ''} ${isMatched ? 'matched' : ''}`}
                onClick={() => handleCardClick(card)}
              >
                <div className="card-inner">
                  <div className="card-front">?</div>
                  <div className="card-back">{card.icon}</div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="puzzle-status">
          {matched.length / 2} of {STEM_ICONS.length} Pairs Found
        </div>
      </div>
    </div>
  );
};

export default MemoryMatchPuzzle;
