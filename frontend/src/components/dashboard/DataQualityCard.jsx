import React from 'react';
import { Database, ShieldCheck, AlertCircle, CheckCircle2, FileSpreadsheet } from 'lucide-react';
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
            {isFallback ? (
              <FileSpreadsheet className="w-3.5 h-3.5 text-amber-400" />
            ) : (
              <Database className="w-3.5 h-3.5 text-indigo-400" />
            )}
            <span className="text-slate-400">Source:</span>
            <span className="font-semibold text-slate-200">
              {dataSource === 'monday_api' ? 'Monday.com API' : dataSource === 'excel_fallback' ? 'Excel Backup' : (dataSource || 'Unknown')}
            </span>
          </div>

          {/* Ingestion Status Badge */}
          <div className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold border ${
            isLive
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
              : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
          }`}>
            {isLive ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
            <span>{isLive ? 'Live Status' : 'Fallback Mode'}</span>
          </div>
        </div>
      </div>

      {/* 4-Pillar Data Quality Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3">
        {/* Pillar 1: Valid Numeric Values */}
        <div className="bg-slate-950/40 border border-slate-800/60 rounded-xl p-2.5">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>Valid Numeric Deals</span>
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
          </div>
          <div className="text-base font-bold text-emerald-400">
            {formatCount(validCount)}
          </div>
          <p className="text-[10px] text-slate-500 mt-0.5">
            {totalRecords && validCount != null ? `${((validCount / totalRecords) * 100).toFixed(1)}% of dataset` : 'Summed in pipeline'}
          </p>
        </div>

        {/* Pillar 2: Missing Deal Values */}
        <div className="bg-slate-950/40 border border-slate-800/60 rounded-xl p-2.5">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>Missing Deal Values</span>
            <span className="w-2 h-2 rounded-full bg-amber-400" />
          </div>
          <div className="text-base font-bold text-amber-400">
            {formatCount(missingCount)}
          </div>
          <p className="text-[10px] text-slate-500 mt-0.5">
            {totalRecords && missingCount != null ? `${((missingCount / totalRecords) * 100).toFixed(1)}% (Excluded from sums)` : 'Excluded from sums'}
          </p>
        </div>

        {/* Pillar 3: Invalid Deal Values */}
        <div className="bg-slate-950/40 border border-slate-800/60 rounded-xl p-2.5">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>Invalid Numeric Deals</span>
            <span className="w-2 h-2 rounded-full bg-blue-400" />
          </div>
          <div className="text-base font-bold text-slate-200">
            {formatCount(invalidCount)}
          </div>
          <p className="text-[10px] text-slate-500 mt-0.5">
            Unparseable strings (0 in verified dataset)
          </p>
        </div>

        {/* Pillar 4: Total Business Deals */}
        <div className="bg-slate-950/40 border border-slate-800/60 rounded-xl p-2.5">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>Total Business Deals</span>
            <span className="w-2 h-2 rounded-full bg-indigo-400" />
          </div>
          <div className="text-base font-bold text-slate-100">
            {formatCount(totalRecords)}
          </div>
          <p className="text-[10px] text-slate-500 mt-0.5">
            {unknownCount > 0 ? `${unknownCount} header rows quarantined` : 'Clean business deals'}
          </p>
        </div>
      </div>

      {/* Audit Footnote */}
      <div className="mt-2.5 text-[10px] text-slate-500 flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-t border-slate-800/40 pt-2">
        <span>Invariant: Valid ({formatCount(validCount)}) + Missing ({formatCount(missingCount)}) + Invalid ({formatCount(invalidCount)}) = {formatCount(totalRecords)} Total Deals</span>
        <span className="text-slate-600">Note: Foreign currency rejection & negative counts isolated in backend diagnostics</span>
      </div>
    </div>
  );
}

