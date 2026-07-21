import React from 'react';
import { Bot, Activity } from 'lucide-react';
import LeadershipButton from './LeadershipButton';

export default function Header({ onGenerateReport, reportLoading }) {
  return (
    <header className="bg-slate-950/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-50 px-6 py-4">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Bot className="w-6 h-6 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold text-slate-100 tracking-tight">Monday.com BI Agent</h1>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <Activity className="w-3 h-3 mr-1 animate-pulse" />
                Live API
              </span>
            </div>
            <p className="text-xs text-slate-400">Executive Business Intelligence & Strategy Advisor</p>
          </div>
        </div>

        <LeadershipButton onClick={onGenerateReport} loading={reportLoading} />
      </div>
    </header>
  );
}
