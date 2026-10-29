import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, RotateCw, CheckCircle, ShieldAlert, Cpu } from "lucide-react";
import { api } from "../../lib/api";
import { PlanRun, Drug, Facility } from "../../types";
import { PlanKpiHeader } from "./PlanKpiHeader";
import { OrdersTable } from "./OrdersTable";
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

  const { data: plan, isLoading: isPlanLoading } = useQuery<PlanRun>({
    queryKey: ["plan"],
    queryFn: () => api.getLatestPlan(),
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
    mutationFn: () => api.runPlan("live"),
    onMutate: () => {
      setIsSolving(true);
      onSimulateProgress("SNAPSHOT_FEFO", 20, "PlatformEngine");
      setTimeout(() => onSimulateProgress("FEASIBILITY_F1_F6", 50, "PlatformEngine"), 400);
      setTimeout(() => onSimulateProgress("QUBO_SOLVER", 85, "QpiAI_LocalProvider"), 900);
    },
    onSuccess: (newPlan) => {
      setTimeout(() => {
        setIsSolving(false);
        onClearProgress();
        queryClient.setQueryData(["plan"], newPlan);
        queryClient.invalidateQueries({ queryKey: ["positions"] });
      }, 1400);
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

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      {/* Top Action Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            Redistribution Optimization Plan (CP1)
          </h1>
          <p className="text-sm text-slate-500 font-medium">
            Lot-by-lot redistribution from near-expiry surplus facilities to acute deficit facilities
          </p>
        </div>

        <button
          onClick={() => runPlanMutation.mutate()}
          disabled={isSolving}
          className={`flex items-center space-x-2 px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all ${
            isSolving
              ? "bg-slate-400 text-white cursor-not-allowed"
              : "bg-teal-600 hover:bg-teal-700 text-white active:scale-95"
          }`}
        >
          {isSolving ? (
            <>
              <RotateCw className="w-4 h-4 animate-spin" />
              <span>Solving QUBO & Constraints...</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-white" />
              <span>Run Redistribution Plan</span>
            </>
          )}
        </button>
      </div>

      {/* Plan Solving Progress Bar (from SSE plan.progress) */}
      {(isSolving || planProgress) && (
        <div className="p-4 bg-teal-50 border border-teal-200 rounded-xl space-y-2 shadow-sm animate-in fade-in duration-300">
          <div className="flex items-center justify-between text-xs font-bold text-teal-900">
            <div className="flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-teal-700 animate-spin" />
              <span>
                Stage: {planProgress?.stage || "SOLVING_QUBO_ALLOCATION"}
              </span>
              <span className="text-teal-600 font-mono">
                [{planProgress?.active_tier || "QpiAI Opt LocalProvider"}]
              </span>
            </div>
            <span>{planProgress?.percent_complete || 65}%</span>
          </div>

          <div className="w-full bg-teal-200 h-2.5 rounded-full overflow-hidden">
            <div
              className="bg-teal-600 h-full rounded-full transition-all duration-300"
              style={{ width: `${planProgress?.percent_complete || 65}%` }}
            />
          </div>
        </div>
      )}

      {/* KPI Header */}
      <PlanKpiHeader plan={plan} />

      {/* Orders Table */}
      <OrdersTable
        orders={plan.orders}
        drugs={drugs}
        facilities={facilities}
        onApproveOrder={(orderId) => approveMutation.mutate(orderId)}
      />
    </div>
  );
};
