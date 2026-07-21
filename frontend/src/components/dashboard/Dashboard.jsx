import React from 'react';
import { useDashboard } from '../../hooks/useDashboard';
import KPICards from './KPICards';
import RevenueBySectorChart from './RevenueBySectorChart';
import RevenueByStageChart from './RevenueByStageChart';
import MonthlyPipelineChart from './MonthlyPipelineChart';
import TopCustomersTable from './TopCustomersTable';
import BillingSummaryCard from './BillingSummaryCard';
import WorkOrderCard from './WorkOrderCard';
import { RefreshCw, AlertTriangle, BarChart2 } from 'lucide-react';

export default function Dashboard() {
  const { metrics, loading, error, refreshMetrics } = useDashboard();

  if (loading) {
    return (
      <div className="p-6 max-w-7xl mx-auto space-y-6 animate-pulse">
        <div className="flex items-center justify-between">
          <div className="h-8 bg-slate-800 rounded-lg w-64" />
          <div className="h-9 bg-slate-800 rounded-lg w-28" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 bg-slate-900 border border-slate-800 rounded-2xl p-5" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="h-80 bg-slate-900 border border-slate-800 rounded-2xl" />
          <div className="h-80 bg-slate-900 border border-slate-800 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-12 max-w-xl mx-auto text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 text-red-400 flex items-center justify-center mx-auto border border-red-500/20">
          <AlertTriangle className="w-7 h-7" />
        </div>
        <h2 className="text-xl font-bold text-slate-100">Failed to Load Executive Dashboard</h2>
        <p className="text-sm text-slate-400 leading-relaxed">{error}</p>
        <button
          onClick={refreshMetrics}
          className="inline-flex items-center space-x-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium text-sm transition-all shadow-md shadow-indigo-500/20 cursor-pointer"
        >
          <RefreshCw className="w-4 h-4" />
          <span>Retry Loading Dashboard</span>
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Dashboard Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <BarChart2 className="w-6 h-6 text-indigo-400" />
            <h2 className="text-2xl font-bold text-slate-100 tracking-tight">Executive Dashboard</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time business intelligence metrics computed from Deals & Work Orders dataset
          </p>
        </div>

        <button
          onClick={refreshMetrics}
          className="inline-flex items-center space-x-2 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 rounded-xl text-xs font-semibold transition-all cursor-pointer shadow-sm self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5 text-indigo-400" />
          <span>Refresh Metrics</span>
        </button>
      </div>

      {/* Top 4 KPI Summary Cards */}
      <KPICards
        pipelineSummary={metrics?.pipeline_summary}
        billingSummary={metrics?.billing_summary}
        workOrderSummary={metrics?.work_order_summary}
      />

      {/* Main Responsive Grid Layout (2-Columns on Desktop, 1-Column on Mobile) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column */}
        <div className="space-y-6">
          <RevenueBySectorChart revenueBySector={metrics?.revenue_by_sector} />
          <MonthlyPipelineChart monthlyPipeline={metrics?.monthly_pipeline} />
          <BillingSummaryCard billingSummary={metrics?.billing_summary} />
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          <RevenueByStageChart revenueByStage={metrics?.revenue_by_stage} />
          <TopCustomersTable topCustomers={metrics?.top_customers} />
          <WorkOrderCard workOrderSummary={metrics?.work_order_summary} />
        </div>
      </div>
    </div>
  );
}
