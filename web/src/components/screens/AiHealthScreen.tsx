import React from "react";
import { Cpu, Zap, ShieldCheck, Database } from "lucide-react";

export const AiHealthScreen: React.FC = () => {
  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">GenAI Gateway Health & Prompt Registry</h1>
        <p className="text-sm text-slate-500 font-medium">
          Provider status, 24h rolling metrics, structured schema validation retries, and Redis replay cache
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs">
          <span className="text-xs font-bold text-slate-500 uppercase block mb-1">Active Provider</span>
          <span className="text-xl font-black text-teal-700">ClaudeProvider</span>
          <span className="text-[11px] text-slate-500 block">Fast: Haiku | Smart: Sonnet</span>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs">
          <span className="text-xs font-bold text-slate-500 uppercase block mb-1">Cache Hit Rate</span>
          <span className="text-xl font-black text-slate-900">100.0%</span>
          <span className="text-[11px] text-emerald-600 block">DEMO_MODE=replay active</span>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs">
          <span className="text-xs font-bold text-slate-500 uppercase block mb-1">Schema Compliance</span>
          <span className="text-xl font-black text-emerald-600">100% Valid</span>
          <span className="text-[11px] text-slate-500 block">0 schema retries needed</span>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs">
          <span className="text-xs font-bold text-slate-500 uppercase block mb-1">P50 Latency</span>
          <span className="text-xl font-black text-slate-900">0.02s</span>
          <span className="text-[11px] text-slate-500 block">Replay cache speedup</span>
        </div>
      </div>
    </div>
  );
};
