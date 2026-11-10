import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from 'recharts';
import { Calendar, Info } from 'lucide-react';
import { formatCurrency } from '../../utils/formatters';

function formatAxisVal(value) {
  if (value >= 1e7) return `₹${(value / 1e7).toFixed(1)} Cr`;
  if (value >= 1e5) return `₹${(value / 1e5).toFixed(1)} L`;
  return `₹${value}`;
}

export default function MonthlyPipelineChart({ monthlyPipeline }) {
  if (!monthlyPipeline || Object.keys(monthlyPipeline).length === 0) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg flex items-center justify-center min-h-[320px] text-slate-500 text-sm">
        No monthly pipeline trend data available.
      </div>
    );
  }

  const data = Object.entries(monthlyPipeline).map(([month, val]) => ({
    month,
    value: val,
  }));

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg flex flex-col justify-between">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-violet-500/10 text-violet-400 flex items-center justify-center shrink-0">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-base font-bold text-slate-100">Monthly Pipeline Trend</h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 inline-flex items-center">
                <Info className="w-3 h-3 mr-1" />
                Projected / Created Dates
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Grouped by actual close, tentative close, or lead creation date. 99.1% of valued pipeline uses tentative close dates.
            </p>
          </div>
        </div>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
            <XAxis dataKey="month" stroke="#94A3B8" fontSize={11} tickLine={false} />
            <YAxis stroke="#94A3B8" fontSize={11} tickFormatter={formatAxisVal} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0F172A',
                borderColor: '#334155',
                borderRadius: '0.75rem',
                color: '#F8FAFC',
                fontSize: '12px',
              }}
              formatter={(val) => [formatCurrency(val), 'Created / Projected Value']}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#8B5CF6"
              strokeWidth={3}
              dot={{ fill: '#C4B5FD', r: 4 }}
              activeDot={{ r: 6, fill: '#8B5CF6' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
