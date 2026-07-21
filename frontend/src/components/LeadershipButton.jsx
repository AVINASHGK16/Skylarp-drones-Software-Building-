import React from 'react';
import { FileText, Loader2 } from 'lucide-react';

export default function LeadershipButton({ onClick, loading }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium text-sm transition-all duration-200 shadow-md ${
        loading
          ? 'bg-indigo-900/60 text-indigo-300 cursor-not-allowed border border-indigo-700/50'
          : 'bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white hover:shadow-indigo-500/25 active:scale-95 cursor-pointer'
      }`}
    >
      {loading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin text-indigo-300" />
          <span>Generating Report...</span>
        </>
      ) : (
        <>
          <FileText className="w-4 h-4" />
          <span>Generate Leadership Report</span>
        </>
      )}
    </button>
  );
}
