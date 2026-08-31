/**
 * components/assessment/AnswerOptions.jsx
 * Renders multiple-choice answer buttons.
 * Tracks how many times the selection changes (answerChanges counter).
 */
import './AnswerOptions.css';

const AnswerOptions = ({
  options,
  selectedAnswer,
  onSelect,
  disabled,
  correctAnswer,
  showResult,
}) => {
  const getOptionClass = (opt) => {
    if (!showResult) {
      return selectedAnswer === opt ? 'option selected' : 'option';
    }
    if (opt === correctAnswer)  return 'option correct';
    if (opt === selectedAnswer && selectedAnswer !== correctAnswer) return 'option wrong';
    return 'option faded';
  };

  return (
    <div className="answer-options">
      {options.map((opt, idx) => (
        <button
          key={idx}
          id={`option-${idx}`}
          className={getOptionClass(opt)}
          onClick={() => !disabled && onSelect(opt)}
          disabled={disabled}
        >
          <span className="option-letter">{String.fromCharCode(65 + idx)}</span>
          <span className="option-text">{opt}</span>
          {showResult && opt === correctAnswer && (
            <span className="option-badge correct-badge">✓ Correct</span>
          )}
          {showResult && opt === selectedAnswer && selectedAnswer !== correctAnswer && (
            <span className="option-badge wrong-badge">✗ Your Answer</span>
          )}
        </button>
      ))}
    </div>
  );
};

export default AnswerOptions;
