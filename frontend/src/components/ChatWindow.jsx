import React, { useRef, useEffect } from 'react';
import { Bot, BarChart3, PieChart, ShieldCheck, Sparkles, Loader2 } from 'lucide-react';
import ChatMessage from './ChatMessage';

export default function ChatWindow({ messages, loading }) {
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  return (
    <div className="flex-1 overflow-y-auto min-h-0 py-4 divide-y divide-slate-800/40">
      {messages.length === 0 ? (
        <div className="max-w-3xl mx-auto px-6 py-12 text-center space-y-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-tr from-indigo-500/20 to-violet-500/20 border border-indigo-500/30 text-indigo-400 shadow-xl">
            <Bot className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-slate-100 tracking-tight">
              Executive Business Intelligence Agent
            </h2>
            <p className="text-sm text-slate-400 max-w-lg mx-auto">
              Ask strategic questions regarding your Monday.com Deals sales funnel, Work Order execution, revenue breakdowns, and customer insights.
            </p>
          </div>

          {/* Feature Highlights Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left pt-4">
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center">
                <BarChart3 className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-semibold text-slate-200">Pipeline & Revenue</h3>
              <p className="text-xs text-slate-400">
                Track conversion rates, monthly deal values, and revenue by sector.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                <PieChart className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-semibold text-slate-200">Operations & Billing</h3>
              <p className="text-xs text-slate-400">
                Monitor work order completion, billed amounts, and unbilled backlog.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-semibold text-slate-200">Data Quality Audit</h3>
              <p className="text-xs text-slate-400">
                Automatic data cleaning caveats and quality reports for total transparency.
              </p>
            </div>
          </div>
        </div>
      ) : (
        messages.map((message, index) => (
          <ChatMessage key={index} message={message} />
        ))
      )}

      {/* Loading Skeleton Indicator */}
      {loading && (
        <div className="py-4 px-4 sm:px-6 bg-slate-800/20">
          <div className="max-w-4xl mx-auto flex space-x-4">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center text-white shrink-0 animate-pulse">
              <Bot className="w-5 h-5" />
            </div>
            <div className="flex items-center space-x-3 text-slate-400 text-sm py-1">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
              <span>Analyzing business metrics & generating insights...</span>
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
