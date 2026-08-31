/**
 * pages/LessonCompletedPage.jsx
 * Shown after the student finishes an AR lesson.
 * Displays lesson info and a button to begin the 3-level assessment.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAllLessons } from '../api/lessonApi';
import { getAssessmentQuestions, getAdaptiveAssessmentQuestions } from '../api/assessmentApi';
import { useAssessment } from '../context/AssessmentContext';
import './LessonCompletedPage.css';

const LessonCompletedPage = () => {
  const navigate = useNavigate();
  const { student, setStudent, startAssessment } = useAssessment();

  const [lesson,            setLesson]            = useState(null);
  const [loading,           setLoading]           = useState(true);
  const [starting,          setStarting]          = useState(false);
  const [error,             setError]             = useState('');
  const [previousWeakAreas, setPreviousWeakAreas] = useState([]);
  const [previousScore,     setPreviousScore]     = useState(null);

  // Restore student from localStorage on page refresh
  useEffect(() => {
    if (!student) {
      const stored = localStorage.getItem('stemStudent');
      if (stored) setStudent(JSON.parse(stored));
      else { navigate('/login'); return; }
    }
  }, []);

  // Fetch lesson and check for previous weak areas (adaptive mode)
  useEffect(() => {
    const fetchLesson = async () => {
      try {
        const res = await getAllLessons();
        if (!res.data?.length) { setError('No lessons found. Please run the seed script.'); return; }
        const foundLesson = res.data[0];
        setLesson(foundLesson);

        // If student is known, try to load their previous weak areas via adaptive endpoint
        const sid = student?.studentId || JSON.parse(localStorage.getItem('stemStudent') || '{}')?.studentId;
        if (sid) {
          try {
            const adaptive = await getAdaptiveAssessmentQuestions(foundLesson.lessonId, sid);
            if (adaptive.isAdaptive) {
              setPreviousWeakAreas(adaptive.previousWeakAreas || []);
              setPreviousScore(adaptive.previousScore ?? null);
            }
          } catch { /* no previous session — normal mode */ }
        }
      } catch {
        setError('Could not connect to server. Is the backend running?');
      } finally {
        setLoading(false);
      }
    };
    fetchLesson();
  }, [student]);

  const handleStartAssessment = async () => {
    if (!lesson) return;
    setStarting(true);
    try {
      const sid = student?.studentId;
      // Use adaptive endpoint when a previous session exists (it returns same shape)
      const res = sid && previousWeakAreas.length > 0
        ? await getAdaptiveAssessmentQuestions(lesson.lessonId, sid)
        : await getAssessmentQuestions(lesson.lessonId);

      const formattedQuestions = {
        level1: res.levels.level1.questions || [],
        level2: res.levels.level2.questions || [],
        level3: res.levels.level3.questions || [],
      };

      startAssessment(lesson, formattedQuestions, previousWeakAreas, previousScore);
      navigate('/assessment');
    } catch {
      setError('Failed to load questions. Please try again.');
    } finally {
      setStarting(false);
    }
  };

  if (loading) return (
    <div className="lc-page">
      <div className="lc-loader"><div className="spin-ring"/><p>Loading lesson…</p></div>
    </div>
  );

  return (
    <div className="lc-page">
      <div className="lc-card">
        {/* Congrats banner */}
        <div className="lc-banner">
          <div className="lc-trophy">🏆</div>
          <h1 className="lc-title">AR Lesson Complete!</h1>
          <p className="lc-subtitle">Great work! Now let's see how well you've understood the material.</p>
        </div>

        {/* Student info */}
        {student && (
          <div className="lc-student-chip">
            <span>👤</span>
            <span>{student.name} — {student.studentId}</span>
          </div>
        )}

        {/* Returning student: jump straight to existing report / study plan without redoing the quiz */}
        {previousScore !== null && (
          <button
            type="button"
            className="lc-view-plan-link"
            onClick={() => navigate('/report')}
            style={{
              display: 'block', margin: '0 auto 16px', background: 'none', border: 'none',
              color: '#6366f1', textDecoration: 'underline', cursor: 'pointer', fontSize: '14px',
            }}
          >
            📊 View My Last Report &amp; Study Plan
          </button>
        )}

        <button
          type="button"
          className="lc-view-plan-link"
          onClick={() => navigate('/practice')}
          style={{
            display: 'block', margin: '0 auto 16px', background: 'none', border: 'none',
            color: '#22c55e', textDecoration: 'underline', cursor: 'pointer', fontSize: '14px',
          }}
        >
          📝 Practice Mode — Generate a Quiz from Your Own Notes
        </button>

        {/* Adaptive mode: show previous weak areas if available */}
        {previousWeakAreas.length > 0 && (
          <div className="lc-adaptive-banner">
            <div className="lc-adaptive-title">
              🎯 Adaptive Mode — Focus on Weak Areas
            </div>
            <p className="lc-adaptive-note">
              Based on your last attempt ({previousScore !== null ? `${Math.round(previousScore)}%` : ''}), these concepts will be prioritised in this quiz:
            </p>
            <div className="lc-weak-tags">
              {previousWeakAreas.map((area) => (
                <span key={area} className="lc-weak-tag">📌 {area}</span>
              ))}
            </div>
          </div>
        )}

        {/* Lesson card */}
        {lesson && (
          <div className="lc-lesson-info">
            <div className="lc-lesson-badge">{lesson.subject}</div>
            <h2 className="lc-lesson-title">{lesson.title}</h2>
            <p className="lc-lesson-desc">{lesson.description}</p>
            <div className="lc-meta">
              <span>📚 {lesson.gradeLevel}</span>
              <span>⏱ ~{lesson.estimatedDuration} min</span>
            </div>
          </div>
        )}

        {/* Assessment info */}
        <div className="lc-assessment-info">
          <h3>What's Next?</h3>
          <div className="lc-levels">
            {[
              { lvl: 1, icon: '🟢', label: 'Level 1', desc: '3 Basic Questions' },
              { lvl: 2, icon: '🟡', label: 'Level 2', desc: '3 Concept Questions' },
              { lvl: 3, icon: '🔴', label: 'Level 3', desc: '3 Advanced Questions' },
            ].map(l => (
              <div className="lc-level-item" key={l.lvl}>
                <span>{l.icon}</span>
                <div>
                  <strong>{l.label}</strong>
                  <span>{l.desc}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="lc-note">💡 The system will monitor your responses and facial expressions to provide personalised support.</p>
        </div>

        {error && <div className="lc-error">⚠️ {error}</div>}

        <button id="btn-start-assessment" className="btn-start" onClick={handleStartAssessment} disabled={!lesson || starting}>
          {starting ? <><span className="spinner-sm"/>Preparing Assessment…</> : '🚀 Start Assessment'}
        </button>
      </div>
    </div>
  );
};

export default LessonCompletedPage;
