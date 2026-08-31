import { useEffect, useRef, useState } from 'react';
import { useVoice } from '../../context/VoiceContext';
import './GlobalVoiceController.css';

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const GlobalVoiceController = () => {
  const {
    isListening, setIsListening,
    setError, handleTranscript,
    speak,
  } = useVoice();

  const [debugLog, setDebugLog] = useState(SpeechRecognition ? 'System ready' : '❌ Not Supported');
  const [liveTranscript, setLiveTranscript] = useState('');
  const recognitionRef = useRef(null);
  const handleTranscriptRef = useRef(handleTranscript);
  const isListeningRef = useRef(isListening);

  useEffect(() => { handleTranscriptRef.current = handleTranscript; }, [handleTranscript]);
  useEffect(() => { isListeningRef.current = isListening; }, [isListening]);

  useEffect(() => {
    if (!SpeechRecognition) return;

    const initRecognition = () => {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setDebugLog('🟢 Listening...');
        setError(null);
      };
      
      recognition.onend = () => {
        if (isListeningRef.current) {
          setDebugLog('🔄 Auto-Restarting...');
          setTimeout(() => {
            if (isListeningRef.current) {
              try { recognition.start(); } catch (e) { console.log('Restart failed'); }
            }
          }, 300);
        } else {
          setDebugLog('⚪ Mic Offline');
        }
      };

      recognition.onerror = (event) => {
        setDebugLog(`⚠️ Error: ${event.error}`);
        if (event.error === 'not-allowed') {
          setIsListening(false);
          setError('Mic Denied');
        }
      };

      recognition.onresult = (event) => {
        const result = event.results[event.results.length - 1];
        const transcript = result[0].transcript;
        setLiveTranscript(transcript);
        
        if (result.isFinal) {
          setDebugLog(`👂 Heard: "${transcript}"`);
          handleTranscriptRef.current(transcript);
          // Clear live transcript after a delay
          setTimeout(() => setLiveTranscript(''), 2000);
        }
      };

      recognitionRef.current = recognition;
    };

    if (!recognitionRef.current) initRecognition();

    if (isListening) {
      try { recognitionRef.current.start(); } catch (e) {
        // Recognition might already be running, that's fine
      }
    } else {
      try { recognitionRef.current.stop(); } catch (e) {}
    }

    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (e) {}
      }
    };
  }, [isListening, setIsListening, setError]);

  const toggleListening = () => {
    if (isListening) {
      setIsListening(false);
      speak("Voice control disabled");
    } else {
      setError(null);
      setIsListening(true);
      speak("Voice control activated. I am listening.");
    }
  };

  return (
    <div className={`global-voice-indicator ${isListening ? 'active' : 'inactive'}`}>
      <div className="voice-visualizer" onClick={toggleListening}>
        <div className="pulse-ring"></div>
        <div className="mic-icon">{isListening ? '🎤' : '🔇'}</div>
      </div>
      
      <div className="voice-label">
        <span className="status-text">{debugLog}</span>
        {liveTranscript && (
          <div className="live-bubble">
             "{liveTranscript}"
          </div>
        )}
      </div>
    </div>
  );
};

export default GlobalVoiceController;
