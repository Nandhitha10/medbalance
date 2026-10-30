import React from "react";
import { Snowflake, ArrowRight } from "lucide-react";

export const MapLegend: React.FC = () => {
  return (
    <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl p-4 shadow-lg text-xs space-y-3 max-w-xs select-none">
      <div className="font-bold text-slate-800 text-[11px] uppercase tracking-wider pb-1.5 border-b border-slate-100 flex items-center justify-between">
        <span className="text-slate-900 font-black">District Map Legend</span>
        <span className="text-[10px] text-blue-700 font-bold bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
          Bengaluru Urban
        </span>
      </div>

      {/* Stock Health Rings */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
          Facility Stock Health
        </span>
        <div className="flex items-center space-x-2.5">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-emerald-500 bg-emerald-100/60 shadow-2xs"></div>
          <span className="text-slate-700 font-semibold text-[11px]">Adequate / Balanced Reserve</span>
        </div>
        <div className="flex items-center space-x-2.5">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-amber-500 bg-amber-100/60 shadow-2xs"></div>
          <span className="text-slate-700 font-semibold text-[11px]">Warning: Surplus or Expiry Risk</span>
        </div>
        <div className="flex items-center space-x-2.5">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-rose-500 bg-rose-100/60 shadow-2xs"></div>
          <span className="text-slate-700 font-semibold text-[11px]">Critical Deficit (Vital Drug)</span>
        </div>
      </div>

      {/* Transfer Routes */}
      <div className="space-y-1.5 pt-1.5 border-t border-slate-100">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
          Active Transfer Network
        </span>
        <div className="flex items-center space-x-2.5">
          <div className="w-5 h-1 bg-blue-600 rounded-full shadow-2xs"></div>
          <span className="text-slate-700 font-semibold text-[11px]">Ambient Redistribution</span>
        </div>
        <div className="flex items-center space-x-2.5">
          <div className="w-5 h-1 bg-sky-500 rounded-full border-b border-dashed border-sky-300 flex items-center shadow-2xs">
            <Snowflake className="w-2.5 h-2.5 text-sky-700 ml-1 inline" />
          </div>
          <span className="text-slate-700 font-semibold text-[11px]">Cold Chain Van (2.0–8.0 °C)</span>
        </div>
      </div>

      <div className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-100">
        Click any facility disc to inspect its FEFO inventory drawer.
      </div>
    </div>
  );
};
