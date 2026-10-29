import React from "react";
import { Scale, CheckCircle2, TrendingUp, AlertTriangle } from "lucide-react";

export const BenchmarkScreen: React.FC = () => {
  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">Solver Benchmark & Algorithm Comparison</h1>
        <p className="text-sm text-slate-500 font-medium">
          Evaluating the gap to MILP optimum: QUBO (QpiAI Opt) vs Safe Greedy F4 vs Baseline Phone Call
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-900">Baseline Phone Call</h3>
            <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-bold">Manual</span>
          </div>
          <p className="text-xs text-slate-500">
            Simulates current manual hospital calls. Ignores destination usable capacity, moving stock that still expires at destination.
          </p>
          <div className="text-xs text-rose-700 font-semibold bg-rose-50 p-2 rounded border border-rose-200">
            Moved Waste: ~400 units
          </div>
        </div>

        <div className="p-5 bg-teal-50 border border-teal-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-teal-950">Safe Greedy F4</h3>
            <span className="text-xs bg-teal-600 text-white px-2 py-0.5 rounded font-bold">CP1 Core</span>
          </div>
          <p className="text-xs text-teal-800">
            Sequential greedy allocation with full F1–F6 feasibility enforcement and reserve protection. Guarantees zero waste moved.
          </p>
          <div className="text-xs text-emerald-800 font-semibold bg-emerald-100/60 p-2 rounded border border-emerald-300">
            Moved Waste: 0 units (100% Usable)
          </div>
        </div>

        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-900">QUBO Allocation</h3>
            <span className="text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded font-bold">QpiAI Opt</span>
          </div>
          <p className="text-xs text-slate-500">
            Quadratic unconstrained binary optimization with soft chunk constraints, VEN priorities, and multi-trip cost sharing.
          </p>
          <div className="text-xs text-purple-800 font-semibold bg-purple-50 p-2 rounded border border-purple-200">
            Energy: -42.8 | Time: 4.12s
          </div>
        </div>
      </div>
    </div>
  );
};
