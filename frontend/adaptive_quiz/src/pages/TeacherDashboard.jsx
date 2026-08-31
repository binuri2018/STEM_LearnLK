import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useVoice } from '../context/VoiceContext';
import { getExpressionEmoji } from '../utils/quizLogic';
import { getTeacherKey, setTeacherKey, clearTeacherKey } from '../utils/teacherAuth';
import QuestionGeneratorPanel from '../components/teacher/QuestionGeneratorPanel';
import './ReportPage.css'; // Reuse report styles

const TeacherDashboard = () => {
  const [reports, setReports] = useState([]);
  const [, setLoading] = useState(true);
  const [needsKey, setNeedsKey] = useState(() => !getTeacherKey());
  const [keyInput, setKeyInput] = useState('');
  const [keyError, setKeyError] = useState('');
  const navigate = useNavigate();
  const { registerCommands, speak } = useVoice();

  // Export Logic
  const handleExport = () => {
    if (reports.length === 0) return;
    speak("Exporting research data to JSON format.");
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(reports, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href",     dataStr);
    downloadAnchorNode.setAttribute("download", "research_data_export.json");
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  // Register Voice Commands
  useEffect(() => {
    const unregister = registerCommands('teacher-dashboard', {
      'export': handleExport,
      'download': handleExport,
      'logout': () => { speak("Logging out."); clearTeacherKey(); navigate('/login'); },
      'login': () => { navigate('/login'); }
    });
    return unregister;
  }, [reports, navigate, registerCommands, speak]);

  const fetchReports = (key) => {
    const API_URL = import.meta.env.VITE_API_URL || '/api/adaptive-quiz';
    setLoading(true);
    // Use plain fetch — no 401 redirect interceptor — teacher dashboard has no student login
    const timer = setTimeout(() => setLoading(false), 8000); // never block page > 8s
    fetch(`${API_URL}/reports/all`, { headers: { 'X-Teacher-Key': key } })
      .then(r => {
        if (r.status === 403) {
          clearTeacherKey();
          setNeedsKey(true);
          setKeyError('Invalid teacher key — try again.');
          throw new Error('Invalid teacher key');
        }
        return r.json();
      })
      .then(data => { setReports(data.data || []); })
      .catch(() => { /* backend down or bad key — handled above, or show empty state */ })
      .finally(() => { clearTimeout(timer); setLoading(false); });
  };

  useEffect(() => {
    if (!needsKey) fetchReports(getTeacherKey());
  }, []);

  const handleKeySubmit = (e) => {
    e.preventDefault();
    const key = keyInput.trim();
    if (!key) return;
    setTeacherKey(key);
    setKeyError('');
    setNeedsKey(false);
    fetchReports(key);
  };

  if (needsKey) {
    return (
      <div className="report-page" style={{ padding: '60px 24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <form onSubmit={handleKeySubmit} style={{
          background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(12px)',
          border: '1px solid rgba(15,23,42,0.05)', borderRadius: '16px',
          padding: '40px 32px', maxWidth: '360px', width: '100%', textAlign: 'center',
        }}>
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>🔑</div>
          <h2 style={{ color: '#111827', fontSize: '20px', margin: '0 0 8px' }}>Teacher Access</h2>
          <p style={{ color: '#6b7280', fontSize: '13px', margin: '0 0 20px' }}>
            Enter the shared teacher key to view classroom research data.
          </p>
          <input
            type="password"
            autoFocus
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="Teacher access key"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '10px 14px', borderRadius: '8px',
              border: '1px solid #c2ccd9', background: 'rgba(15,23,42,0.08)', color: '#111827',
              fontSize: '14px', marginBottom: '12px',
            }}
          />
          {keyError && <p style={{ color: '#dc2626', fontSize: '12px', margin: '0 0 12px' }}>{keyError}</p>}
          <button type="submit" style={{
            width: '100%', padding: '10px', borderRadius: '8px', border: 'none',
            background: '#6366f1', color: '#fff', fontWeight: '700', fontSize: '14px', cursor: 'pointer',
          }}>
            Continue
          </button>
          <button
            type="button"
            onClick={() => navigate('/login')}
            style={{ marginTop: '14px', background: 'transparent', border: 'none', color: '#9ca3af', fontSize: '12px', cursor: 'pointer' }}
          >
            ← Return to Main Login
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="report-page" style={{ padding: '60px 24px' }}>
      <div className="report-container" style={{ maxWidth: '1100px' }}>

        {/* Header Section */}
        <div className="report-header" style={{ marginBottom: '50px' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>🏫</div>
          <h1 className="report-title" style={{ fontSize: '36px', letterSpacing: '-0.5px' }}>Teacher Dashboard</h1>
          <p className="report-meta" style={{ fontSize: '16px', color: '#6b7280' }}>
            Real-time Monitoring of Classroom-wide Behavioral Engagement & Performance
          </p>
        </div>

        {/* Question Generator */}
        <QuestionGeneratorPanel />

        {/* Dashboard Content */}
        <div className="report-section" style={{
          background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(12px)',
          border: '1px solid rgba(15,23,42,0.05)', padding: '32px'
        }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px' }}>
            <div>
              <h3 className="section-title" style={{ color:'#6366f1', margin:0 }}>📊 Student Performance Overview</h3>
              {reports.length > 0 && (
                <p style={{ margin:'4px 0 0', fontSize:'12px', color:'#9ca3af' }}>
                  {Object.keys(reports.reduce((a,r)=>({...a,[r.studentId]:1}),{})).length} students · {reports.length} sessions total
                </p>
              )}
            </div>
            {reports.length > 0 && (
              <button onClick={handleExport} style={{
                background:'rgba(99,102,241,0.1)', border:'1px solid #6366f1', color:'#4f46e5',
                padding:'8px 16px', borderRadius:'8px', fontSize:'12px', fontWeight:'700', cursor:'pointer'
              }}>📥 Export Data (JSON)</button>
            )}
          </div>

          {reports.length === 0 ? (
            <div style={{ textAlign:'center', padding:'60px 20px', color:'#4b5563' }}>
              <div style={{ fontSize:'40px', marginBottom:'16px', opacity:0.4 }}>📂</div>
              <p style={{ fontSize:'16px', fontWeight:'600', margin:0 }}>No Data Yet</p>
              <p style={{ fontSize:'13px', marginTop:'8px', color:'#9ca3af' }}>Student behavioral data will appear here once assessments are completed.</p>
            </div>
          ) : (
            <StudentCards reports={reports} getExpressionEmoji={getExpressionEmoji} />
          )}
        </div>

        {/* Footer Actions */}
        <div className="report-actions" style={{ marginTop: '40px', justifyContent: 'center' }}>
          <button className="btn-logout" onClick={() => { clearTeacherKey(); navigate('/login'); }} style={{ minWidth: '200px' }}>
            ← Return to Main Login
          </button>
        </div>
      </div>

      <style>{`
        .dashboard-row:hover {
          background: rgba(15,23,42,0.05) !important;
          transform: scale(1.01);
        }
      `}</style>
    </div>
  );
};

// ── Student Cards ─────────────────────────────────────────────────────────────
function StudentCards({ reports, getExpressionEmoji }) {
  const [expanded, setExpanded] = React.useState({});

  // Group all sessions by studentId, sorted oldest→newest
  const groups = React.useMemo(() => {
    const map = {};
    reports.forEach(r => { (map[r.studentId] = map[r.studentId] || []).push(r); });
    return Object.entries(map).map(([studentId, sessions]) => {
      sessions.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
      const scores    = sessions.map(s => Math.round(s.totalScore));
      const avg       = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
      const latest    = scores[scores.length - 1];
      const trend     = scores.length > 1 ? latest - scores[0] : null;
      const avgHints  = Math.round(sessions.reduce((a, s) => a + (s.hintUsageCount || 0), 0) / sessions.length);
      const emotion   = sessions[sessions.length - 1].mostCommonExpression || 'neutral';
      const weakAreas = [...new Set(sessions[sessions.length - 1].weakAreas || [])];
      const status    = avg >= 75 ? 'mastery' : avg >= 50 ? 'progressing' : 'intervention';
      return { studentId, sessions, scores, avg, latest, trend, avgHints, emotion, weakAreas, status };
    }).sort((a, b) => a.avg - b.avg); // worst performers first
  }, [reports]);

  const STATUS = {
    mastery:      { label:'Mastery',      color:'#22c55e', bg:'rgba(34,197,94,0.12)',   border:'rgba(34,197,94,0.25)' },
    progressing:  { label:'Progressing',  color:'#f59e0b', bg:'rgba(245,158,11,0.12)',  border:'rgba(245,158,11,0.25)' },
    intervention: { label:'Needs Support',color:'#ef4444', bg:'rgba(239,68,68,0.12)',   border:'rgba(239,68,68,0.25)' },
  };

  return (
    <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(320px,1fr))', gap:'16px' }}>
      {groups.map(g => {
        const st = STATUS[g.status];
        const isOpen = expanded[g.studentId];
        return (
          <div key={g.studentId} style={{
            background:'rgba(15,23,42,0.05)', border:`1px solid ${st.border}`,
            borderRadius:'16px', overflow:'hidden',
          }}>
            {/* Card header */}
            <div style={{ padding:'18px 20px', borderBottom:'1px solid rgba(15,23,42,0.05)' }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'12px' }}>
                <div style={{ display:'flex', alignItems:'center', gap:'12px' }}>
                  {/* Avatar */}
                  <div style={{
                    width:'42px', height:'42px', borderRadius:'50%',
                    background:`linear-gradient(135deg,${st.color}44,${st.color}22)`,
                    border:`1px solid ${st.border}`,
                    display:'flex', alignItems:'center', justifyContent:'center',
                    fontSize:'16px', fontWeight:'800', color:st.color,
                  }}>
                    {g.studentId.slice(0,2).toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight:'800', color:'#111827', fontSize:'15px' }}>{g.studentId}</div>
                    <div style={{ fontSize:'11px', color:'#9ca3af' }}>
                      {g.sessions.length} session{g.sessions.length > 1 ? 's' : ''} · {g.sessions[0].lessonId}
                    </div>
                  </div>
                </div>
                <span style={{
                  padding:'4px 10px', borderRadius:'20px', fontSize:'10px', fontWeight:'800',
                  textTransform:'uppercase', letterSpacing:'0.5px',
                  background:st.bg, color:st.color, border:`1px solid ${st.border}`,
                }}>{st.label}</span>
              </div>

              {/* Score row */}
              <div style={{ display:'flex', alignItems:'flex-end', gap:'16px', marginBottom:'12px' }}>
                <div>
                  <div style={{ fontSize:'11px', color:'#9ca3af', marginBottom:'2px', textTransform:'uppercase', letterSpacing:'0.4px' }}>Latest</div>
                  <div style={{ fontSize:'32px', fontWeight:'800', color:st.color, lineHeight:1 }}>{g.latest}%</div>
                </div>
                <div>
                  <div style={{ fontSize:'11px', color:'#9ca3af', marginBottom:'2px', textTransform:'uppercase', letterSpacing:'0.4px' }}>Average</div>
                  <div style={{ fontSize:'20px', fontWeight:'700', color:'#4b5563', lineHeight:1 }}>{g.avg}%</div>
                </div>
                {g.trend !== null && (
                  <div style={{ marginLeft:'auto', textAlign:'right' }}>
                    <div style={{ fontSize:'11px', color:'#9ca3af', marginBottom:'2px' }}>Trend</div>
                    <div style={{
                      fontSize:'15px', fontWeight:'800',
                      color: g.trend > 0 ? '#22c55e' : g.trend < 0 ? '#ef4444' : '#4b5563',
                    }}>
                      {g.trend > 0 ? '▲' : g.trend < 0 ? '▼' : '→'} {Math.abs(g.trend)}%
                    </div>
                  </div>
                )}
              </div>

              {/* Score progress bars (last 5 sessions) */}
              {g.scores.length > 1 && (
                <div style={{ display:'flex', alignItems:'flex-end', gap:'4px', height:'28px', marginBottom:'12px' }}>
                  {g.scores.slice(-7).map((s, i) => (
                    <div key={i} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:'2px' }}>
                      <div style={{
                        width:'100%', borderRadius:'3px 3px 0 0',
                        height:`${Math.max(4, (s / 100) * 24)}px`,
                        background: i === g.scores.slice(-7).length - 1 ? st.color : 'rgba(255,255,255,0.1)',
                        transition:'height 0.4s ease',
                      }}/>
                    </div>
                  ))}
                </div>
              )}

              {/* Emotion + hints row */}
              <div style={{ display:'flex', gap:'8px', flexWrap:'wrap' }}>
                <span style={{
                  padding:'4px 10px', borderRadius:'8px', fontSize:'12px',
                  background:'rgba(15,23,42,0.05)', border:'1px solid rgba(15,23,42,0.05)', color:'#4b5563',
                }}>
                  {getExpressionEmoji(g.emotion)} {g.emotion}
                </span>
                <span style={{
                  padding:'4px 10px', borderRadius:'8px', fontSize:'12px',
                  background: g.avgHints > 4 ? 'rgba(239,68,68,0.1)' : 'rgba(15,23,42,0.05)',
                  border: g.avgHints > 4 ? '1px solid rgba(239,68,68,0.2)' : '1px solid rgba(15,23,42,0.05)',
                  color: g.avgHints > 4 ? '#dc2626' : '#4b5563',
                }}>
                  💡 {g.avgHints} avg hints
                </span>
                {g.weakAreas.slice(0,2).map(w => (
                  <span key={w} style={{
                    padding:'4px 10px', borderRadius:'8px', fontSize:'11px',
                    background:'rgba(239,68,68,0.08)', border:'1px solid rgba(239,68,68,0.15)', color:'#dc2626',
                  }}>⚠ {w}</span>
                ))}
              </div>
            </div>

            {/* Expandable session history */}
            <button
              onClick={() => setExpanded(p => ({ ...p, [g.studentId]: !p[g.studentId] }))}
              style={{
                width:'100%', padding:'10px 20px', background:'transparent',
                border:'none', cursor:'pointer', color:'#9ca3af', fontSize:'12px',
                display:'flex', alignItems:'center', justifyContent:'space-between',
              }}
            >
              <span>Session history ({g.sessions.length})</span>
              <span>{isOpen ? '▲' : '▼'}</span>
            </button>

            {isOpen && (
              <div style={{ padding:'0 20px 16px', display:'flex', flexDirection:'column', gap:'6px' }}>
                {g.sessions.map((s, i) => (
                  <div key={s.sessionId} style={{
                    display:'flex', alignItems:'center', gap:'10px',
                    padding:'8px 12px', borderRadius:'8px',
                    background: i === g.sessions.length-1 ? `${st.color}11` : 'rgba(15,23,42,0.05)',
                    border: i === g.sessions.length-1 ? `1px solid ${st.border}` : '1px solid rgba(15,23,42,0.05)',
                  }}>
                    <span style={{ fontSize:'11px', color:'#9ca3af', width:'20px' }}>#{i+1}</span>
                    <span style={{
                      fontWeight:'700', fontSize:'14px',
                      color: s.totalScore >= 75 ? '#22c55e' : s.totalScore >= 50 ? '#f59e0b' : '#ef4444',
                      width:'46px',
                    }}>{Math.round(s.totalScore)}%</span>
                    <span style={{ fontSize:'11px', color:'#9ca3af', flex:1 }}>
                      {s.createdAt ? new Date(s.createdAt).toLocaleDateString() : '—'}
                    </span>
                    <span style={{ fontSize:'11px', color:'#9ca3af' }}>💡 {s.hintUsageCount || 0}</span>
                    <span style={{ fontSize:'13px' }}>{getExpressionEmoji(s.mostCommonExpression)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default TeacherDashboard;
