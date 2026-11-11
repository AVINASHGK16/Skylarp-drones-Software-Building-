import React from 'react';
import { IndianRupee, TrendingUp, Layers, Target, CreditCard, CheckCircle2 } from 'lucide-react';
import { formatCurrency } from '../../utils/formatters';

export default function KPICards({ pipelineSummary, billingSummary, workOrderSummary }) {
  // 1. Active Open Deals derivation (consume explicit field if exposed; do not derive or hardcode)
  const openTotalDeals = pipelineSummary?.open_deal_count ?? pipelineSummary?.active_deals;
  const explicitOpenValuedCount = pipelineSummary?.open_valued_deal_count ?? pipelineSummary?.open_valid_value_count;

  // 2. Gross Total Deals & Value Coverage derivation
  const valueCoverage = pipelineSummary?.value_coverage;
  const totalDeals = pipelineSummary?.total_deals ?? valueCoverage?.total_records;
  const validCount = valueCoverage?.valid_numeric_count;
  const missingCount = valueCoverage?.missing_value_count;

  // 3. Win Rate Metrics derivation
  const overallWinRate = pipelineSummary?.overall_concluded_win_rate;
  const formalWinRate = pipelineSummary?.formal_decision_win_rate ?? pipelineSummary?.pipeline_conversion_rate;
  const wonCount = pipelineSummary?.won_deal_count ?? pipelineSummary?.deals_won;

  const cards = [
    {
      title: 'Active Pipeline Value',
      value: formatCurrency(pipelineSummary?.active_pipeline_value),
      subtitle: explicitOpenValuedCount != null && openTotalDeals != null
        ? `${explicitOpenValuedCount} valued of ${openTotalDeals} open deals`
        : (openTotalDeals != null ? `${openTotalDeals} Open Deals` : '—'),
      icon: TrendingUp,
      color: 'from-emerald-500 to-teal-600',
      badge: openTotalDeals != null ? `${openTotalDeals} Active Deals` : '—',
      badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    },
    {
      title: 'Avg Active Deal Size',
      value: formatCurrency(pipelineSummary?.average_deal_value),
      subtitle: explicitOpenValuedCount != null
        ? `Across ${explicitOpenValuedCount} valued open deals`
        : 'Open Deals (Valued count N/A)',
      icon: IndianRupee,
      color: 'from-blue-500 to-indigo-600',
      badge: 'Open Deals Only',
      badgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    },
    {
      title: 'Gross Opportunity Value',
      value: formatCurrency(pipelineSummary?.gross_historical_opportunity_value ?? pipelineSummary?.total_pipeline_value),
      subtitle: validCount != null && totalDeals != null
        ? `${validCount} valued of ${totalDeals} total deals`
        : (totalDeals != null ? `${totalDeals} Total Deals` : '—'),
      icon: Layers,
      color: 'from-indigo-500 to-violet-600',
      badge: missingCount != null ? `${missingCount} unvalued` : '—',
      badgeColor: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    },
    {
      title: 'Win Rate Performance',
      value: overallWinRate != null ? `${overallWinRate}%` : '—',
      subtitle: wonCount != null ? `Overall Concluded (${wonCount} Won)` : 'Overall Concluded',
      icon: Target,
      color: 'from-amber-500 to-orange-600',
      badge: formalWinRate != null ? `${formalWinRate}% Formal` : '—',
      badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    },
    {
      title: 'Billing Realization',
      value: billingSummary?.billing_percentage != null ? `${billingSummary.billing_percentage}%` : '—',
      subtitle: billingSummary?.total_billed != null ? `${formatCurrency(billingSummary.total_billed)} Billed` : '—',
      icon: CreditCard,
      color: 'from-violet-500 to-purple-600',
      badge: billingSummary?.total_unbilled != null ? `${formatCurrency(billingSummary.total_unbilled)} Backlog` : '—',
      badgeColor: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    },
    {
      title: 'Work Order Completion',
      value: workOrderSummary?.completion_rate != null ? `${workOrderSummary.completion_rate}%` : '—',
      subtitle: workOrderSummary?.completed_work_orders != null && workOrderSummary?.total_work_orders != null
        ? `${workOrderSummary.completed_work_orders} of ${workOrderSummary.total_work_orders} Delivered`
        : '—',
      icon: CheckCircle2,
      color: 'from-teal-500 to-cyan-600',
      badge: workOrderSummary?.ongoing_work_orders != null ? `${workOrderSummary.ongoing_work_orders} Ongoing` : '—',
      badgeColor: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
      {cards.map((card, index) => {
        const Icon = card.icon;
        return (
          <div
            key={index}
            className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg relative overflow-hidden group hover:border-slate-700 transition-all duration-200 flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider truncate mr-1">
                  {card.title}
                </span>
                <div className={`w-8 h-8 rounded-xl bg-gradient-to-tr ${card.color} flex items-center justify-center text-white shadow-md shrink-0`}>
                  <Icon className="w-4 h-4" />
                </div>
              </div>

              <div className="mt-2.5">
                <div className="text-xl font-extrabold text-slate-100 tracking-tight">
                  {card.value}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-800/80">
              <span className="text-[11px] text-slate-400 font-medium truncate mr-1">
                {card.subtitle}
              </span>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border shrink-0 ${card.badgeColor}`}>
                {card.badge}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
