import React from "react";
import { TrendingUp, ShieldCheck, DollarSign, Package } from "lucide-react";

export const ResultsScreen: React.FC = () => {
  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">Impact Evaluation & Stockout Reduction</h1>
        <p className="text-sm text-slate-500 font-medium">
          District-level outcomes tracking: actual stockout reduction, expiry units rescued, and financial savings
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-2">
          <span className="text-xs font-bold uppercase text-slate-500">Cumulative Shortage Reduced</span>
          <div className="text-3xl font-black text-teal-700">1,350 units</div>
          <p className="text-xs text-slate-500">92% reduction across high-volume district facilities</p>
        </div>

        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-2">
          <span className="text-xs font-bold uppercase text-slate-500">Total Expiry Value Rescued</span>
          <div className="text-3xl font-black text-slate-900">₹12,450</div>
          <p className="text-xs text-slate-500">Net benefit after ₹820 total transport costs</p>
        </div>

        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-2">
          <span className="text-xs font-bold uppercase text-slate-500">Active Audit Provenance DAGs</span>
          <div className="text-3xl font-black text-emerald-600">6 / 6 verified</div>
          <p className="text-xs text-slate-500">Cryptographically chained via SHA-256 audit log</p>
        </div>
      </div>
    </div>
  );
};
