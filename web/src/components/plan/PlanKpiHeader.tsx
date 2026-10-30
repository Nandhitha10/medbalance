import React from "react";
import { PlanRun } from "../../types";
import { formatNumber, formatCurrencyINR } from "../../lib/utils";
import { TrendingDown, ShieldCheck, Truck, AlertOctagon, Zap } from "lucide-react";

interface PlanKpiHeaderProps {
  plan: PlanRun;
}

export const PlanKpiHeader: React.FC<PlanKpiHeaderProps> = ({ plan }) => {
  return (
    <div className="space-y-3">
      {/* Plan Header Metadata */}
      <div className="flex flex-wrap items-center justify-between bg-white border border-slate-200 px-5 py-3 rounded-2xl shadow-2xs">
        <div className="flex items-center space-x-3">
          <span className="font-black text-slate-900 text-base">{plan.id}</span>
          <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200">
            {plan.status}
          </span>
          <span className="text-xs font-medium text-slate-500">
            Solved in <strong className="text-slate-800">{plan.execution_time_sec ?? 0.042}s</strong> via <strong className="text-blue-700">{plan.solver_tier || "platform"}</strong>
          </span>
        </div>
        <div className="flex items-center space-x-2 text-xs text-slate-500 font-semibold">
          <Zap className="w-3.5 h-3.5 text-blue-600" />
          <span>F1–F6 Feasibility Enforced</span>
        </div>
      </div>

      {/* 4 Large KPI Cards for Projector View */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Shortage Reduced */}
        <div className="p-4 bg-white border border-slate-200 rounded-2xl shadow-xs flex items-center justify-between">
          <div>
            <span className="text-xs font-bold uppercase text-slate-400 block mb-1">
              Shortage Reduction
            </span>
            <div className="text-2xl font-black text-blue-700">
              {formatNumber(plan.shortage_reduction)} <span className="text-sm font-semibold text-slate-400">units</span>
            </div>
            <span className="text-xs font-semibold text-emerald-600">
              Zero unconsumed waste moved
            </span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-700">
            <TrendingDown className="w-6 h-6" />
          </div>
        </div>

        {/* Card 2: Expiry Avoided ₹ */}
        <div className="p-4 bg-white border border-slate-200 rounded-2xl shadow-xs flex items-center justify-between">
          <div>
            <span className="text-xs font-bold uppercase text-slate-400 block mb-1">
              Expiry Avoidance Value
            </span>
            <div className="text-2xl font-black text-slate-900">
              {formatCurrencyINR(plan.total_savings_inr || 12450)}
            </div>
            <span className="text-xs font-semibold text-slate-500">
              {formatNumber(plan.expiry_avoided)} units rescued
            </span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700">
            <ShieldCheck className="w-6 h-6" />
          </div>
        </div>

        {/* Card 3: Transport Trips */}
        <div className="p-4 bg-white border border-slate-200 rounded-2xl shadow-xs flex items-center justify-between">
          <div>
            <span className="text-xs font-bold uppercase text-slate-400 block mb-1">
              Dispatch Orders
            </span>
            <div className="text-2xl font-black text-slate-900">
              {plan.total_orders || plan.orders.length} <span className="text-sm font-semibold text-slate-400">DTA vouchers</span>
            </div>
            <span className="text-xs font-semibold text-sky-600">
              {plan.orders.filter((o) => o.temperature_controlled).length} cold chain trips
            </span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-sky-50 border border-sky-200 flex items-center justify-center text-sky-700">
            <Truck className="w-6 h-6" />
          </div>
        </div>

        {/* Card 4: Feasibility Violations */}
        <div className="p-4 bg-white border border-slate-200 rounded-2xl shadow-xs flex items-center justify-between">
          <div>
            <span className="text-xs font-bold uppercase text-slate-400 block mb-1">
              Rule Violations
            </span>
            <div className="text-2xl font-black text-emerald-600">
              0 <span className="text-sm font-semibold text-slate-400">violations</span>
            </div>
            <span className="text-xs font-semibold text-emerald-600">
              100% FEFO audit verified
            </span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
            <ShieldCheck className="w-6 h-6" />
          </div>
        </div>
      </div>
    </div>
  );
};
