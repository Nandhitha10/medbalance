import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Play,
  Pause,
  FastForward,
  Activity,
  Radio,
  Clock,
  AlertCircle,
  Truck,
  Package,
} from "lucide-react";
import { api } from "../../lib/api";
import { ClockState, SSEEvent } from "../../types";
import { formatDateTime } from "../../lib/utils";
import { AuditBadge } from "./AuditBadge";

interface TopBarProps {
  events: SSEEvent[];
  isConnected: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({ events, isConnected }) => {
  const queryClient = useQueryClient();

  const { data: clock } = useQuery<ClockState>({
    queryKey: ["clock"],
    queryFn: () => api.getClock(),
    refetchInterval: 10000,
  });

  const clockMutation = useMutation({
    mutationFn: ({ running, speed }: { running: boolean; speed?: number }) =>
      api.setClockState(running, speed),
    onSuccess: (updated) => {
      queryClient.setQueryData(["clock"], updated);
    },
  });

  const isRunning = clock?.is_running ?? true;
  const currentSpeed = clock?.speed ?? 1.0;

  const toggleRunning = () => {
    clockMutation.mutate({ running: !isRunning, speed: currentSpeed });
  };

  const cycleSpeed = () => {
    const speeds = [1.0, 2.0, 5.0];
    const nextIdx = (speeds.indexOf(currentSpeed) + 1) % speeds.length;
    clockMutation.mutate({ running: isRunning, speed: speeds[nextIdx] });
  };

  const getEventBadge = (type: string) => {
    switch (type) {
      case "clock.tick":
        return { label: "TICK", bg: "bg-blue-100 text-blue-800 border-blue-300" };
      case "inventory.updated":
        return { label: "INVENTORY", bg: "bg-emerald-100 text-emerald-800 border-emerald-300" };
      case "coldchain.alert":
        return { label: "COLD-ALERT", bg: "bg-amber-100 text-amber-900 border-amber-300" };
      case "plan.completed":
        return { label: "PLAN-SOLVED", bg: "bg-purple-100 text-purple-800 border-purple-300" };
      case "anomaly.flagged":
        return { label: "ANOMALY", bg: "bg-rose-100 text-rose-800 border-rose-300" };
      default:
        return { label: type.split(".")[0].toUpperCase(), bg: "bg-slate-100 text-slate-800 border-slate-300" };
    }
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between shadow-2xs z-30 select-none">
      {/* Brand & Context */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-blue-600 text-white font-black text-lg shadow-xs">
          MB
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-black text-slate-900 text-lg tracking-tight">MedBalance-Q</span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
              Bengaluru Urban
            </span>
          </div>
          <p className="text-xs text-slate-500 font-medium hidden sm:block">
            District Essential Medicine Redistribution
          </p>
        </div>
      </div>

      {/* Center: Live Event Ticker (Latest 5 Events) */}
      <div className="hidden lg:flex items-center max-w-xl xl:max-w-2xl flex-1 mx-6 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 overflow-hidden">
        <div className="flex items-center space-x-1.5 mr-3 pr-3 border-r border-slate-200 shrink-0">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-600"></span>
          </span>
          <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            Live Feed
          </span>
        </div>

        <div className="flex items-center space-x-3 overflow-x-auto no-scrollbar whitespace-nowrap text-xs">
          {events.slice(0, 5).map((ev, idx) => {
            const badge = getEventBadge(ev.event_type);
            const detail =
              ev.data.facility_code ||
              ev.data.plan_id ||
              ev.data.sim_date ||
              ev.data.device_id ||
              "";
            return (
              <div
                key={ev.event_id || idx}
                className="inline-flex items-center space-x-1.5 bg-white border border-slate-200 rounded-lg px-2.5 py-0.5 shadow-2xs shrink-0"
              >
                <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded border ${badge.bg}`}>
                  {badge.label}
                </span>
                <span className="text-slate-700 font-semibold">
                  {detail}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {new Date(ev.timestamp).toLocaleTimeString("en-IN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right: Landing Page Link, Cryptographic Audit Badge & Simulation Clock Controls */}
      <div className="flex items-center space-x-3">
        {/* Quick link to 3D Landing Page */}
        <a
          href="/landing.html"
          title="Return to MedBalance-Q 3D Capsule Landing Page"
          className="hidden sm:inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 shadow-2xs transition-all hover:scale-[1.02]"
        >
          <span>✨ Landing Page</span>
        </a>

        {/* SHA-256 Merkle Audit Verification Badge with Tamper Demo Menu */}
        <AuditBadge />

        {/* Sim Date */}
        <div className="flex items-center space-x-2 bg-blue-50/80 border border-blue-200 px-3 py-1.5 rounded-xl shadow-2xs">
          <Clock className="w-4 h-4 text-blue-600" />
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-bold text-blue-700 leading-none">
              Simulation Clock
            </span>
            <span className="text-xs font-bold text-blue-950">
              {clock?.now ? formatDateTime(clock.now) : "01 Nov 2026, 08:00 AM"}
            </span>
          </div>
        </div>

        {/* Controls: Play/Pause and Speed */}
        <div className="flex items-center space-x-1 bg-slate-100 border border-slate-200 p-1 rounded-xl">
          <button
            onClick={toggleRunning}
            title={isRunning ? "Pause Simulation" : "Resume Simulation"}
            className={`p-1.5 rounded-lg transition-colors ${
              isRunning
                ? "bg-amber-500 hover:bg-amber-600 text-white"
                : "bg-blue-600 hover:bg-blue-700 text-white"
            }`}
          >
            {isRunning ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={cycleSpeed}
            title="Cycle Speed (1x, 2x, 5x)"
            className="flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-bold text-slate-700 hover:bg-white transition-colors"
          >
            <FastForward className="w-3 h-3 text-slate-500" />
            <span>{currentSpeed}x</span>
          </button>
        </div>
      </div>
    </header>
  );
};
