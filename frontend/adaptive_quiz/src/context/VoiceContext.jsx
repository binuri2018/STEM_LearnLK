/* eslint-disable react-refresh/only-export-components -- provider + useVoice hook intentionally colocated */
import { createContext, useContext, useState, useCallback, useRef } from 'react';

const VoiceContext = createContext();

export const useVoice = () => useContext(VoiceContext);

export const VoiceProvider = ({ children }) => {
  const [isListening, setIsListening] = useState(false);
  const [lastCommand, setLastCommand] = useState('');
  const [error, setError] = useState(null);
  
  // Registry for page-specific commands
  const commandsRef = useRef({});

  const registerCommands = useCallback((id, commandMap) => {
    commandsRef.current[id] = commandMap;
    return () => {
      delete commandsRef.current[id];
    };
  }, []);

  const speak = useCallback((text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.1; // Slightly higher pitch for the AI companion vibe
    window.speechSynthesis.speak(utterance);
  }, []);

  const [, setIsProcessing] = useState(false);
  const isProcessingRef = useRef(false);

  const handleTranscript = useCallback((transcript) => {
    if (isProcessingRef.current) return;
    const cmd = transcript.toLowerCase().trim();
    setLastCommand(cmd);

    // Get all phrases across all registered sets
    const allCommands = [];
    Object.values(commandsRef.current).forEach(map => {
      Object.entries(map).forEach(([phrase, action]) => {
        allCommands.push({ phrase: phrase.toLowerCase(), action });
      });
    });

    // Sort by length descending to match most specific first
    allCommands.sort((a, b) => b.phrase.length - a.phrase.length);

    for (const item of allCommands) {
      if (cmd.includes(item.phrase)) {
        console.log(`✅ Smart Match: "${item.phrase}"`);
        isProcessingRef.current = true;
        setIsProcessing(true); // Still update state for UI if needed
        
        item.action();

        // Cooldown to prevent double-triggering
        setTimeout(() => {
          isProcessingRef.current = false;
          setIsProcessing(false);
        }, 1000);
        break; 
      }
    }
  }, []); // Stable reference

  return (
    <VoiceContext.Provider value={{
      isListening,
      setIsListening,
      lastCommand,
      error,
      setError,
      registerCommands,
      handleTranscript,
      speak
    }}>
      {children}
    </VoiceContext.Provider>
  );
};
