import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { loginStudent, registerStudent } from '../api/authApi';
import { useAssessment } from '../context/AssessmentContext';
import { useVoice } from '../context/VoiceContext';
import './LoginPage.css';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Per-field rules. Each returns an error string, or '' when the value is valid.
const FIELD_RULES = {
  studentId: (v) => {
    const s = v.trim();
    if (!s) return 'Student ID is required';
    if (s.length < 3) return 'Student ID must be at least 3 characters';
    if (/\s/.test(s)) return 'Student ID cannot contain spaces';
    return '';
  },
  name: (v) => {
    const s = v.trim();
    if (!s) return 'Full name is required';
    if (s.length < 2) return 'Name must be at least 2 characters';
    if (!/^[\p{L}\p{M}][\p{L}\p{M}\s.'-]*$/u.test(s)) return 'Name has invalid characters';
    return '';
  },
  email: (v) => {
    const s = v.trim();
    if (!s) return 'Email address is required';
    if (!EMAIL_RE.test(s)) return 'Enter a valid email address';
    return '';
  },
  password: (v) => {
    if (!v) return 'Password is required';
    if (v.length < 6) return 'Password must be at least 6 characters';
    return '';
  },
};

const LoginPage = () => {
  const navigate = useNavigate();
  const { setStudent } = useAssessment();
  const { registerCommands, speak } = useVoice();

  const [mode, setMode]         = useState('login'); // 'login' | 'register'
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  // Form fields
  const [form, setForm] = useState({
    studentId: '', name: '', email: '', password: '', gradeLevel: 'Year 1',
  });
  // Per-field error messages, shown under each input.
  const [fieldErrors, setFieldErrors] = useState({});
  // Only surface a field's error once it's been touched (blur) or after a submit attempt.
  const [touched, setTouched] = useState({});

  // Register Voice Commands
  useEffect(() => {
    const unregister = registerCommands('login-page', {
      'register': () => { setMode('register'); speak("Switched to registration mode."); },
      'login': () => { setMode('login'); speak("Switched to login mode."); },
      'teacher': () => { speak("Navigating to teacher dashboard."); navigate('/teacher'); },
      'dashboard': () => { speak("Navigating to teacher dashboard."); navigate('/teacher'); }
    });
    return unregister;
  }, [navigate, registerCommands, speak]);

  // Which fields apply in the current mode.
  const activeFields = mode === 'register'
    ? ['studentId', 'name', 'email', 'password']
    : ['email', 'password'];

  const validateField = (field, value) => FIELD_RULES[field](value);

  const validateAll = () => {
    const next = {};
    for (const field of activeFields) {
      const msg = validateField(field, form[field]);
      if (msg) next[field] = msg;
    }
    return next;
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
    setError('');
    // Live-clear a field's error as soon as it becomes valid again.
    if (touched[name]) {
      setFieldErrors((fe) => ({ ...fe, [name]: validateField(name, value) }));
    }
  };

  const handleBlur = (e) => {
    const { name, value } = e.target;
    setTouched((t) => ({ ...t, [name]: true }));
    setFieldErrors((fe) => ({ ...fe, [name]: validateField(name, value) }));
  };

  const switchMode = (next) => {
    setMode(next);
    setError('');
    setFieldErrors({});
    setTouched({});
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validateAll();
    setFieldErrors(errs);
    setTouched(Object.fromEntries(activeFields.map((f) => [f, true])));
    if (Object.keys(errs).length > 0) {
      setError('Please fix the highlighted fields.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      let data;
      if (mode === 'login') {
        data = await loginStudent({ email: form.email.trim(), password: form.password });
      } else {
        data = await registerStudent({
          studentId: form.studentId.trim(),
          name: form.name.trim(),
          email: form.email.trim(),
          password: form.password,
          gradeLevel: form.gradeLevel,
        });
      }

      // Persist token and student info
      localStorage.setItem('stemToken',   data.data.token);
      localStorage.setItem('stemStudent', JSON.stringify(data.data));
      setStudent(data.data);
      navigate('/lesson-complete');
    } catch (err) {
      setError(err.response?.data?.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const showError = (field) => Boolean(fieldErrors[field] && touched[field]);
  const fieldClass = (field) => `form-group${showError(field) ? ' has-error' : ''}`;
  const renderFieldError = (field) =>
    showError(field) ? <span className="field-error">{fieldErrors[field]}</span> : null;

  return (
    <div className="login-page">
      <div className="login-card">
        {/* Header */}
        <div className="login-header">
          <div className="login-logo">🧠</div>
          <h1 className="login-title">STEM Assessment</h1>
          <p className="login-subtitle">Behavior-Aware Multi-Level Learning System</p>
        </div>

        {/* Tab switch */}
        <div className="login-tabs">
          <button id="tab-login"    type="button" className={`tab-btn ${mode === 'login'    ? 'active' : ''}`} onClick={() => switchMode('login')}>Login</button>
          <button id="tab-register" type="button" className={`tab-btn ${mode === 'register' ? 'active' : ''}`} onClick={() => switchMode('register')}>Register</button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="login-form" noValidate>
          {mode === 'register' && (
            <>
              <div className={fieldClass('studentId')}>
                <label htmlFor="studentId">Student ID</label>
                <input
                  id="studentId" name="studentId" type="text"
                  placeholder="e.g. ST22001234"
                  value={form.studentId}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  aria-invalid={showError('studentId')}
                />
                {renderFieldError('studentId')}
              </div>
              <div className={fieldClass('name')}>
                <label htmlFor="name">Full Name</label>
                <input
                  id="name" name="name" type="text"
                  placeholder="Your full name"
                  value={form.name}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  aria-invalid={showError('name')}
                />
                {renderFieldError('name')}
              </div>
            </>
          )}

          <div className={fieldClass('email')}>
            <label htmlFor="email">Email Address</label>
            <input
              id="email" name="email" type="email"
              placeholder="student@university.edu"
              value={form.email}
              onChange={handleChange}
              onBlur={handleBlur}
              aria-invalid={showError('email')}
            />
            {renderFieldError('email')}
          </div>

          <div className={fieldClass('password')}>
            <label htmlFor="password">Password</label>
            <input
              id="password" name="password" type="password"
              placeholder="••••••••"
              value={form.password}
              onChange={handleChange}
              onBlur={handleBlur}
              aria-invalid={showError('password')}
            />
            {renderFieldError('password')}
            {mode === 'register' && !showError('password') && (
              <span className="field-hint">At least 6 characters</span>
            )}
          </div>

          {error && <div className="form-error">⚠️ {error}</div>}

          <button id="btn-submit" type="submit" className="btn-primary" disabled={loading}>
            {loading ? <span className="spinner" /> : mode === 'login' ? '🔐 Login' : '📝 Create Account'}
          </button>

          <div style={{ marginTop: '20px', textAlign: 'center', opacity: 0.6, fontSize: '12px' }}>
            <span
              onClick={() => navigate('/teacher')}
              style={{ cursor: 'pointer', color: '#6366f1', textDecoration: 'underline' }}
            >
              👩‍🏫 Teacher Portal
            </span>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
