/**
 * utils/reportUtils.js
 * Helper functions for building the report display data from raw API response.
 */

/**
 * Convert a levelScores map object to a sorted array for charts/tables.
 * @param {object} levelScores  e.g. { "1": 66.7, "2": 33.3, "3": 100 }
 * @returns {Array} [{ level, label, score }]
 */
export const formatLevelScores = (levelScores = {}) => {
  const labels = { 1: 'Basic', 2: 'Concept', 3: 'Advanced' };
  return Object.entries(levelScores)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([level, score]) => ({
      level: Number(level),
      label: labels[Number(level)] || `Level ${level}`,
      score: Number(score),
    }));
};

/**
 * Convert a conceptPerformance map to sorted array (worst first).
 * @param {object} conceptPerformance e.g. { "Heart Structure": 75 }
 * @returns {Array} [{ concept, score }]
 */
export const formatConceptPerformance = (conceptPerformance = {}) => {
  return Object.entries(conceptPerformance)
    .map(([concept, score]) => ({ concept, score: Number(score) }))
    .sort((a, b) => a.score - b.score); // worst first
};

/**
 * Convert expressionFrequency map to sorted array for display.
 * @param {object} freq e.g. { neutral: 4, confused: 2 }
 * @returns {Array} [{ expression, count }]
 */
export const formatExpressionFrequency = (freq = {}) => {
  return Object.entries(freq)
    .map(([expression, count]) => ({ expression, count: Number(count) }))
    .sort((a, b) => b.count - a.count);
};

/**
 * Determine performance badge label from a score percentage.
 */
export const getPerformanceBadge = (score) => {
  if (score >= 85) return { label: 'Excellent', color: '#22c55e' };
  if (score >= 70) return { label: 'Good',      color: '#84cc16' };
  if (score >= 50) return { label: 'Fair',      color: '#f59e0b' };
  return              { label: 'Needs Work',  color: '#ef4444' };
};

/**
 * Format total time in seconds to a readable string.
 */
export const formatTotalTime = (seconds) => {
  if (!seconds) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
};

/**
 * Convert learning state distribution map to display array.
 */
export const formatLearningStates = (distribution = {}) => {
  const labels = {
    strong_understanding:  'Strong',
    partial_understanding: 'Partial',
    weak_understanding:    'Weak',
    needs_hint:            'Needs Hint',
  };
  const colors = {
    strong_understanding:  '#22c55e',
    partial_understanding: '#f59e0b',
    weak_understanding:    '#f97316',
    needs_hint:            '#ef4444',
  };
  return Object.entries(distribution)
    .map(([state, count]) => ({
      state,
      label: labels[state] || state,
      count: Number(count),
      color: colors[state] || '#6b7280',
    }))
    .sort((a, b) => b.count - a.count);
};

/**
 * Format the progress timeline returned by GET /api/reports/progress/:studentId/:lessonId
 * into a display-ready array.
 * @param {Array} history  Raw timeline entries from the API
 * @returns {Array}        Cleaned entries safe for rendering
 */
export const formatProgressHistory = (history = []) => {
  return history.map((entry) => ({
    sessionIndex:        entry.sessionIndex,
    sessionId:           entry.sessionId,
    date:                entry.date ? new Date(entry.date).toLocaleDateString() : '',
    totalScore:          Number(entry.totalScore),
    scoreDelta:          entry.scoreDelta !== null ? Number(entry.scoreDelta) : null,
    weakAreas:           entry.weakAreas || [],
    improvedConcepts:    entry.improvedConcepts || [],
    persistentWeakAreas: entry.persistentWeakAreas || [],
    hintUsageCount:      entry.hintUsageCount || 0,
  }));
};

/**
 * Format a Date as "Mon, 18 Aug" for deadlines and schedule labels.
 */
export const formatPlanDate = (date) =>
  date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });

/**
 * RESEARCH COMPONENT: Generate Pedagogical Study Plan
 * Analyzes performance and behavior to provide actionable, measurable study advice —
 * every card carries a numeric target and a real calendar deadline, and weak-area
 * advice is generated per-concept (using that concept's actual score) rather than
 * as one generic blob.
 * @param {object} report     Full report from the API
 * @param {Date}   startDate  Reference "today" — defaults to now, injectable for tests
 */
