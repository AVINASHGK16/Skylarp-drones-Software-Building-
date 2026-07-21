import React, { useState } from 'react';
import Header from './components/Header';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import Dashboard from './components/dashboard/Dashboard';
import { askQuestion, getLeadershipReport } from './api/api';
import { AlertTriangle, X } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'dashboard'
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

    // Switch to chat tab to view report
    setActiveTab('chat');
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
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 font-sans antialiased selection:bg-indigo-500 selection:text-white overflow-hidden">
      {/* Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onGenerateReport={handleGenerateReport}
        reportLoading={reportLoading}
      />

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900/40 border-b border-red-500/30 px-6 py-2.5 flex items-center justify-between text-xs text-red-200">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-red-400 hover:text-red-200 transition-colors p-1 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Content View Tab Switching */}
      {activeTab === 'chat' ? (
        <>
          <ChatWindow messages={messages} loading={loading} />
          <ChatInput onSendMessage={handleSendMessage} disabled={loading || reportLoading} />
        </>
      ) : (
        <div className="flex-1 overflow-y-auto min-h-0 bg-slate-950">
          <Dashboard />
        </div>
      )}
    </div>
  );
}
