import React, { useState } from 'react';
import Header from './components/Header';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import { askQuestion, getLeadershipReport } from './api/api';
import { AlertTriangle, X } from 'lucide-react';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState(null);

  /**
   * Handle sending user executive questions to POST /ask
   */
  const handleSendMessage = async (text) => {
    if (!text.trim() || loading) return;

    setError(null);
    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const userMessage = {
      sender: 'user',
      text: text.trim(),
      timestamp: timeString,
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const response = await askQuestion(text.trim());
      const agentMessage = {
        sender: 'agent',
        text: response.answer || 'No analysis available.',
        notes: response.data_quality_notes || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, agentMessage]);
    } catch (err) {
      console.error('Error sending question:', err);
      setError(err.message || 'Failed to connect to the BI Agent server.');
      const errorMessage = {
        sender: 'agent',
        text: `⚠️ **Connection Error**: Unable to reach backend server. ${err.message || 'Please check your connection.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handle generating Executive Leadership Report via GET /leadership-report
   */
  const handleGenerateReport = async () => {
    if (reportLoading) return;

    setError(null);
    setReportLoading(true);

    try {
      const response = await getLeadershipReport();
      const reportMessage = {
        sender: 'agent',
        isReport: true,
        text: response.report || '# Executive Report\nNo report data generated.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, reportMessage]);
    } catch (err) {
      console.error('Error generating report:', err);
      setError(err.message || 'Failed to generate Executive Leadership Report.');
    } finally {
      setReportLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 font-sans antialiased selection:bg-indigo-500 selection:text-white">
      {/* Header */}
      <Header onGenerateReport={handleGenerateReport} reportLoading={reportLoading} />

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900/40 border-b border-red-500/30 px-6 py-2.5 flex items-center justify-between text-xs text-red-200">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-red-400 hover:text-red-200 transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Main Chat Window */}
      <ChatWindow messages={messages} loading={loading} />

      {/* Chat Input Bar */}
      <ChatInput onSendMessage={handleSendMessage} disabled={loading || reportLoading} />
    </div>
  );
}
