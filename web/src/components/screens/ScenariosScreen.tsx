import React from "react";
import { Sliders, Zap, AlertTriangle, ShieldCheck } from "lucide-react";

export const ScenariosScreen: React.FC = () => {
  const scenarios = [
    { id: "baseline", name: "Baseline Normal Operations", desc: "Standard demand profiles and functional cold-chain fleet.", active: true },
    { id: "dengue_outbreak", name: "Dengue Outbreak (H3 Yelahanka)", desc: "Triggers 4x demand spike for Paracetamol and ORS.", active: false },
    { id: "fridge_failure", name: "Cold Van CV-02 Fridge Failure", desc: "Temperature drifts to 11.4 °C, triggering coldchain.alert.", active: false },
    { id: "bad_data", name: "Corrupted Stock Register (H4)", desc: "Injects 10,000 insulin vials with year 1999 to test anomaly gate.", active: false },
    { id: "ilr_repaired", name: "H4 ILR Compressor Repaired", desc: "Restores cold storage capability at Primary Health Centre 4.", active: false },
  ];

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">Simulation Scenarios & Stress Injections</h1>
        <p className="text-sm text-slate-500 font-medium">
          Trigger deterministic operational shocks, epidemiological outbreaks, or equipment failures across the district twin
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scenarios.map((sc) => (
          <div
            key={sc.id}
            className={`p-5 rounded-xl border transition-all ${
              sc.active
                ? "bg-teal-50/50 border-teal-300 shadow-xs"
                : "bg-white border-slate-200 hover:border-slate-300"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-slate-900 text-sm flex items-center space-x-2">
                <Sliders className="w-4 h-4 text-teal-600" />
                <span>{sc.name}</span>
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  sc.active
                    ? "bg-teal-600 text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {sc.active ? "ACTIVE" : "STANDBY"}
              </span>
            </div>
            <p className="text-xs text-slate-500 mb-3">{sc.desc}</p>
            <button
              disabled={sc.active}
              className={`w-full py-1.5 px-3 rounded-md text-xs font-bold transition-colors ${
                sc.active
                  ? "bg-slate-200 text-slate-500 cursor-not-allowed"
                  : "bg-slate-900 hover:bg-slate-800 text-white"
              }`}
            >
              {sc.active ? "Currently Injected" : "Inject Scenario"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
