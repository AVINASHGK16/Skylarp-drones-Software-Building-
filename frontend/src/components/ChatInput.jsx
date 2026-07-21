import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';

const SUGGESTIONS = [
  'What is our total pipeline value and conversion rate?',
  'Which sector generates the highest revenue?',
  'Summarize work order completion rates and unbilled backlog.',
];

export default function ChatInput({ onSendMessage, disabled }) {
  const [input, setInput] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!input.trim() || disabled) return;
    onSendMessage(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSuggestionClick = (suggestion) => {
    if (disabled) return;
    onSendMessage(suggestion);
  };

  return (
    <div className="border-t border-slate-800 bg-slate-950/90 backdrop-blur-md p-4 sticky bottom-0 z-40">
      <div className="max-w-4xl mx-auto space-y-3">
        {/* Suggestion Chips */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center">
            <Sparkles className="w-3 h-3 mr-1 text-indigo-400" />
            Suggested Prompts:
          </span>
          {SUGGESTIONS.map((suggestion, index) => (
            <button
              key={index}
              onClick={() => handleSuggestionClick(suggestion)}
              disabled={disabled}
              className="text-xs bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-indigo-300 border border-slate-800 hover:border-indigo-500/40 rounded-full px-3 py-1 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {suggestion}
            </button>
          ))}
        </div>

        {/* Form Input */}
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a strategic question about deals, revenue, or work orders... (Shift + Enter for new line)"
            disabled={disabled}
            className="w-full bg-slate-900 border border-slate-700/70 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-xl pl-4 pr-12 py-3 text-sm text-slate-100 placeholder-slate-500 resize-none outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          />

          <button
            type="submit"
            disabled={!input.trim() || disabled}
            className={`absolute right-2.5 p-2 rounded-lg transition-all duration-150 ${
              input.trim() && !disabled
                ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-500/25 active:scale-95 cursor-pointer'
                : 'bg-slate-800 text-slate-500 cursor-not-allowed'
            }`}
          >
            {disabled ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </form>

        <p className="text-[11px] text-center text-slate-500">
          Powered by Monday.com GraphQL API & Google Gemini AI • Data is securely processed in-memory
        </p>
      </div>
    </div>
  );
}
