/**
 * pages/PracticePage.jsx
 * Student self-study: upload your own PDF, generate ungraded practice questions.
 * Purely a self-study tool — nothing here is scored, tracked, or saved to reports;
 * it exists so a student can turn their own notes into a quick practice quiz
 * without touching the graded adaptive-assessment question bank.
 */
import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { generatePracticeQuestionsFromPDF } from '../api/questionApi';
import AnswerOptions from '../components/assessment/AnswerOptions';
import './PracticePage.css';

const PracticePage = () => {
  const navigate = useNavigate();
  const [pdfFile, setPdfFile]       = useState(null);
  const [conceptTag, setConceptTag] = useState('');
  const [numQuestions, setNumQuestions] = useState(6);
  const [generating, setGenerating] = useState(false);
  const [error, setError]           = useState('');
  const [questions, setQuestions]   = useState(null); // flat array once generated
  const [idx, setIdx]               = useState(0);
  const [selected, setSelected]     = useState('');
  const [submitted, setSubmitted]   = useState(false);
  const [score, setScore]           = useState(0);
  const [finished, setFinished]     = useState(false);
  const fileInputRef = useRef(null);

  const handleFile = (file) => {
    if (!file) return;
    if (file.type !== 'application/pdf') { setError('Please select a PDF file.'); return; }
    if (file.size > 20 * 1024 * 1024)   { setError('PDF must be under 20 MB.'); return; }
    setError('');
    setPdfFile(file);
  };

  const handleGenerate = async () => {
    if (!pdfFile) { setError('Upload a PDF first.'); return; }
    setGenerating(true);
    setError('');
    try {
      const data = await generatePracticeQuestionsFromPDF({
        pdf: pdfFile,
        conceptTag: conceptTag.trim() || 'General',
        numQuestions,
      });
      const flat = [
        ...(data.questions?.level1 || []),
        ...(data.questions?.level2 || []),
        ...(data.questions?.level3 || []),
      ];
      if (flat.length === 0) { setError('No questions could be generated from this PDF.'); return; }
      setQuestions(flat);
      setIdx(0);
      setSelected('');
      setSubmitted(false);
      setScore(0);
      setFinished(false);
    } catch (err) {
      setError(err.response?.data?.message || 'Generation failed. Is the ML service running?');
    } finally {
      setGenerating(false);
    }
  };

  const current = questions?.[idx];

  const handleSubmit = () => {
    if (!selected) return;
    setSubmitted(true);
    if (selected === current.correctAnswer) setScore((s) => s + 1);
  };

  const handleNext = () => {
    if (idx + 1 < questions.length) {
      setIdx((i) => i + 1);
      setSelected('');
      setSubmitted(false);
    } else {
      setFinished(true);
    }
  };

  const reset = () => {
    setPdfFile(null);
    setQuestions(null);
    setFinished(false);
    setError('');
  };

  return (
    <div className="practice-page">
      <div className="practice-container">
        <div className="practice-header">
          <h1 className="practice-title">📝 Practice Mode</h1>
          <p className="practice-subtitle">Turn your own notes into a quick practice quiz — ungraded, just for you.</p>
        </div>

        {!questions ? (
          <div className="practice-card">
            <label className="practice-label">Concept / Topic (optional)</label>
            <input
              className="practice-input"
              placeholder="e.g. Photosynthesis"
              value={conceptTag}
              onChange={(e) => setConceptTag(e.target.value)}
              disabled={generating}
            />

            <label className="practice-label">Number of Questions</label>
            <select
              className="practice-input"
              value={numQuestions}
              onChange={(e) => setNumQuestions(Number(e.target.value))}
              disabled={generating}
            >
              {[3, 6, 9, 12].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>

            <div
              className={`practice-dropzone ${pdfFile ? 'has-file' : ''}`}
              onClick={() => !generating && fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files[0]); }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                style={{ display: 'none' }}
                onChange={(e) => handleFile(e.target.files[0])}
              />
              {pdfFile ? (
                <div>📄 {pdfFile.name}</div>
              ) : (
                <div>📂 Drop your PDF here or click to upload (max 20MB)</div>
              )}
            </div>

            {error && <div className="practice-error">⚠️ {error}</div>}

            <button className="btn-practice-generate" onClick={handleGenerate} disabled={generating || !pdfFile}>
              {generating ? <><span className="spinner-sm" /> Generating…</> : '✨ Generate Practice Quiz'}
            </button>

            <button className="btn-practice-back" onClick={() => navigate('/lesson-complete')}>← Back</button>
          </div>
        ) : finished ? (
          <div className="practice-card practice-result">
            <div className="practice-result-score">{score} / {questions.length}</div>
            <p>Practice complete — this session was not saved or graded.</p>
            <button className="btn-practice-generate" onClick={reset}>🔄 Practice Another PDF</button>
            <button className="btn-practice-back" onClick={() => navigate('/lesson-complete')}>← Back to Lesson</button>
          </div>
        ) : current ? (
          <div className="practice-card">
            <div className="practice-progress">Question {idx + 1} of {questions.length}</div>
            <h2 className="practice-question-text">{current.questionText}</h2>

            <AnswerOptions
              options={current.options}
              selectedAnswer={selected}
              onSelect={(opt) => !submitted && setSelected(opt)}
              disabled={submitted}
              correctAnswer={current.correctAnswer}
              showResult={submitted}
            />

            {submitted && selected !== current.correctAnswer && current.shortTheoryExplanation && (
              <div className="practice-hint">📖 {current.shortTheoryExplanation}</div>
            )}

            <div className="practice-actions">
              {!submitted ? (
                <button className="btn-practice-generate" onClick={handleSubmit} disabled={!selected}>Submit</button>
              ) : (
                <button className="btn-practice-generate" onClick={handleNext}>
                  {idx + 1 < questions.length ? 'Next Question →' : 'Finish'}
                </button>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default PracticePage;
