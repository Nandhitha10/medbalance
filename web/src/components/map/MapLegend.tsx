import React from "react";
import { Snowflake, ArrowRight } from "lucide-react";

export const MapLegend: React.FC = () => {
  return (
    <div className="bg-white/95 backdrop-blur-xs border border-slate-200 rounded-xl p-3.5 shadow-md text-xs space-y-2.5 max-w-xs">
      <div className="font-bold text-slate-800 text-[11px] uppercase tracking-wider pb-1 border-b border-slate-100 flex items-center justify-between">
        <span>Map Legend</span>
        <span className="text-[10px] text-teal-700 font-semibold bg-teal-50 px-1.5 py-0.5 rounded">
          Bengaluru Urban
        </span>
      </div>

      {/* Stock Health Rings */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-bold text-slate-500 uppercase">Stock-Health Rings</span>
        <div className="flex items-center space-x-2">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-emerald-500 bg-emerald-100/50"></div>
          <span className="text-slate-700 font-medium">Adequate / Balanced</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-amber-500 bg-amber-100/50"></div>
          <span className="text-slate-700 font-medium">Warning: Surplus or Expiry Risk</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-rose-500 bg-rose-100/50"></div>
          <span className="text-slate-700 font-medium">Critical Shortage (Vital Drug)</span>
        </div>
      </div>

      {/* Transfer Routes */}
      <div className="space-y-1.5 pt-1 border-t border-slate-100">
        <span className="text-[10px] font-bold text-slate-500 uppercase">Transfer Plan Arcs</span>
        <div className="flex items-center space-x-2">
          <div className="w-5 h-0.5 bg-teal-600 rounded"></div>
          <span className="text-slate-700 font-medium">Ambient Transfer</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-5 h-0.5 bg-cyan-500 rounded border-b border-dashed border-cyan-300 flex items-center">
            <Snowflake className="w-2.5 h-2.5 text-cyan-600 ml-1 inline" />
          </div>
          <span className="text-slate-700 font-medium">Cold Chain Van (2–8 °C)</span>
        </div>
      </div>

      <div className="text-[10px] text-slate-400 italic pt-0.5">
        Click any facility marker to open the detailed stock & FEFO drawer.
      </div>
    </div>
  );
};