export const generateStudyPlan = (report, startDate = new Date()) => {
  const plan = [];
  const { totalScore, weakAreas = [], responses, totalTime, conceptPerformance = {} } = report;

  const reviewDeadline = new Date(startDate);
  reviewDeadline.setDate(reviewDeadline.getDate() + 7);
  const reviewDeadlineLabel = formatPlanDate(reviewDeadline);

  // 1. Conceptual Advice — one specific, measurable card per weak concept
  if (weakAreas.length > 0) {
    weakAreas.forEach((area) => {
      const current = Math.round(Number(conceptPerformance[area] ?? 0));
      const target = Math.min(90, current + 20);
      plan.push({
        type: 'conceptual',
        title: `Targeted Review: ${area}`,
        content: `You're at ${current}% on ${area}. Complete at least 4 practice questions on this topic and retake the quiz by ${reviewDeadlineLabel} — aim for ${target}%+.`,
        icon: '📚',
        metric: `${current}% → ${target}%`,
        deadline: reviewDeadlineLabel,
      });
    });
  } else if (totalScore > 90) {
    const challengeDeadline = new Date(startDate);
    challengeDeadline.setDate(challengeDeadline.getDate() + 3);
    const challengeDeadlineLabel = formatPlanDate(challengeDeadline);
    plan.push({
      type: 'conceptual',
      title: 'Advanced Challenge Recommended',
      content: `Mastery achieved at ${Math.round(totalScore)}%! Attempt 3 advanced-level problems on this topic by ${challengeDeadlineLabel} to extend your understanding.`,
      icon: '🚀',
      metric: `${Math.round(totalScore)}% mastery`,
      deadline: challengeDeadlineLabel,
    });
  }

  // 2. Behavioral Advice (Cognitive Load & Persistence) — quantified, with a deadline
  const avgLoad = responses?.reduce((sum, r) => sum + (r.cognitiveLoad || 0), 0) / (responses?.length || 1);

  if (avgLoad > 70) {
    plan.push({
      type: 'behavioral',
      title: 'Manage Cognitive Overload',
      content: `Mental effort ran high this session (${Math.round(avgLoad)}/100). Split your next session into three 10-minute blocks with 5-minute breaks, starting before ${reviewDeadlineLabel}.`,
      icon: '🧠',
      metric: `Load ${Math.round(avgLoad)}/100`,
      deadline: reviewDeadlineLabel,
    });
  } else if (avgLoad < 30 && totalScore > 80) {
    plan.push({
      type: 'behavioral',
      title: 'High Fluency Detected',
      content: `Low mental strain (${Math.round(avgLoad)}/100) with ${Math.round(totalScore)}% accuracy. Move up to the next difficulty tier by ${reviewDeadlineLabel}.`,
      icon: '⚡',
      metric: `Load ${Math.round(avgLoad)}/100`,
      deadline: reviewDeadlineLabel,
    });
  }

  if (totalTime > 300) {
    const minutes = Math.round(totalTime / 60);
    plan.push({
      type: 'behavioral',
      title: 'Strong Persistence Habits',
      content: `You spent ${minutes} min analysing these questions. Maintain an average session length of at least ${minutes} min across your next 3 sessions this week.`,
      icon: '🔥',
      metric: `${minutes} min/session`,
      deadline: reviewDeadlineLabel,
    });
  }

  // 4. Emotional/behavioral check-in — based on the session's dominant facial expression
  const { mostCommonExpression, hintUsageCount = 0 } = report;
  if (mostCommonExpression === 'confused' || mostCommonExpression === 'frustrated') {
    plan.push({
      type: 'behavioral',
      title: 'Emotional Check-in',
      content: `You looked ${mostCommonExpression} most often this session. Try a 5-minute brain-break puzzle before your next study block to reset focus.`,
      icon: '😌',
      metric: `Mostly ${mostCommonExpression}`,
      deadline: reviewDeadlineLabel,
    });
  }

  // 5. Hint-dependency insight — only fires when hints were leaned on heavily
  if (hintUsageCount >= 3) {
    plan.push({
      type: 'resource',
      title: 'Build Hint Independence',
      content: `You used ${hintUsageCount} hints this session. Before your next attempt, re-read the theory explanation for each weak concept before checking a hint.`,
      icon: '💡',
      metric: `${hintUsageCount} hints used`,
      deadline: reviewDeadlineLabel,
    });
  }

  // 3. Recommended Action — measurable, dated
  plan.push({
    type: 'resource',
    title: 'Suggested Next Action',
    content: totalScore < 60
      ? `Review the basic AR heart model again, then retake the Level 1 quiz by ${reviewDeadlineLabel} — target 70%+.`
      : `Explore the "Pathology & Disease" advanced module and complete it by ${reviewDeadlineLabel}.`,
    icon: '✨',
    metric: totalScore < 60 ? 'Target 70%+' : 'Module complete',
    deadline: reviewDeadlineLabel,
  });

  return plan;
};

