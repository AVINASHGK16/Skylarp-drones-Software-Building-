import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';
import { Building2 } from 'lucide-react';

const COLORS = [
  '#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899',
  '#06B6D4', '#6366F1', '#14B8A6', '#F97316', '#A855F7',
];

function formatVal(value) {
  if (value >= 1e7) return `₹${(value / 1e7).toFixed(1)}Cr`;
  if (value >= 1e5) return `₹${(value / 1e5).toFixed(1)}L`;
  return `₹${value}`;
}

export default function RevenueBySectorChart({ revenueBySector }) {
  if (!revenueBySector || Object.keys(revenueBySector).length === 0) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg flex items-center justify-center min-h-[320px] text-slate-500 text-sm">
        No sector revenue data available.
      </div>
    );
  }

  const data = Object.entries(revenueBySector).map(([sector, val]) => ({
    sector,
    value: val,
  }));

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <Building2 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100">Revenue by Sector</h3>
            <p className="text-xs text-slate-400">Total pipeline deal distribution across industries</p>
          </div>
        </div>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
            <XAxis
              dataKey="sector"
              stroke="#94A3B8"
              fontSize={11}
              tickLine={false}
              interval={0}
              angle={-25}
              textAnchor="end"
            />
            <YAxis
              stroke="#94A3B8"
              fontSize={11}
              tickFormatter={formatVal}
              tickLine={false}
            />
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
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
