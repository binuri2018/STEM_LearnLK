import { useEffect, useState } from 'react';
import { useVoice } from '../../context/VoiceContext';
import './ResearchAvatar.css';

const ResearchAvatar = ({ expression, learningState }) => {
  const { speak } = useVoice();
  const [avatarState, setAvatarState] = useState('neutral'); // neutral, happy, encouraged, thinking

  useEffect(() => {
    // Reaction logic based on emotion and learning state
    if (expression === 'happy' || expression === 'surprised') {
      setAvatarState('happy');
    } else if (expression === 'sad' || expression === 'angry' || expression === 'disgusted') {
      setAvatarState('encouraged');
      // Throttled TTS encouragement
      const lastEncouraged = localStorage.getItem('last_encouragement');
      const now = Date.now();
      if (!lastEncouraged || now - parseInt(lastEncouraged) > 30000) {
        speak("I can see this is challenging, but you're making progress. Let's keep going!");
        localStorage.setItem('last_encouragement', now.toString());
      }
    } else if (learningState?.includes('struggling') || learningState?.includes('confusion')) {
      setAvatarState('thinking');
    } else {
      setAvatarState('neutral');
    }
  }, [expression, learningState, speak]);

  return (
    <div className={`research-avatar-container ${avatarState}`}>
      <div className="avatar-floating-card">
        <div className="avatar-visual">
          <div className="avatar-eyes">
            <div className="eye left"></div>
            <div className="eye right"></div>
          </div>
          <div className="avatar-mouth"></div>
        </div>
        <div className="avatar-status-glow"></div>
      </div>
      <div className="avatar-speech-bubble">
        {avatarState === 'happy' && "Great job! Keep it up! 🌟"}
        {avatarState === 'encouraged' && "You've got this! Stay focused. 💪"}
        {avatarState === 'thinking' && "Analyzing patterns... 🧠"}
        {avatarState === 'neutral' && "Exploring STEM Quest 🚀"}
      </div>
    </div>
  );
};

export default ResearchAvatar;