/**
 * GAMIFICATION: Derive earned badges from a report + session history.
 * Purely deterministic (no external calls) — badges are computed from data
 * that already exists in the report and progress timeline.
 * @param {object} report            Full report from the API
 * @param {Array}  progressHistory   Output of formatProgressHistory()
 * @returns {Array} [{ icon, label, desc, color }]
 */
export const calculateBadges = (report, progressHistory = []) => {
  const badges = [];
  const { totalScore = 0, weakAreas = [], hintUsageCount = 0, responses = [] } = report || {};

  if (totalScore >= 95) {
    badges.push({ icon: '🏆', label: 'Perfect Score', desc: `Scored ${Math.round(totalScore)}% — near-flawless run.`, color: '#facc15' });
  } else if (totalScore >= 85) {
    badges.push({ icon: '🎯', label: 'High Achiever', desc: `Scored ${Math.round(totalScore)}% this session.`, color: '#22c55e' });
  }

  if (weakAreas.length === 0) {
    badges.push({ icon: '🎓', label: 'Concept Master', desc: 'No weak areas detected — full concept coverage.', color: '#a78bfa' });
  }

  if (hintUsageCount === 0) {
    badges.push({ icon: '🙋', label: 'Hint-Free Run', desc: 'Solved every question without a single hint.', color: '#38bdf8' });
  }

  const avgLoad = responses.length
    ? responses.reduce((s, r) => s + (r.cognitiveLoad || 0), 0) / responses.length
    : null;
  if (avgLoad !== null && avgLoad < 30) {
    badges.push({ icon: '🧠', label: 'Cool Under Pressure', desc: `Average cognitive load only ${Math.round(avgLoad)}/100.`, color: '#34d399' });
  }

  if (progressHistory.length >= 3) {
    badges.push({ icon: '🔥', label: `${progressHistory.length}-Session Streak`, desc: 'Consistently showing up to practice.', color: '#fb923c' });
  }

  const latest = progressHistory[progressHistory.length - 1];
  if (latest && latest.scoreDelta !== null && latest.scoreDelta >= 10) {
    badges.push({ icon: '📈', label: 'Most Improved', desc: `Up ${Math.round(latest.scoreDelta)}% from your last session.`, color: '#4ade80' });
  }

  return badges;
};

/** Clock start time (24h) for each time-of-day slot used in the timetable. */
const TIME_SLOTS = {
  Morning:      { hour: 8,  minute: 0 },
  Afternoon:    { hour: 14, minute: 0 },
  'After School': { hour: 16, minute: 0 },
  Evening:      { hour: 19, minute: 0 },
};

/** The time-of-day slot names, for building a picker when customizing a session. */
export const TIME_SLOT_NAMES = Object.keys(TIME_SLOTS);

const formatClock = (hour24, minute) => {
  const period = hour24 >= 12 ? 'PM' : 'AM';
  const hour12 = ((hour24 + 11) % 12) + 1;
  return `${hour12}:${String(minute).padStart(2, '0')} ${period}`;
};

/**
 * Turn a session's time-of-day slot + duration into a concrete clock range,
 * e.g. ('After School', 30) -> '4:00 PM – 4:30 PM'.
 */
export const formatTimeRange = (timeLabel, durationMinutes) => {
  const slot = TIME_SLOTS[timeLabel] || TIME_SLOTS['After School'];
  const startTotalMin = slot.hour * 60 + slot.minute;
  const endTotalMin = startTotalMin + durationMinutes;
  const start = formatClock(Math.floor(startTotalMin / 60) % 24, startTotalMin % 60);
  const end = formatClock(Math.floor(endTotalMin / 60) % 24, endTotalMin % 60);
  return `${start} – ${end}`;
};

const isWeekend = (date) => date.getDay() === 0 || date.getDay() === 6;

// Local-time YYYY-MM-DD — avoids the date shifting near midnight that toISOString() (UTC) would cause.
export const toLocalISODate = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

