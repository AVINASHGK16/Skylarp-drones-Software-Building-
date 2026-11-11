import React from 'react';
import { Database, ShieldCheck, AlertCircle, CheckCircle2, FileSpreadsheet, Sparkles } from 'lucide-react';
import { formatCount } from '../../utils/formatters';

export default function DataQualityCard({ metadata, pipelineSummary }) {
  const valueCoverage = pipelineSummary?.value_coverage;
  const validCount = valueCoverage?.valid_numeric_count;
  const missingCount = valueCoverage?.missing_value_count;
  const invalidCount = valueCoverage?.invalid_value_count;
  const totalRecords = valueCoverage?.total_records ?? pipelineSummary?.total_deals;
  const unknownCount = pipelineSummary?.unknown_deal_count ?? 0;

  const dataSource = metadata?.data_source;
  const dataStatus = metadata?.data_status;

  const isDemo = dataSource === 'synthetic_demo';
  const isLive = dataStatus === 'live';
  const isFallback = dataStatus === 'fallback' || dataSource === 'excel_fallback';

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 shadow-md text-xs">
      {/* Top Header & Status Indicators */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center space-x-2.5">
          <div className="w-7 h-7 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center shrink-0">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <h4 className="font-bold text-slate-200">Data Hygiene & Source Integrity</h4>
            <p className="text-[11px] text-slate-400">Strict numeric value classification and ingestion origin</p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {/* Data Source Badge */}
          <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-[11px]">
            {isDemo ? (
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            ) : isFallback ? (
              <FileSpreadsheet className="w-3.5 h-3.5 text-amber-400" />
            ) : (
              <Database className="w-3.5 h-3.5 text-indigo-400" />
            )}
            <span className="text-slate-400">Source:</span>
            <span className="font-semibold text-slate-200">
              {isDemo
                ? 'Portfolio Synthetic Data'
                : dataSource === 'monday_api'
                ? 'Monday.com API'
                : dataSource === 'excel_fallback'
                ? 'Excel Backup'
                : (dataSource || 'Unknown')}
            </span>
          </div>

          {/* Ingestion Status Badge */}
          <div className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold border ${
            isDemo
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              : isLive
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
              : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
          }`}>
            {isDemo ? (
              <Sparkles className="w-3 h-3" />
            ) : isLive ? (
              <CheckCircle2 className="w-3 h-3" />
            ) : (
              <AlertCircle className="w-3 h-3" />
            )}
            <span>{isDemo ? 'Portfolio Demo' : isLive ? 'Live Status' : 'Fallback Mode'}</span>
          </div>
        </div>
      </div>

      {/* 4-Pillar Data Quality Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3">
        {/* Valid Records */}
        <div className="p-3 bg-slate-950/50 border border-slate-800/80 rounded-xl">
          <span className="text-slate-400 font-medium block">Valid Numeric Values</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-base font-bold text-emerald-400">{formatCount(validCount)}</span>
            <span className="text-[10px] text-slate-500">/ {formatCount(totalRecords)} total</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">Sanitized clean values</span>
        </div>

        {/* Missing Values */}
        <div className="p-3 bg-slate-950/50 border border-slate-800/80 rounded-xl">
          <span className="text-slate-400 font-medium block">Missing Values</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className={`text-base font-bold ${missingCount > 0 ? 'text-amber-400' : 'text-slate-300'}`}>
              {formatCount(missingCount)}
            </span>
            <span className="text-[10px] text-slate-500">records</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">Treated as 0 without skewing</span>
        </div>

        {/* Non-numeric / Invalid */}
        <div className="p-3 bg-slate-950/50 border border-slate-800/80 rounded-xl">
          <span className="text-slate-400 font-medium block">Invalid Strings</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className={`text-base font-bold ${invalidCount > 0 ? 'text-rose-400' : 'text-slate-300'}`}>
              {formatCount(invalidCount)}
            </span>
            <span className="text-[10px] text-slate-500">records</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">Cleaned currency symbols</span>
        </div>

        {/* Unknown Category/Stage */}
        <div className="p-3 bg-slate-950/50 border border-slate-800/80 rounded-xl">
          <span className="text-slate-400 font-medium block">Unknown Stage</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className={`text-base font-bold ${unknownCount > 0 ? 'text-amber-400' : 'text-slate-300'}`}>
              {formatCount(unknownCount)}
            </span>
            <span className="text-[10px] text-slate-500">deals</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">Categorized under &apos;Unknown&apos;</span>
        </div>
      </div>
    </div>
  );
}
