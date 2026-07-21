import React from 'react';
import { CheckCircle2, Clock, PlayCircle, ListOrdered } from 'lucide-react';

export default function WorkOrderCard({ workOrderSummary }) {
  const total = workOrderSummary?.total_work_orders || 0;
  const completed = workOrderSummary?.completed_work_orders || 0;
  const ongoing = workOrderSummary?.ongoing_work_orders || 0;
  const pending = workOrderSummary?.pending_work_orders || 0;
  const completionRate = workOrderSummary?.completion_rate || 0;

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-lg flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
            <ListOrdered className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100">Work Orders Execution</h3>
            <p className="text-xs text-slate-400">Operational project fulfillment pipeline</p>
          </div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
          {completionRate}% Completed
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1 mb-4">
        <div className="flex justify-between text-xs font-medium text-slate-400">
          <span>Completed ({completed})</span>
          <span>Ongoing ({ongoing})</span>
          <span>Pending ({pending})</span>
        </div>
        <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden flex">
          <div
            className="bg-emerald-500 h-full transition-all duration-500"
            style={{ width: total > 0 ? `${(completed / total) * 100}%` : '0%' }}
          />
          <div
            className="bg-blue-500 h-full transition-all duration-500"
            style={{ width: total > 0 ? `${(ongoing / total) * 100}%` : '0%' }}
          />
          <div
            className="bg-slate-700 h-full transition-all duration-500"
            style={{ width: total > 0 ? `${(pending / total) * 100}%` : '0%' }}
          />
        </div>
      </div>

      {/* Metric Breakdown Grid */}
      <div className="grid grid-cols-4 gap-2 pt-3 border-t border-slate-800 text-xs">
        <div>
          <span className="text-slate-400 font-medium block">Total</span>
          <span className="text-sm font-bold text-slate-100 block mt-1">{total}</span>
        </div>
        <div>
          <span className="text-slate-400 font-medium block flex items-center">
            <CheckCircle2 className="w-3 h-3 text-emerald-400 mr-0.5" />
            Done
          </span>
          <span className="text-sm font-bold text-emerald-400 block mt-1">{completed}</span>
        </div>
        <div>
          <span className="text-slate-400 font-medium block flex items-center">
            <PlayCircle className="w-3 h-3 text-blue-400 mr-0.5" />
            Ongoing
          </span>
          <span className="text-sm font-bold text-blue-400 block mt-1">{ongoing}</span>
        </div>
        <div>
          <span className="text-slate-400 font-medium block flex items-center">
            <Clock className="w-3 h-3 text-slate-400 mr-0.5" />
            Pending
          </span>
          <span className="text-sm font-bold text-slate-300 block mt-1">{pending}</span>
        </div>
      </div>
    </div>
  );
}
