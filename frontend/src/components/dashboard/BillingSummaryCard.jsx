import React from 'react';
import { CreditCard, ArrowUpRight, Clock } from 'lucide-react';
import { formatCurrency } from '../../utils/formatters';

export default function BillingSummaryCard({ billingSummary }) {
  const contractVal = billingSummary?.total_contract_value;
  const billedVal = billingSummary?.total_billed;
  const unbilledVal = billingSummary?.total_unbilled;
  const billingPct = billingSummary?.billing_percentage;

  const validPct = billingPct != null ? Math.min(100, Math.max(0, billingPct)) : 0;
  const unbilledPct = billingPct != null ? Math.min(100, Math.max(0, 100 - billingPct)) : 0;

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <CreditCard className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100">Billing Summary</h3>
            <p className="text-xs text-slate-400">Financial execution & realization backlog</p>
          </div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          {billingPct != null ? `${billingPct}% Realized` : '—'}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1 mb-4">
        <div className="flex justify-between text-xs font-medium text-slate-400">
          <span>Realized ({billingPct != null ? `${billingPct}%` : '—'})</span>
          <span>Unbilled ({billingPct != null ? `${(100 - billingPct).toFixed(1)}%` : '—'})</span>
        </div>
        <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden flex">
          <div
            className="bg-emerald-500 h-full transition-all duration-500"
            style={{ width: `${validPct}%` }}
          />
          <div
            className="bg-amber-500/80 h-full transition-all duration-500"
            style={{ width: `${unbilledPct}%` }}
          />
        </div>
      </div>

      {/* Metric Items Grid */}
      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-slate-800 text-xs">
        <div>
          <span className="text-slate-400 font-medium block">Total Contract</span>
          <span className="text-sm font-bold text-slate-100 block mt-1">
            {formatCurrency(contractVal)}
          </span>
        </div>
        <div>
          <span className="text-slate-400 font-medium flex items-center">
            <ArrowUpRight className="w-3 h-3 text-emerald-400 mr-0.5" />
            Billed
          </span>
          <span className="text-sm font-bold text-emerald-400 block mt-1">
            {formatCurrency(billedVal)}
          </span>
        </div>
        <div>
          <span className="text-slate-400 font-medium flex items-center">
            <Clock className="w-3 h-3 text-amber-400 mr-0.5" />
            Unbilled
          </span>
          <span className="text-sm font-bold text-amber-400 block mt-1">
            {formatCurrency(unbilledVal)}
          </span>
        </div>
      </div>
    </div>
  );
}
