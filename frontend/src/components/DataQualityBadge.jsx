import React, { useState } from 'react';
import { ShieldAlert, ChevronDown, ChevronUp } from 'lucide-react';

export default function DataQualityBadge({ notes }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!notes || notes.length === 0) return null;

  return (
    <div className="mt-3 border border-amber-500/30 bg-amber-950/20 rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 flex items-center justify-between text-amber-300 bg-amber-900/30 hover:bg-amber-900/40 transition-colors font-medium cursor-pointer"
      >
        <div className="flex items-center space-x-2">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
          <span>Data Quality Notes ({notes.length})</span>
        </div>
        {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {isOpen && (
        <ul className="p-3 space-y-1.5 text-amber-200/90 list-disc list-inside bg-amber-950/40 border-t border-amber-500/20">
          {notes.map((note, index) => (
            <li key={index} className="leading-relaxed">
              {note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
