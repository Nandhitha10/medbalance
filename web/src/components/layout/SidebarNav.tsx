import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Map,
  FileSpreadsheet,
  GitCommit,
  Scale,
  ThermometerSnowflake,
  TrendingUp,
  Cpu,
  Sliders,
  AlertCircle,
} from "lucide-react";
import { NavPage } from "../../types";
import { api } from "../../lib/api";

interface SidebarNavProps {
  activePage: NavPage;
  onSelectPage: (page: NavPage) => void;
  anomalyCount?: number;
}

export const SidebarNav: React.FC<SidebarNavProps> = ({
  activePage,
  onSelectPage,
  anomalyCount: externalAnomalyCount,
}) => {
  const { data: reviews = [] } = useQuery({
    queryKey: ["reviews"],
    queryFn: () => api.getReviews(),
    refetchInterval: 5000,
  });

  const pendingAnomaliesCount =
    externalAnomalyCount !== undefined
      ? externalAnomalyCount
      : reviews.filter((r: any) => r.status === "PENDING" || !r.status).length;

  const navItems: {
    id: NavPage;
    label: string;
    icon: React.ReactNode;
    badge?: string;
    badgeVariant?: "teal" | "amber" | "rose" | "purple";
  }[] = [
    { id: "map", label: "District Map", icon: <Map className="w-5 h-5" /> },
    {
      id: "plan",
      label: "Redistribution Plan",
      icon: <GitCommit className="w-5 h-5" />,
      badge: "CP1",
      badgeVariant: "teal",
    },
    {
      id: "ingestion",
      label: "Hospital Ingest",
      icon: <FileSpreadsheet className="w-5 h-5" />,
      badge: pendingAnomaliesCount > 0 ? `${pendingAnomaliesCount} Review` : undefined,
      badgeVariant: "amber",
    },
    {
      id: "coldchain",
      label: "Cold Chain IoT",
      icon: <ThermometerSnowflake className="w-5 h-5" />,
      badge: "2-8°C",
      badgeVariant: "teal",
    },
    {
      id: "benchmark",
      label: "Solver Benchmark",
      icon: <Scale className="w-5 h-5" />,
      badge: "QUBO",
      badgeVariant: "purple",
    },
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
                    className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full flex items-center space-x-1 ${
                      item.badgeVariant === "amber"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse"
                        : item.badgeVariant === "purple"
                        ? "bg-purple-900/60 text-purple-300 border border-purple-700/50"
                        : isActive
                        ? "bg-teal-800 text-teal-200"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {item.badgeVariant === "amber" && (
                      <AlertCircle className="w-3 h-3 text-amber-400 mr-0.5" />
                    )}
                    <span>{item.badge}</span>
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
