import React from "react";
import {
  Map,
  FileSpreadsheet,
  GitCommit,
  Scale,
  ThermometerSnowflake,
  TrendingUp,
  Cpu,
  Sliders,
} from "lucide-react";
import { NavPage } from "../../types";

interface SidebarNavProps {
  activePage: NavPage;
  onSelectPage: (page: NavPage) => void;
}

export const SidebarNav: React.FC<SidebarNavProps> = ({ activePage, onSelectPage }) => {
  const navItems: { id: NavPage; label: string; icon: React.ReactNode; badge?: string }[] = [
    { id: "map", label: "District Map", icon: <Map className="w-5 h-5" /> },
    { id: "plan", label: "Redistribution Plan", icon: <GitCommit className="w-5 h-5" />, badge: "CP1" },
    { id: "ingestion", label: "Hospital Ingest", icon: <FileSpreadsheet className="w-5 h-5" /> },
    { id: "coldchain", label: "Cold Chain IoT", icon: <ThermometerSnowflake className="w-5 h-5" /> },
    { id: "benchmark", label: "Solver Benchmark", icon: <Scale className="w-5 h-5" />, badge: "QUBO" },
    { id: "results", label: "Impact Results", icon: <TrendingUp className="w-5 h-5" /> },
    { id: "ai-health", label: "GenAI Gateway", icon: <Cpu className="w-5 h-5" /> },
    { id: "scenarios", label: "Sim Scenarios", icon: <Sliders className="w-5 h-5" /> },
  ];

  return (
    <aside className="w-64 bg-slate-900 text-slate-200 flex flex-col justify-between shrink-0 select-none shadow-md">
      <div className="p-4 space-y-6">
        <div className="px-3 pt-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-teal-400">
            District Operations
          </span>
        </div>

        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectPage(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  isActive
                    ? "bg-teal-700 text-white shadow-sm"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                <div className="flex items-center space-x-3">
                  <span className={isActive ? "text-teal-200" : "text-slate-400"}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span
                    className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                      isActive
                        ? "bg-teal-800 text-teal-200"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* District Officer User Pill at bottom */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/40">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-full bg-teal-600 text-white flex items-center justify-center font-bold text-xs shadow-inner">
            DO
          </div>
          <div className="flex flex-col text-left">
            <span className="text-xs font-bold text-slate-100">District Drug Officer</span>
            <span className="text-[11px] text-teal-400 font-medium">Bengaluru Urban Hub</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
