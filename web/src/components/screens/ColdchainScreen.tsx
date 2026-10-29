import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { ThermometerSnowflake, ShieldCheck, AlertTriangle, Truck } from "lucide-react";

export const ColdchainScreen: React.FC = () => {
  const { data: status } = useQuery({
    queryKey: ["coldchain"],
    queryFn: () => api.getColdchainStatus(),
  });

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">Cold Chain Telemetry & IoT Excursions</h1>
        <p className="text-sm text-slate-500 font-medium">
          Continuous temperature monitoring (2–8 °C) across refrigerated transport vans and facility ILRs
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Cold Van CV-01 */}
        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-900 text-sm flex items-center space-x-2">
              <Truck className="w-4 h-4 text-cyan-600" />
              <span>Cold Van CV-01</span>
            </span>
            <span className="bg-emerald-100 text-emerald-800 text-xs font-bold px-2 py-0.5 rounded border border-emerald-300">
              OK (4.2 °C)
            </span>
          </div>
          <div className="text-xs text-slate-500 space-y-1">
            <p>Device: <strong className="text-slate-800">DEV-CV-01</strong> (MQTT Active)</p>
            <p>Routes: <span className="text-teal-700 font-semibold">Active & Certified Safe</span></p>
            <p>Door: Closed · Battery: 94%</p>
          </div>
        </div>

        {/* Cold Van CV-02 */}
        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-900 text-sm flex items-center space-x-2">
              <Truck className="w-4 h-4 text-cyan-600" />
              <span>Cold Van CV-02</span>
            </span>
            <span className="bg-emerald-100 text-emerald-800 text-xs font-bold px-2 py-0.5 rounded border border-emerald-300">
              OK (4.8 °C)
            </span>
          </div>
          <div className="text-xs text-slate-500 space-y-1">
            <p>Device: <strong className="text-slate-800">DEV-CV-02</strong> (MQTT Active)</p>
            <p>Fault Mode: <span className="text-slate-600">Standby (triggers on fridge_failure)</span></p>
            <p>Door: Closed · Battery: 91%</p>
          </div>
        </div>

        {/* H4 Facility ILR */}
        <div className="p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-900 text-sm flex items-center space-x-2">
              <ThermometerSnowflake className="w-4 h-4 text-rose-600" />
              <span>H4 Facility ILR</span>
            </span>
            <span className="bg-rose-100 text-rose-800 text-xs font-bold px-2 py-0.5 rounded border border-rose-300">
              FAULT / UNDER REPAIR
            </span>
          </div>
          <div className="text-xs text-slate-500 space-y-1">
            <p>Device: <strong className="text-slate-800">DEV-ILR-H4</strong></p>
            <p>Status: <span className="text-rose-700 font-semibold">Cold Storage Ineligible</span></p>
            <p>Action: Insulin lots prioritized for immediate evacuation</p>
          </div>
        </div>
      </div>
    </div>
  );
};
