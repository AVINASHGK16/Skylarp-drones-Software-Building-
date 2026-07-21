import React, { useState, useEffect } from 'react';
import { Bot, MessageSquare, LayoutDashboard } from 'lucide-react';
import LeadershipButton from './LeadershipButton';
import { checkHealth } from '../api/api';

export default function Header({ activeTab, setActiveTab, onGenerateReport, reportLoading }) {
  const [isConnected, setIsConnected] = useState(true);

  // Poll backend health status independently using GET /health
  useEffect(() => {
    let isMounted = true;

    const verifyBackendHealth = async () => {
      try {
        await checkHealth();
        if (isMounted) {
          // checkHealth only resolves for an HTTP 200 response from GET /health.
          setIsConnected(true);
        }
      } catch (err) {
        if (isMounted) {
          console.warn('Backend health check poll failed:', err);
          setIsConnected(false);
        }
      }
    };

    verifyBackendHealth();
    const interval = setInterval(verifyBackendHealth, 10000); // Poll every 10 seconds

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="bg-slate-950/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-50 px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Logo & Info */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 shrink-0">
            <Bot className="w-6 h-6 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold text-slate-100 tracking-tight">Monday.com BI Agent</h1>

              {/* Connection Status Badge (Strictly reflects GET /health) */}
              {isConnected ? (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 mr-1.5 animate-pulse" />
                  Backend Connected
                </span>
              ) : (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/20">
                  <span className="w-2 h-2 rounded-full bg-red-400 mr-1.5 animate-ping" />
                  Backend Offline
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400">Executive Business Intelligence & Strategy Advisor</p>
          </div>
        </div>

        {/* Navigation Tabs & Actions */}
        <div className="flex items-center space-x-3">
          {/* Tab Switcher */}
          <div className="flex bg-slate-900 border border-slate-800 p-1 rounded-xl">
            <button
              onClick={() => setActiveTab('chat')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'chat'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>AI Assistant</span>
            </button>

            <button
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'dashboard'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span>Dashboard</span>
            </button>
          </div>

          <LeadershipButton onClick={onGenerateReport} loading={reportLoading} />
        </div>
      </div>
    </header>
  );
}
