import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, FileSpreadsheet, Sparkles, Download, FileText } from 'lucide-react';
import DataQualityBadge from './DataQualityBadge';

export default function ChatMessage({ message }) {
  const isUser = message.sender === 'user';
  const isReport = message.isReport;

  /**
   * Export cached report as Markdown (.md) or Plain Text (.txt) file without regenerating
   */
  const handleExport = (format) => {
    if (!message.text) return;
    const dateStr = new Date().toISOString().slice(0, 10);
    const filename = `Executive_Leadership_Report_${dateStr}.${format}`;
    const mimeType = format === 'md' ? 'text/markdown;charset=utf-8;' : 'text/plain;charset=utf-8;';
    const blob = new Blob([message.text], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className={`py-4 px-4 sm:px-6 transition-colors ${isUser ? 'bg-slate-900/40' : 'bg-slate-800/30'}`}>
      <div className="max-w-4xl mx-auto flex space-x-4">
        {/* Avatar */}
        <div className="shrink-0 mt-0.5">
          {isUser ? (
            <div className="w-8 h-8 rounded-lg bg-slate-700 flex items-center justify-center text-slate-200">
              <User className="w-5 h-5" />
            </div>
          ) : isReport ? (
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-amber-500 to-orange-500 flex items-center justify-center text-white shadow-md shadow-amber-500/20">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
          ) : (
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
              <Bot className="w-5 h-5" />
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden space-y-2">
          {/* Header info & Export Actions */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-semibold text-slate-200">
                {isUser ? 'You' : isReport ? 'Executive Leadership Report' : 'BI Agent'}
              </span>
              <span className="text-xs text-slate-500">
                {message.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              {!isUser && !isReport && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <Sparkles className="w-2.5 h-2.5 mr-1" />
                  Gemini AI
                </span>
              )}
            </div>

            {/* Export buttons for Executive Leadership Report */}
            {isReport && (
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleExport('md')}
                  className="inline-flex items-center space-x-1 text-[11px] font-medium bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2.5 py-1 rounded-md transition-all cursor-pointer"
                  title="Export report as Markdown file"
                >
                  <Download className="w-3 h-3" />
                  <span>Export .MD</span>
                </button>
                <button
                  onClick={() => handleExport('txt')}
                  className="inline-flex items-center space-x-1 text-[11px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 px-2.5 py-1 rounded-md transition-all cursor-pointer"
                  title="Export report as Plain Text file"
                >
                  <FileText className="w-3 h-3" />
                  <span>Export .TXT</span>
                </button>
              </div>
            )}
          </div>

          {/* Message Text */}
          <div className="text-sm text-slate-300 leading-relaxed overflow-x-auto">
            {isUser ? (
              <p className="whitespace-pre-wrap">{message.text}</p>
            ) : (
              <div className="prose prose-invert max-w-none prose-headings:text-indigo-300 prose-headings:font-bold prose-h1:text-xl prose-h1:border-b prose-h1:border-slate-700 prose-h1:pb-2 prose-h2:text-lg prose-h3:text-base prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 prose-strong:text-slate-100 prose-code:text-indigo-300 prose-code:bg-slate-950/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-table:text-xs prose-th:bg-slate-800 prose-th:p-2 prose-td:p-2 prose-tr:border-slate-800">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.text}
                </ReactMarkdown>
              </div>
            )}
          </div>

          {/* Data Quality Notes */}
          {!isUser && message.notes && message.notes.length > 0 && (
            <DataQualityBadge notes={message.notes} />
          )}
        </div>
      </div>
    </div>
  );
}
