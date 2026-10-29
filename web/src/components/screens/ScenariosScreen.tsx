import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { ScenarioItem, SignalItem, ClockState } from "../../types";
import {
  Sliders,
  Zap,
  AlertTriangle,
  ShieldCheck,
  RotateCcw,
  Play,
  Pause,
  FastForward,
  Radio,
  Flame,
  FileSpreadsheet,
  Truck,
  Syringe,
  Activity,
  CheckCircle2,
} from "lucide-react";

export const ScenariosScreen: React.FC = () => {
  const queryClient = useQueryClient();
  const [resetSeed, setResetSeed] = useState<number>(42);
  const [activatingId, setActivatingId] = useState<string | null>(null);

  const { data: scenarios = [] } = useQuery<ScenarioItem[]>({
    queryKey: ["scenarios"],
    queryFn: () => api.getScenarios(),
    refetchInterval: 3000,
  });

  const { data: signals = [] } = useQuery<SignalItem[]>({
    queryKey: ["signals"],
    queryFn: () => api.getSignals(),
    refetchInterval: 4000,
  });

  const { data: clock } = useQuery<ClockState>({
    queryKey: ["clock"],
    queryFn: () => api.getClock(),
    refetchInterval: 1000,
  });

  const activateMutation = useMutation({
    mutationFn: (name: string) => api.applyScenario(name),
    onMutate: (name) => setActivatingId(name),
    onSuccess: () => {
      setTimeout(() => {
        setActivatingId(null);
        queryClient.invalidateQueries({ queryKey: ["scenarios"] });
        queryClient.invalidateQueries({ queryKey: ["signals"] });
        queryClient.invalidateQueries({ queryKey: ["coldchain"] });
        queryClient.invalidateQueries({ queryKey: ["positions"] });
      }, 500);
    },
    onError: () => setActivatingId(null),
  });

  const clockMutation = useMutation({
    mutationFn: ({ running, speed }: { running: boolean; speed?: number }) =>
      api.setClockState(running, speed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clock"] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: (seed: number) => api.resetSimulation(seed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clock"] });
      queryClient.invalidateQueries({ queryKey: ["scenarios"] });
      queryClient.invalidateQueries({ queryKey: ["signals"] });
      queryClient.invalidateQueries({ queryKey: ["coldchain"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["plan"] });
    },
  });

  const scenarioMeta: Record<string, { icon: React.ReactNode; color: string }> = {
    baseline: { icon: <ShieldCheck className="w-4 h-4 text-teal-600" />, color: "border-teal-200" },
    dengue_outbreak: { icon: <Activity className="w-4 h-4 text-rose-600" />, color: "border-rose-300" },
    fridge_failure: { icon: <Flame className="w-4 h-4 text-rose-600" />, color: "border-rose-300" },
    bad_data: { icon: <FileSpreadsheet className="w-4 h-4 text-amber-600" />, color: "border-amber-300" },
    ilr_repaired: { icon: <CheckCircle2 className="w-4 h-4 text-emerald-600" />, color: "border-emerald-300" },
    road_closure: { icon: <Truck className="w-4 h-4 text-slate-600" />, color: "border-slate-300" },
    td_campaign: { icon: <Syringe className="w-4 h-4 text-indigo-600" />, color: "border-indigo-300" },
  };

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">
          Simulation Scenarios & Operational Stress Injections
        </h1>
        <p className="text-sm text-slate-500 font-medium">
          Trigger deterministic epidemiological outbreaks, equipment breakdowns, or clerical defects across the digital district twin.
        </p>
      </div>

      {/* Control Console: Clock Speed & Simulation Reset */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
        {/* Clock Controls */}
        <div className="md:col-span-7 p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase font-bold tracking-wider text-slate-600 flex items-center space-x-1.5">
              <FastForward className="w-4 h-4 text-teal-600" />
              <span>Simulation Clock & Speed Multiplier</span>
            </span>
            <span className="font-mono text-xs font-bold text-teal-800 bg-teal-50 px-2 py-0.5 rounded border border-teal-200">
              {clock?.today || "2026-11-01"} • Day {clock?.day_index ?? 1}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => clockMutation.mutate({ running: !clock?.is_running })}
              className={`flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-xs ${
                clock?.is_running
                  ? "bg-amber-600 hover:bg-amber-700 text-white"
                  : "bg-teal-700 hover:bg-teal-800 text-white"
              }`}
            >
              {clock?.is_running ? (
                <>
                  <Pause className="w-3.5 h-3.5" />
                  <span>Pause Clock</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-white" />
                  <span>Start Clock</span>
                </>
              )}
            </button>

            {/* Speed Multipliers */}
            <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-bold">
              {[1, 2, 5, 10, 30].map((spd) => {
                const isSelected = (clock?.speed ?? 1) === spd;
                return (
                  <button
                    key={spd}
                    onClick={() => clockMutation.mutate({ running: true, speed: spd })}
                    className={`px-3 py-1.5 rounded-lg transition-all ${
                      isSelected
                        ? "bg-slate-900 text-white shadow-xs"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-200"
                    }`}
                  >
                    {spd}×
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Reset Simulation with Seed */}
        <div className="md:col-span-5 p-5 bg-white border border-slate-200 rounded-xl shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase font-bold tracking-wider text-slate-600 flex items-center space-x-1.5">
              <RotateCcw className="w-4 h-4 text-slate-600" />
              <span>Deterministic Cluster Reset</span>
            </span>
            <span className="text-[11px] text-slate-400 font-medium">Seed Replay</span>
          </div>

          <div className="flex items-center space-x-2">
            <input
              type="number"
              value={resetSeed}
              onChange={(e) => setResetSeed(Number(e.target.value))}
              className="w-24 bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-xs font-mono font-bold text-slate-900 focus:ring-2 focus:ring-teal-500"
              placeholder="42"
            />
            <button
              onClick={() => resetMutation.mutate(resetSeed)}
              disabled={resetMutation.isPending}
              className="flex-1 bg-slate-900 hover:bg-slate-800 active:scale-95 text-white font-bold px-4 py-2 rounded-xl text-xs transition-colors flex items-center justify-center space-x-1.5 shadow-xs"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resetMutation.isPending ? "animate-spin" : ""}`} />
              <span>{resetMutation.isPending ? "Resetting District..." : "Reset All Twin Nodes"}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Scenarios Grid with One-Line Descriptions */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          Available Simulation Scenarios ({scenarios.length})
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {scenarios.map((sc) => {
            const meta = scenarioMeta[sc.id] || {
              icon: <Sliders className="w-4 h-4 text-slate-600" />,
              color: "border-slate-200",
            };
            const isActivating = activatingId === sc.id;

            return (
              <div
                key={sc.id}
                className={`p-5 rounded-2xl border transition-all flex flex-col justify-between space-y-3 ${
                  sc.active
                    ? "bg-teal-50/60 border-teal-400 ring-2 ring-teal-500/20 shadow-xs"
                    : "bg-white border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-black text-slate-900 text-sm flex items-center space-x-2">
                      {meta.icon}
                      <span>{sc.title || sc.name}</span>
                    </span>
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                        sc.active
                          ? "bg-teal-700 text-white"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {sc.active ? "ACTIVE" : "STANDBY"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 font-medium leading-relaxed">
                    {sc.desc}
                  </p>
                </div>

                <button
                  onClick={() => activateMutation.mutate(sc.id)}
                  disabled={sc.active || isActivating}
                  className={`w-full py-2 px-3 rounded-xl text-xs font-bold transition-all shadow-2xs flex items-center justify-center space-x-1.5 ${
                    sc.active
                      ? "bg-teal-100 text-teal-800 cursor-not-allowed font-black"
                      : "bg-slate-900 hover:bg-slate-800 text-white active:scale-95"
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>{sc.active ? "Currently Injected" : isActivating ? "Injecting..." : "Inject Scenario"}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Real-Time Active Epidemiological Signals Feed */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Radio className="w-4 h-4 text-teal-600 animate-pulse" />
            <h3 className="font-bold text-slate-900 text-sm">
              Active IDSP Epidemiological & Infrastructure Signal Feed ({signals.length})
            </h3>
          </div>
          <span className="text-xs font-semibold px-2.5 py-0.5 rounded bg-teal-50 text-teal-800 border border-teal-200">
            Sim-Control GET /signals
          </span>
        </div>

        <div className="divide-y divide-slate-100 text-xs">
          {signals.length === 0 ? (
            <div className="p-6 text-center text-slate-400">
              No active signals or shock bulletins currently active.
            </div>
          ) : (
            signals.map((sig) => (
              <div key={sig.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                    <span className="font-mono font-bold bg-slate-900 text-white px-2 py-0.5 rounded text-[11px]">
                      {sig.id}
                    </span>
                    <h4 className="font-bold text-slate-900 text-sm">{sig.title}</h4>
                    <span className="text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded">
                      {sig.type}
                    </span>
                    <span className="text-teal-700 font-bold bg-teal-50 border border-teal-200 px-2 py-0.5 rounded">
                      Facility: {sig.facility_id || "ALL"}
                    </span>
                  </div>
                  <p className="text-slate-600 font-medium">
                    {sig.reason}
                  </p>
                </div>

                <div className="flex md:flex-col items-end shrink-0 space-y-1">
                  <span className="text-sm font-black text-rose-600">
                    {sig.multiplier ? `${sig.multiplier}× Demand Multiplier` : "Alert Active"}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {sig.start_date} &rarr; {sig.end_date}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
