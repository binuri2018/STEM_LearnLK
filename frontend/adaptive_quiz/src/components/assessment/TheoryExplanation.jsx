/**
 * components/assessment/TheoryExplanation.jsx
 * Shown after a wrong answer — displays the correct answer and a short theory explanation.
 */
import './TheoryExplanation.css';

const TheoryExplanation = ({ correctAnswer, explanation, visible }) => {
  if (!visible) return null;
  return (
    <div className="theory-box">
      <div className="theory-header">
        <span className="theory-icon">📖</span>
        <span className="theory-title">Theory Explanation</span>
      </div>
      <div className="theory-correct">
        <span className="theory-correct-label">Correct Answer:</span>
        <span className="theory-correct-answer">{correctAnswer}</span>
      </div>
      <p className="theory-text">{explanation}</p>
    </div>
  );
};

export default TheoryExplanation;
