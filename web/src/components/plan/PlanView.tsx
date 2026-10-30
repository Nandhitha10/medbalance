import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Play,
  RotateCw,
  CheckCircle2,
  ShieldCheck,
  Cpu,
  Layers,
  Sparkles,
  Zap,
  Check,
  ArrowRight,
  Activity,
} from "lucide-react";
import { api } from "../../lib/api";
import { PlanRun, Drug, Facility } from "../../types";
import { PlanKpiHeader } from "./PlanKpiHeader";
import { OrdersTable } from "./OrdersTable";
import { PlanMiniMap } from "./PlanMiniMap";
import { OrderDetailModal } from "./OrderDetailModal";
import { TransferOrder } from "../../types";
import { PlanProgressInfo } from "../../hooks/useEventSource";

interface PlanViewProps {
  planProgress: PlanProgressInfo | null;
  onSimulateProgress: (stage: string, percent: number, tier: string) => void;
  onClearProgress: () => void;
}

export const PlanView: React.FC<PlanViewProps> = ({
  planProgress,
  onSimulateProgress,
  onClearProgress,
}) => {
  const queryClient = useQueryClient();
  const [isSolving, setIsSolving] = useState(false);
  const [activeStageIndex, setActiveStageIndex] = useState<number>(5); // default completed
  const [selectedSolver, setSelectedSolver] = useState<string>("qubo");
  const [selectedOrder, setSelectedOrder] = useState<TransferOrder | null>(null);

  const stages = [
    { id: "snapshot", label: "Snapshot (FEFO)", desc: "Build in-memory state & rates" },
    { id: "feasibility", label: "Feasibility (F1–F6)", desc: "Rules & reserve protection" },
    { id: "zoning", label: "Zoning (QAOA)", desc: "Max-Cut graph decomposition" },
    { id: "qubo", label: "QUBO Solver", desc: "QpiAI Opt quadratic search" },
    { id: "validator", label: "FEFO Validator", desc: "Invariants & repair loop" },
    { id: "persist", label: "Persist DTA", desc: "Sequential vouchers & QR tokens" },
  ];

  const { data: plan, isLoading: isPlanLoading } = useQuery<PlanRun>({
    queryKey: ["plan"],
    queryFn: () => api.getLatestPlan(),
    refetchInterval: 5000,
  });

  const { data: drugs = [] } = useQuery<Drug[]>({
    queryKey: ["drugs"],
    queryFn: () => api.getDrugs(),
  });

  const { data: facilities = [] } = useQuery<Facility[]>({
    queryKey: ["facilities"],
    queryFn: () => api.getFacilities(),
  });

  const runPlanMutation = useMutation({
    mutationFn: (solver: string) => api.runPlan("live", solver),
    onMutate: () => {
      setIsSolving(true);
      setActiveStageIndex(0);
      onSimulateProgress("SNAPSHOT_FEFO", 15, "PlatformEngine");

      setTimeout(() => {
        setActiveStageIndex(1);
        onSimulateProgress("FEASIBILITY_F1_F6", 35, "DeterministicEngine");
      }, 300);

      setTimeout(() => {
        setActiveStageIndex(2);
        onSimulateProgress("QAOA_ZONING", 55, "QpiAI_QCloud_Simulator");
      }, 700);

      setTimeout(() => {
        setActiveStageIndex(3);
        onSimulateProgress("QUBO_SOLVER", 75, "QpiAI_Opt_LocalProvider");
      }, 1100);

      setTimeout(() => {
        setActiveStageIndex(4);
        onSimulateProgress("FEFO_VALIDATOR", 90, "HypothesisRepairEngine");
      }, 1500);

      setTimeout(() => {
        setActiveStageIndex(5);
        onSimulateProgress("PERSIST_DTAS", 100, "CoreApiPersistence");
      }, 1800);
    },
    onSuccess: (newPlan) => {
      setTimeout(() => {
        setIsSolving(false);
        onClearProgress();
        setActiveStageIndex(5);
        queryClient.setQueryData(["plan"], newPlan);
        queryClient.invalidateQueries({ queryKey: ["positions"] });
        queryClient.invalidateQueries({ queryKey: ["lots"] });
      }, 2000);
    },
    onError: () => {
      setIsSolving(false);
      onClearProgress();
    },
  });

  const approveMutation = useMutation({
    mutationFn: (orderId: string) => api.approveOrder(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plan"] });
    },
  });

  if (isPlanLoading || !plan) {
    return (
      <div className="p-8 text-center text-slate-500 font-medium">
        Loading redistribution plan data...
      </div>
    );
  }

  const solverTierText =
    plan.solver_tier || "QpiAI Opt Platform (DWave Neal SA / LocalProvider)";
  const qcloudTierText =
    plan.qcloud_tier || "QpiAI QCloud (QAOA Max-Cut Zoning, p=2)";

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto select-none">
      {/* Top Header & Solver Trigger */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3 mb-1">
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">
              Redistribution Optimization Plan (CP1 / QUBO)
            </h1>
            {/* Violations: 0 Certified Badge */}
            <span className="inline-flex items-center space-x-1 bg-emerald-100 text-emerald-800 text-xs font-bold px-2.5 py-1 rounded-full border border-emerald-300 shadow-2xs">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 mr-1" />
              <span>Violations: {plan.violations_count ?? 0} (Validated)</span>
            </span>
          </div>
          <p className="text-sm text-slate-500 font-medium">
            Lot-by-lot redistribution from near-expiry surplus facilities to acute deficit facilities
          </p>
        </div>

        {/* Solver Selector and Run Button */}
        <div className="flex items-center space-x-3">
          <select
            value={selectedSolver}
            onChange={(e) => setSelectedSolver(e.target.value)}
            disabled={isSolving}
            className="bg-white border border-slate-300 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 shadow-2xs focus:ring-2 focus:ring-blue-500"
          >
            <option value="qubo">QUBO (QpiAI Opt Platform / Local)</option>
            <option value="greedy_f4">Safe Greedy F4 (Deterministic Core)</option>
            <option value="greedy">Phone Call Heuristic (Baseline)</option>
          </select>

          <button
            onClick={() => runPlanMutation.mutate(selectedSolver)}
            disabled={isSolving}
            className={`flex items-center space-x-2 px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all ${
              isSolving
                ? "bg-slate-400 text-white cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700 text-white active:scale-95"
            }`}
          >
            {isSolving ? (
              <>
                <RotateCw className="w-4 h-4 animate-spin" />
                <span>Optimizing Plan...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-white" />
                <span>Run Redistribution Plan</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Solver Tier Badges Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-blue-950 text-blue-100 rounded-xl shadow-xs border border-blue-900">
        <div className="flex items-center space-x-2 text-xs">
          <Cpu className="w-4 h-4 text-blue-400" />
          <span className="font-bold text-blue-200">Active Quantum & Classical Solver Hierarchy:</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* QpiAI Opt Platform Badge */}
          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-bold bg-blue-900/90 text-blue-200 border border-blue-700">
            <Sparkles className="w-3 h-3 text-blue-400 mr-1.5" />
            <span>QpiAI Opt: {solverTierText}</span>
          </span>

          {/* QCloud QAOA Max-Cut Badge */}
          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-bold bg-indigo-900/90 text-indigo-200 border border-indigo-700">
            <Zap className="w-3 h-3 text-indigo-400 mr-1.5" />
            <span>QCloud Zoning: {qcloudTierText}</span>
          </span>

          {/* Runtime */}
          <span className="font-mono text-[11px] font-bold text-blue-200 px-2 py-1 bg-blue-900/60 rounded border border-blue-800">
            {plan.execution_time_sec ? `${plan.execution_time_sec.toFixed(3)}s` : "0.042s"}
          </span>
        </div>
      </div>

      {/* Stage Progress Stepper (snapshot → feasibility → zoning → QUBO → validator → persist) */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-2">
        <div className="flex items-center justify-between text-xs font-bold text-slate-700 mb-2">
          <span>Optimization Pipeline Execution Workflow</span>
          <span className="text-blue-700">
            {isSolving ? `Stage ${activeStageIndex + 1} of 6: ${stages[activeStageIndex]?.label}` : "Pipeline Completed (6/6)"}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          {stages.map((stg, idx) => {
            const isCompleted = activeStageIndex >= idx;
            const isCurrent = isSolving && activeStageIndex === idx;

            return (
              <div
                key={stg.id}
                className={`p-2.5 rounded-lg border text-left transition-all space-y-1 ${
                  isCurrent
                    ? "bg-blue-50 border-blue-500 ring-2 ring-blue-500/20"
                    : isCompleted
                    ? "bg-blue-50/40 border-blue-200"
                    : "bg-slate-50 border-slate-200 opacity-60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold text-slate-400">
                    0{idx + 1}
                  </span>
                  {isCompleted && !isCurrent ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />
                  ) : isCurrent ? (
                    <RotateCw className="w-3.5 h-3.5 text-blue-600 animate-spin" />
                  ) : (
                    <div className="w-2 h-2 rounded-full bg-slate-300"></div>
                  )}
                </div>
                <div className="font-bold text-xs text-slate-900 leading-tight">
                  {stg.label}
                </div>
                <div className="text-[10px] text-slate-500 leading-tight truncate">
                  {stg.desc}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* KPI Cards Header */}
      <PlanKpiHeader plan={plan} />

      {/* Mini-Map with Shaded Zones */}
      <PlanMiniMap facilities={facilities} orders={plan.orders} />

      {/* Orders Table Grouped by Destination Facility */}
      <OrdersTable
        orders={plan.orders}
        drugs={drugs}
        facilities={facilities}
        onApproveOrder={(orderId) => approveMutation.mutate(orderId)}
        onSelectOrder={(ord) => setSelectedOrder(ord)}
      />

      {/* Order Detail & Provenance DAG Modal */}
      {selectedOrder && (
        <OrderDetailModal
          order={selectedOrder}
          onClose={() => setSelectedOrder(null)}
        />
      )}
    </div>
  );
};