/**
 * Generate a personalised 7-day study timetable from assessment results.
 * Rolls forward from `startDate` (today by default) with real calendar dates —
 * not generic weekday labels — so each session carries an actual date and clock time.
 * Returns schedule data that can be scaled by duration preference in the UI.
 *
 * @param {object} report     Full report from the API
 * @param {Date}   startDate  First day of the plan — defaults to now, injectable for tests
 * @returns {{ schedule, intensity, weeklyMinutes, weekRangeLabel }}
 */
export const generateWeeklyTimetable = (report, startDate = new Date()) => {
  const totalScore        = Number(report?.totalScore ?? 0);
  const weakAreas         = report?.weakAreas ?? [];
  const conceptPerformance = report?.conceptPerformance ?? {};

  // Build prioritised topic queue: weak areas first, then 60-80% concepts
  const reviewTopics = weakAreas.map(a => ({
    name: a, type: 'review', priority: 'high',
  }));
  const practiceTopics = Object.entries(conceptPerformance)
    .filter(([, s]) => Number(s) >= 60 && Number(s) < 80)
    .map(([concept]) => ({ name: concept, type: 'practice', priority: 'medium' }));

  const allTopics = [...reviewTopics, ...practiceTopics];

  // High scorers: suggest challenge content instead
  if (allTopics.length === 0) {
    allTopics.push({ name: 'Advanced Concepts',  type: 'advanced',  priority: 'low' });
    allTopics.push({ name: 'Problem Solving',     type: 'practice',  priority: 'low' });
  }

  const intensity =
    totalScore >= 85 ? 'light' :
    totalScore >= 60 ? 'medium' : 'intensive';

  // Roll 7 real calendar days forward from startDate (today), not a fixed Mon–Sun grid.
  const planDates = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(startDate);
    d.setDate(d.getDate() + i);
    return d;
  });

  // Cumulative quiz lands on the first real weekend day in the window (falls back to the last day).
  const quizDayIdx = planDates.findIndex(isWeekend);
  const resolvedQuizDayIdx = quizDayIdx === -1 ? 6 : quizDayIdx;

  // Days that have active study sessions per intensity level
  const studyDays = {
    light:     [0, 2, 4, 5],
    medium:    [0, 1, 2, 3, 4, 5],
    intensive: [0, 1, 2, 3, 4, 5, 6],
  }[intensity];

  const mainDuration = { light: 25, medium: 30, intensive: 40 }[intensity];

  let topicIdx = 0;
  const schedule = planDates.map((date, dayIdx) => {
    const day      = date.toLocaleDateString('en-US', { weekday: 'long' });
    const short    = date.toLocaleDateString('en-US', { weekday: 'short' });
    const dateLabel = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    const isoDate  = toLocalISODate(date);
    const base     = { day, short, date, dateLabel, isoDate, isToday: dayIdx === 0 };

    if (!studyDays.includes(dayIdx)) {
      return { ...base, sessions: [], isRestDay: true };
    }

    const sessions = [];
    const topic = allTopics[topicIdx % allTopics.length];
    topicIdx++;

    // Primary session
    sessions.push({
      id:       `${isoDate}-main`,
      time:     isWeekend(date) ? 'Morning' : 'After School',
      topic:    topic.name,
      type:     topic.type,
      duration: mainDuration,
      priority: topic.priority,
    });

    // Secondary session on select days
    const addFlashcard =
      (intensity === 'medium'    && (dayIdx === 1 || dayIdx === 3)) ||
      (intensity === 'intensive' && dayIdx < 5);

    if (addFlashcard) {
      sessions.push({
        id:       `${isoDate}-flash`,
        time:     'Evening',
        topic:    'Concept Flashcards',
        type:     'flashcard',
        duration: 15,
        priority: 'medium',
      });
    }

    // Weekly cumulative quiz, on the first real weekend day of the plan
    if (dayIdx === resolvedQuizDayIdx) {
      sessions.push({
        id:       `${isoDate}-quiz`,
        time:     'Afternoon',
        topic:    'Weekly Practice Quiz',
        type:     'quiz',
        duration: intensity === 'intensive' ? 40 : 20,
        priority: 'high',
      });
    }

    return { ...base, sessions, isRestDay: false };
  });

  const weeklyMinutes = schedule.reduce(
    (sum, d) => sum + d.sessions.reduce((s, sess) => s + sess.duration, 0),
    0
  );

  const weekRangeLabel = `${schedule[0].dateLabel} – ${schedule[6].dateLabel}`;

  return { schedule, intensity, weeklyMinutes, weekRangeLabel };
};
