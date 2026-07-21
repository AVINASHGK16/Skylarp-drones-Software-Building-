import React from 'react';
import { CreditCard, ArrowUpRight, Clock, AlertCircle } from 'lucide-react';

function formatCurrency(val) {
  if (val === undefined || val === null) return '₹0';
  if (val >= 1e7) return `₹${(val / 1e7).toFixed(2)} Cr`;
  if (val >= 1e5) return `₹${(val / 1e5).toFixed(2)} Lakh`;
  return `₹${val.toLocaleString('en-IN')}`;
}

export default function BillingSummaryCard({ billingSummary }) {
  const contractVal = billingSummary?.total_contract_value || 0;
  const billedVal = billingSummary?.total_billed || 0;
  const unbilledVal = billingSummary?.total_unbilled || 0;
  const billingPct = billingSummary?.billing_percentage || 0;

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
          {billingPct}% Realized
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1 mb-4">
        <div className="flex justify-between text-xs font-medium text-slate-400">
          <span>Realized ({billingPct}%)</span>
          <span>Unbilled ({(100 - billingPct).toFixed(1)}%)</span>
        </div>
        <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden flex">
          <div
            className="bg-emerald-500 h-full transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, billingPct))}%` }}
          />
          <div
            className="bg-amber-500/80 h-full transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, 100 - billingPct))}%` }}
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
          <span className="text-slate-400 font-medium block flex items-center">
            <ArrowUpRight className="w-3 h-3 text-emerald-400 mr-0.5" />
            Billed
          </span>
          <span className="text-sm font-bold text-emerald-400 block mt-1">
            {formatCurrency(billedVal)}
          </span>
        </div>
        <div>
          <span className="text-slate-400 font-medium block flex items-center">
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
