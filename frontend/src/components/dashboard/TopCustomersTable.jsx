import React from 'react';
import { Users, Award } from 'lucide-react';

export default function TopCustomersTable({ topCustomers }) {
  if (!topCustomers || topCustomers.length === 0) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg text-slate-500 text-sm text-center">
        No top customer data available.
      </div>
    );
  }

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg">
      <div className="flex items-center space-x-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
          <Award className="w-4 h-4" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-100">Top 10 Customers</h3>
          <p className="text-xs text-slate-400">Ranked by total billed revenue realization</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider text-[11px] border-b border-slate-800">
            <tr>
              <th className="py-2.5 px-3">Rank</th>
              <th className="py-2.5 px-3">Customer Code</th>
              <th className="py-2.5 px-3 text-right">Billed Revenue</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {topCustomers.map((item, index) => (
              <tr key={index} className="hover:bg-slate-800/40 transition-colors">
                <td className="py-2.5 px-3 font-semibold text-slate-400">
                  <span className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] ${
                    index === 0
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      : index === 1
                      ? 'bg-slate-400/20 text-slate-300 border border-slate-400/30'
                      : index === 2
                      ? 'bg-amber-700/20 text-amber-500 border border-amber-700/30'
                      : 'text-slate-500'
                  }`}>
                    {index + 1}
                  </span>
                </td>
                <td className="py-2.5 px-3 font-medium text-slate-200">{item.customer}</td>
                <td className="py-2.5 px-3 text-right font-bold text-emerald-400">
                  ₹{item.revenue.toLocaleString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
