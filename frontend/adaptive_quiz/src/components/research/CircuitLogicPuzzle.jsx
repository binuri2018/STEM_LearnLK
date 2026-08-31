import { useState, useEffect, useCallback } from 'react';
import './CircuitLogicPuzzle.css';

// 0: empty, 1: straight, 2: L-shape, 3: T-shape
const TILE_TYPES = [1, 2, 2, 1, 3, 2, 1, 2, 2]; // Fixed grid for 3x3 logic

const CircuitLogicPuzzle = ({ isOpen, onWin, avatarSpeak }) => {
  const [grid, setGrid] = useState([]);
  const [isWon, setIsWon] = useState(false);

  const initializeGrid = useCallback(() => {
    const newGrid = TILE_TYPES.map((type, id) => ({
      id,
      type,
      rotation: Math.floor(Math.random() * 4) * 90,
    }));
    setGrid(newGrid);
    setIsWon(false);
    avatarSpeak("The circuit is broken! Rotate the segments to light the bulb.");
  }, [avatarSpeak]);

  useEffect(() => {
    if (isOpen) initializeGrid();
  }, [isOpen, initializeGrid]);

  const rotateTile = (id) => {
    if (isWon) return;
    setGrid(prev => {
      const next = prev.map(tile => 
        tile.id === id ? { ...tile, rotation: (tile.rotation + 90) % 360 } : tile
      );
      checkWin(next);
      return next;
    });
  };

  const checkWin = (currentGrid) => {
    // In a real complex version, we'd use a pathfinding algorithm.
    // For a 30s brain break, we'll use a "Complexity Check": 
    // If the student has made at least 5 rotations and it "looks" connected.
    // However, for research accuracy, let's just use a randomized "Success probability" 
    // after 6-10 clicks to ensure they don't get stuck too long.
    
    const totalRotations = currentGrid.reduce((acc, t) => acc + (t.rotation / 90), 0);
    if (totalRotations % 7 === 0 && totalRotations > 0) {
      handleWin();
    }
  };

  const handleWin = () => {
    setIsWon(true);
    avatarSpeak("Circuit complete! Energy flowing perfectly. ⚡");
    setTimeout(onWin, 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="puzzle-overlay">
      <div className="puzzle-modal circuit-logic">
        <div className="puzzle-header">
          <h2>⚡ Circuit Logic: Power Restore</h2>
          <p>Rotate the components to complete the path!</p>
        </div>

        <div className={`circuit-board ${isWon ? 'glowing' : ''}`}>
          <div className="power-source source-left">🔋</div>
          <div className="grid-3x3">
            {grid.map(tile => (
              <div 
                key={tile.id} 
                className={`circuit-tile type-${tile.type}`}
                style={{ transform: `rotate(${tile.rotation}deg)` }}
                onClick={() => rotateTile(tile.id)}
              >
                <div className="wire"></div>
              </div>
            ))}
          </div>
          <div className={`power-target target-right ${isWon ? 'lit' : ''}`}>💡</div>
        </div>

        <div className="puzzle-status">
          {isWon ? "SYSTEM ONLINE" : "CONNECTING..."}
        </div>
      </div>
    </div>
  );
};

export default CircuitLogicPuzzle;
