/**
 * context/AssessmentContext.jsx
 * Global state management for the entire assessment session.
 * Provides: student info, lesson data, all questions, current progress,
 * responses collected, webcam expression, and session ID.
 *
 * Any component can call useAssessment() to access or update this state.
 */
/* eslint-disable react-refresh/only-export-components -- provider + useAssessment hook intentionally colocated */
import { createContext, useContext, useReducer, useCallback } from 'react';
import { generateSessionId } from '../utils/quizLogic';

// ── Initial State ─────────────────────────────────────────────────────────────
const initialState = {
  student:             null,        // logged-in student object
  lesson:              null,        // current lesson
  allQuestions:        { level1: [], level2: [], level3: [] },
  currentLevel:        1,           // 1 | 2 | 3
  currentQuestionIdx:  0,           // index within current level
  sessionId:           null,        // unique session identifier
  responses:           [],          // all StudentResponse objects collected so far
  isAssessmentDone:    false,       // true after level 3 is finished
  currentExpression:   'neutral',   // latest from webcam hook
  previousWeakAreas:   [],          // weak concept tags from the student's last session
  previousScore:       null,        // total score from the student's last session
};

// ── Reducer ───────────────────────────────────────────────────────────────────
const assessmentReducer = (state, action) => {
  switch (action.type) {

    case 'SET_STUDENT':
      return { ...state, student: action.payload };

    case 'SET_LESSON':
      return { ...state, lesson: action.payload };

    case 'START_ASSESSMENT':
      return {
        ...state,
        lesson:             action.payload.lesson,
        allQuestions:       action.payload.allQuestions,
        currentLevel:       1,
        currentQuestionIdx: 0,
        responses:          [],
        isAssessmentDone:   false,
        sessionId:          generateSessionId(state.student?.studentId, action.payload.lesson?.lessonId),
        previousWeakAreas:  action.payload.previousWeakAreas || [],
        previousScore:      action.payload.previousScore     ?? null,
      };

    case 'SAVE_RESPONSE':
      return { ...state, responses: [...state.responses, action.payload] };

    case 'NEXT_QUESTION': {
      // Adaptive logic: if a targetLevel is passed (e.g., jump to Level 3 early), use it.
      const targetLevel = action.payload?.targetLevel || state.currentLevel;
      const levelKey    = `level${targetLevel}`;
      const levelQs     = state.allQuestions[levelKey] || [];
      
      // If jumping to a new level, start at first question. Otherwise, increment index.
      let nextIdx = (targetLevel !== state.currentLevel) ? 0 : state.currentQuestionIdx + 1;

      if (nextIdx < levelQs.length) {
        return { ...state, currentLevel: targetLevel, currentQuestionIdx: nextIdx };
      }

      // Level complete — move to next level naturally or finish
      const nextNaturalLevel = targetLevel + 1;
      if (nextNaturalLevel <= 3) {
        return { ...state, currentLevel: nextNaturalLevel, currentQuestionIdx: 0 };
      }

      // All levels exhausted
      return { ...state, isAssessmentDone: true };
    }

    case 'SET_EXPRESSION':
      return { ...state, currentExpression: action.payload };

    case 'RESET':
      return { ...initialState, student: state.student };

    default:
      return state;
  }
};

// ── Context ───────────────────────────────────────────────────────────────────
const AssessmentContext = createContext(null);

export const AssessmentProvider = ({ children }) => {
  const [state, dispatch] = useReducer(assessmentReducer, initialState);

  const setStudent         = useCallback((s) => dispatch({ type: 'SET_STUDENT',      payload: s }), []);
  const setLesson          = useCallback((l) => dispatch({ type: 'SET_LESSON',       payload: l }), []);
  const startAssessment    = useCallback((lesson, allQuestions, previousWeakAreas = [], previousScore = null) =>
    dispatch({ type: 'START_ASSESSMENT', payload: { lesson, allQuestions, previousWeakAreas, previousScore } }), []);
  const saveResponse       = useCallback((r) => dispatch({ type: 'SAVE_RESPONSE',    payload: r }), []);
  const nextQuestion       = useCallback((targetLevel) => dispatch({ type: 'NEXT_QUESTION', payload: { targetLevel } }), []);
  const setExpression      = useCallback((e) => dispatch({ type: 'SET_EXPRESSION',   payload: e }), []);
  const resetAssessment    = useCallback(() => dispatch({ type: 'RESET' }),                         []);

  // Derived helpers
  const currentLevelKey   = `level${state.currentLevel}`;
  const currentQuestions  = state.allQuestions[currentLevelKey] || [];
  const currentQuestion   = currentQuestions[state.currentQuestionIdx] || null;
  const totalQuestions    = Object.values(state.allQuestions).flat().length;
  const answeredCount     = state.responses.length;

  return (
    <AssessmentContext.Provider value={{
      ...state,
      currentQuestion,
      currentQuestions,
      totalQuestions,
      answeredCount,
      setStudent,
      setLesson,
      startAssessment,
      saveResponse,
      nextQuestion,
      setExpression,
      resetAssessment,
    }}>
      {children}
    </AssessmentContext.Provider>
  );
};

// ── Hook ──────────────────────────────────────────────────────────────────────
export const useAssessment = () => {
  const ctx = useContext(AssessmentContext);
  if (!ctx) throw new Error('useAssessment must be used inside <AssessmentProvider>');
  return ctx;
};

export default AssessmentContext;
