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
  QrCode,
  ShieldCheck,
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
    badgeVariant?: "blue" | "amber" | "purple" | "emerald";
  }[] = [
    { id: "map", label: "District Map", icon: <Map className="w-5 h-5" /> },
    {
      id: "plan",
      label: "Redistribution Plan",
      icon: <GitCommit className="w-5 h-5" />,
      badge: "CP1",
      badgeVariant: "blue",
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
      badgeVariant: "blue",
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
    {
      id: "scan",
      label: "Mobile Scanner",
      icon: <QrCode className="w-5 h-5" />,
      badge: "LAN",
      badgeVariant: "emerald",
    },
  ];

  return (
    <aside className="w-64 bg-white border-r border-slate-200/90 text-slate-700 flex flex-col justify-between shrink-0 select-none shadow-xs z-20">
      <div className="p-4 space-y-5">
        <div className="px-3 pt-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-blue-700">
            District Operations
          </span>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectPage(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  isActive
                    ? "bg-blue-600 text-white shadow-xs"
                    : "text-slate-600 hover:bg-blue-50/70 hover:text-blue-700"
                }`}
              >
                <div className="flex items-center space-x-3">
                  <span className={isActive ? "text-white" : "text-slate-400 group-hover:text-blue-600"}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span
                    className={`text-[10px] uppercase font-black px-2 py-0.5 rounded-full flex items-center space-x-1 ${
                      item.badgeVariant === "amber"
                        ? "bg-amber-100 text-amber-800 border border-amber-300 animate-pulse"
                        : isActive
                        ? "bg-blue-700/80 text-white border border-blue-400/40"
                        : "bg-blue-50 text-blue-700 border border-blue-200"
                    }`}
                  >
                    {item.badgeVariant === "amber" && (
                      <AlertCircle className="w-3 h-3 text-amber-600 mr-0.5" />
                    )}
                    <span>{item.badge}</span>
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Return to 3D Capsule Landing Page */}
      <div className="px-4 py-2 border-t border-slate-100">
        <a
          href="/landing.html"
          className="flex items-center justify-between w-full px-3 py-2 rounded-xl text-xs font-bold text-blue-700 bg-blue-50/80 hover:bg-blue-100 hover:text-blue-900 border border-blue-200 transition-all shadow-2xs group"
          title="Return to 3D Capsule Landing Page"
        >
          <span className="flex items-center space-x-2">
            <span>✨ 3D Landing Page</span>
          </span>
          <span className="text-[10px] bg-white px-2 py-0.5 rounded-full border border-blue-200 text-blue-700 font-mono">
            &rarr;
          </span>
        </a>
      </div>

      {/* District Officer User Card at bottom */}
      <div className="p-4 border-t border-slate-100 bg-blue-50/40">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-blue-600 text-white flex items-center justify-center font-black text-xs shadow-xs">
            DO
          </div>
          <div className="flex flex-col text-left">
            <span className="text-xs font-bold text-slate-900">District Drug Officer</span>
            <span className="text-[11px] text-blue-700 font-semibold">Bengaluru Urban Hub</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
