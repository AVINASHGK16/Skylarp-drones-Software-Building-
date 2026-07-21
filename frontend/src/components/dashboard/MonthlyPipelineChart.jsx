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
import { Calendar } from 'lucide-react';

function formatVal(value) {
  if (value >= 1e7) return `₹${(value / 1e7).toFixed(1)}Cr`;
  if (value >= 1e5) return `₹${(value / 1e5).toFixed(1)}L`;
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
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-violet-500/10 text-violet-400 flex items-center justify-center">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100">Monthly Pipeline Trend</h3>
            <p className="text-xs text-slate-400">Chronological pipeline value progression</p>
          </div>
        </div>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
            <XAxis dataKey="month" stroke="#94A3B8" fontSize={11} tickLine={false} />
            <YAxis stroke="#94A3B8" fontSize={11} tickFormatter={formatVal} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0F172A',
                borderColor: '#334155',
                borderRadius: '0.75rem',
                color: '#F8FAFC',
                fontSize: '12px',
              }}
              formatter={(val) => [`₹${val.toLocaleString('en-IN')}`, 'Pipeline Value']}
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
