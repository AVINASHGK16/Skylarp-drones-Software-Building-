import React from 'react';
import { DollarSign, TrendingUp, CreditCard, CheckCircle2 } from 'lucide-react';

/**
 * Format currency numbers cleanly into Indian Rupees (INR) format or abbreviated string.
 */
function formatCurrency(val) {
  if (val === undefined || val === null) return '₹0';
  if (val >= 1e9) return `₹${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e7) return `₹${(val / 1e7).toFixed(2)}Cr`;
  if (val >= 1e5) return `₹${(val / 1e5).toFixed(2)}L`;
  return `₹${val.toLocaleString('en-IN')}`;
}

export default function KPICards({ pipelineSummary, billingSummary, workOrderSummary }) {
  const cards = [
    {
      title: 'Total Pipeline Value',
      value: formatCurrency(pipelineSummary?.total_pipeline_value),
      subtitle: `${pipelineSummary?.total_deals || 0} Total Deals`,
      icon: DollarSign,
      color: 'from-emerald-500 to-teal-600',
      badge: `${pipelineSummary?.pipeline_conversion_rate || 0}% Win Rate`,
      badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    },
    {
      title: 'Average Deal Size',
      value: formatCurrency(pipelineSummary?.average_deal_value),
      subtitle: `${pipelineSummary?.active_deals || 0} Active Deals`,
      icon: TrendingUp,
      color: 'from-blue-500 to-indigo-600',
      badge: `${pipelineSummary?.deals_won || 0} Won`,
      badgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    },
    {
      title: 'Billing Realization',
      value: `${billingSummary?.billing_percentage || 0}%`,
      subtitle: `${formatCurrency(billingSummary?.total_billed)} Billed`,
      icon: CreditCard,
      color: 'from-violet-500 to-purple-600',
      badge: `${formatCurrency(billingSummary?.total_unbilled)} Backlog`,
      badgeColor: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    },
    {
      title: 'Work Order Completion',
      value: `${workOrderSummary?.completion_rate || 0}%`,
      subtitle: `${workOrderSummary?.completed_work_orders || 0} of ${workOrderSummary?.total_work_orders || 0} Delivered`,
      icon: CheckCircle2,
      color: 'from-amber-500 to-orange-600',
      badge: `${workOrderSummary?.ongoing_work_orders || 0} Ongoing`,
      badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
      {cards.map((card, index) => {
        const Icon = card.icon;
        return (
          <div
            key={index}
            className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg relative overflow-hidden group hover:border-slate-700 transition-all duration-200"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {card.title}
              </span>
              <div className={`w-9 h-9 rounded-xl bg-gradient-to-tr ${card.color} flex items-center justify-center text-white shadow-md`}>
                <Icon className="w-5 h-5" />
              </div>
            </div>

            <div className="mt-3">
              <div className="text-2xl font-extrabold text-slate-100 tracking-tight">
                {card.value}
              </div>
              <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/80">
                <span className="text-xs text-slate-400 font-medium">
                  {card.subtitle}
                </span>
                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${card.badgeColor}`}>
                  {card.badge}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
