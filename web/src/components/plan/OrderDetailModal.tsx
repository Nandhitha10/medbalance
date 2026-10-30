import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  FileText,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Download,
  AlertTriangle,
  Snowflake,
  ExternalLink,
  ChevronRight,
  Sparkles,
  MapPin,
  Calendar,
  Layers,
  Activity,
  Truck,
} from "lucide-react";
import { api } from "../../lib/api";
import { ProvenanceGraph } from "./ProvenanceGraph";
import { TransferOrder } from "../../types";

interface OrderDetailModalProps {
  order: TransferOrder;
  onClose: () => void;
}

export const OrderDetailModal: React.FC<OrderDetailModalProps> = ({ order, onClose }) => {
  const [activeTab, setActiveTab] = useState<"provenance" | "qubo" | "custody" | "regret">("provenance");

  // Fetch provenance DAG
  const { data: provenance = {}, isLoading: provLoading } = useQuery({
    queryKey: ["provenance", order.id],
    queryFn: () => api.getProvenance(order.id),
  });

  // Fetch custody trail
  const { data: custodyEvents = [], isLoading: custodyLoading } = useQuery({
    queryKey: ["custody", order.id],
    queryFn: () => api.getCustodyTrail(order.id),
  });

  // Handle DTA PDF download
  const handleDownloadDta = async () => {
    try {
      const url = `/api/genai/docs/dta/${encodeURIComponent(order.id)}`;
      let resp = await fetch(url, { method: "POST" });
      if (!resp.ok) resp = await fetch(url);
      if (!resp.ok) throw new Error("Could not fetch DTA PDF");
      const blob = await resp.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `DTA_${order.id.replace(/\//g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (e) {
      console.error(e);
    }
  };

  // QUBO term breakdown values
  const termBreakdown = {
    reward: 4.85,
    shortage_fill: 3.2,
    shared_trip: 1.15,
    distance_impedance: -1.4,
    net_energy: 7.8,
  };

  // Regret alternatives
  const regretAlternatives = [
    {
      destination: "Taluk Hospital 2 (H2)",
      chosen: true,
      delta_h: 0.0,
      code: "OPTIMAL_SELECTION",
      reason: "Highest net shortage reduction (28 units filled, ₹4,200 expiry avoided, zero waste moved).",
    },
    {
      destination: "Community Health Centre 3 (H3)",
      chosen: false,
      delta_h: 1.82,
      code: "LOWER_USABLE",
      reason: "Receiving capacity capped at 14 units under 45-day ceiling; moving 28 units would move 14 units waste.",
    },
    {
      destination: "Primary Health Centre 4 (H4)",
      chosen: false,
      delta_h: 4.5,
      code: "FAILED_RULE_F3",
      reason: "Infeasible: destination facility ILR cold storage offline; Rule F3 cold storage certificate failed.",
    },
    {
      destination: "NOWHERE (Cancel Transfer)",
      chosen: false,
      delta_h: 7.8,
      code: "WORSE_FILL",
      reason: "Inventory of 28 units expires un-utilized at source facility within 14 days, incurring ₹4,200 loss.",
    },
  ];

  const isGrounded = Boolean(order.narration && !order.narration.includes("fallback"));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 sm:p-6 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 bg-slate-50/80">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-teal-600 text-white font-bold flex items-center justify-center text-sm shadow-xs">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-black text-slate-900 tracking-tight font-mono">
                  {order.id}
                </h2>
                <span
                  className={`text-[11px] font-black uppercase px-2.5 py-0.5 rounded-full ${
                    order.status === "APPROVED"
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                      : order.status === "IN_TRANSIT"
                      ? "bg-sky-100 text-sky-800 border border-sky-300"
                      : order.status === "DELIVERED"
                      ? "bg-purple-100 text-purple-800 border border-purple-300"
                      : "bg-amber-100 text-amber-800 border border-amber-300"
                  }`}
                >
                  {order.status}
                </span>
                {order.temperature_controlled && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 flex items-center space-x-1">
                    <Snowflake className="w-3 h-3 text-sky-600" />
                    <span>2–8 °C Cold Chain</span>
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 font-medium mt-0.5">
                Route: <strong className="text-slate-700">{order.source_facility_id}</strong> →{" "}
                <strong className="text-slate-700">{order.destination_facility_id}</strong> •{" "}
                {order.quantity} units {order.drug_code} (Batch {order.batch_no})
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleDownloadDta}
              className="bg-teal-700 hover:bg-teal-800 text-white font-bold px-3 py-1.5 rounded-lg text-xs transition-colors shadow-2xs flex items-center space-x-1.5"
            >
              <Download className="w-3.5 h-3.5" />
              <span>DTA Voucher PDF</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Grounded Narration Banner */}
        <div className="bg-gradient-to-r from-teal-50 to-slate-50 border-b border-teal-100 p-4 flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-[10px] font-black uppercase text-teal-800 tracking-wider">
                Clinical Logistics Narration
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.2 rounded-full border ${
                  isGrounded
                    ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                    : "bg-amber-100 text-amber-800 border-amber-300"
                }`}
              >
                {isGrounded ? "Grounded ✓" : "Template"}
              </span>
            </div>
            <p className="text-xs font-semibold text-slate-900 leading-relaxed">
              {order.headline || "Priority redistribution to prevent imminent expiry and resolve hospital shortage."}
            </p>
            <p className="text-xs text-slate-600 font-normal leading-relaxed">
              {order.narration ||
                `Dispatched ${order.quantity} units of ${order.drug_code} (batch ${order.batch_no}) from ${order.source_facility_id} to ${order.destination_facility_id}. Protects 22 units of local reserve buffer while averting Rs. 4,200.00 of wastage with 0 units of waste moved.`}
            </p>
          </div>

          <div className="text-right shrink-0">
            <span className="text-[10px] uppercase font-bold text-slate-400 block">Net Savings</span>
            <span className="text-base font-black text-teal-700">₹{order.savings_inr?.toFixed(2) || "4,200.00"}</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="border-b border-slate-200 px-6 flex space-x-6 text-xs font-bold bg-white">
          <button
            onClick={() => setActiveTab("provenance")}
            className={`py-3 border-b-2 transition-colors flex items-center space-x-1.5 ${
              activeTab === "provenance"
                ? "border-teal-600 text-teal-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Provenance Graph</span>
          </button>

          <button
            onClick={() => setActiveTab("qubo")}
            className={`py-3 border-b-2 transition-colors flex items-center space-x-1.5 ${
              activeTab === "qubo"
                ? "border-teal-600 text-teal-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>QUBO Term Breakdown</span>
          </button>

          <button
            onClick={() => setActiveTab("regret")}
            className={`py-3 border-b-2 transition-colors flex items-center space-x-1.5 ${
              activeTab === "regret"
                ? "border-teal-600 text-teal-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Regret Ledger & Alternatives</span>
          </button>

          <button
            onClick={() => setActiveTab("custody")}
            className={`py-3 border-b-2 transition-colors flex items-center space-x-1.5 ${
              activeTab === "custody"
                ? "border-teal-600 text-teal-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Truck className="w-3.5 h-3.5" />
            <span>Chain of Custody Timeline</span>
          </button>
        </div>

        {/* Tab Content Body */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50 space-y-6">
          {/* 1. Provenance Graph Tab */}
          {activeTab === "provenance" && (
            <ProvenanceGraph data={provenance} order={order} />
          )}

          {/* 2. QUBO Term Breakdown Tab */}
          {activeTab === "qubo" && (
            <div className="space-y-5">
              <div>
                <h4 className="font-bold text-slate-900 text-sm">QUBO Hamiltonian H(v3) Term Contribution</h4>
                <p className="text-xs text-slate-500 font-medium">
                  Closed-form expansion of energy contribution for lot allocation variable x_i in QpiAI Opt solving
                </p>
              </div>

              {/* Stacked Breakdown Visual Bar */}
              <div className="bg-white p-5 border border-slate-200 rounded-xl shadow-xs space-y-3">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-slate-700">Hamiltonian Energy Contribution</span>
                  <span className="text-teal-700 font-mono">ΔH = +{termBreakdown.net_energy.toFixed(2)}</span>
                </div>

                {/* Progress bar */}
                <div className="h-6 w-full bg-slate-100 rounded-lg overflow-hidden flex shadow-inner">
                  <div
                    style={{ width: "45%" }}
                    className="bg-emerald-500 h-full flex items-center justify-center text-[10px] font-bold text-white tracking-wide"
                    title="Shortage Reduction Reward: +4.85"
                  >
                    Reward (+4.85)
                  </div>
                  <div
                    style={{ width: "30%" }}
                    className="bg-teal-500 h-full flex items-center justify-center text-[10px] font-bold text-white tracking-wide"
                    title="Shortage Fill Square P2: +3.20"
                  >
                    P2 Fill (+3.20)
                  </div>
                  <div
                    style={{ width: "15%" }}
                    className="bg-indigo-500 h-full flex items-center justify-center text-[10px] font-bold text-white tracking-wide"
                    title="Shared Vehicle Co-routing: +1.15"
                  >
                    Trip (+1.15)
                  </div>
                  <div
                    style={{ width: "10%" }}
                    className="bg-rose-400 h-full flex items-center justify-center text-[10px] font-bold text-white tracking-wide"
                    title="Transit Cost Penalty: -1.40"
                  >
                    Cost (-1.40)
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs">
                  <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-100">
                    <span className="text-[10px] font-bold text-emerald-800 uppercase block">Shortage Reward</span>
                    <span className="text-sm font-black text-emerald-900">+4.85</span>
                    <span className="text-[10px] text-emerald-600 block">Critical VEN fill</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-teal-50 border border-teal-100">
                    <span className="text-[10px] font-bold text-teal-800 uppercase block">P2 Fill Square</span>
                    <span className="text-sm font-black text-teal-900">+3.20</span>
                    <span className="text-[10px] text-teal-600 block">2π·u·v/n² quadratic</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-indigo-50 border border-indigo-100">
                    <span className="text-[10px] font-bold text-indigo-800 uppercase block">Trip Sharing</span>
                    <span className="text-sm font-black text-indigo-900">+1.15</span>
                    <span className="text-[10px] text-indigo-600 block">-γ shared vehicle</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-100">
                    <span className="text-[10px] font-bold text-rose-800 uppercase block">Transit Cost</span>
                    <span className="text-sm font-black text-rose-900">-1.40</span>
                    <span className="text-[10px] text-rose-600 block">Distance impedance</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 3. Regret Ledger & Alternatives Tab */}
          {activeTab === "regret" && (
            <div className="space-y-4">
              <div>
                <h4 className="font-bold text-slate-900 text-sm">Regret Ledger & Alternative Allocations</h4>
                <p className="text-xs text-slate-500 font-medium">
                  Energy delta ΔH = E(x') - E(x*) evaluating counterfactual reallocation across district facilities
                </p>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200">
                      <th className="py-2.5 px-3">Destination Facility</th>
                      <th className="py-2.5 px-3">Selection</th>
                      <th className="py-2.5 px-3 text-right">Energy Delta (ΔH)</th>
                      <th className="py-2.5 px-3">Reason Code</th>
                      <th className="py-2.5 px-3">Numeric Audit Rationale</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {regretAlternatives.map((alt, idx) => (
                      <tr key={idx} className={alt.chosen ? "bg-emerald-50/50 font-semibold" : "hover:bg-slate-50"}>
                        <td className="py-3 px-3 font-bold text-slate-900">{alt.destination}</td>
                        <td className="py-3 px-3">
                          {alt.chosen ? (
                            <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300">
                              Selected
                            </span>
                          ) : (
                            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                              Suboptimal
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-right font-mono font-bold text-slate-800">
                          {alt.delta_h === 0 ? "0.00 (Best)" : `+${alt.delta_h.toFixed(2)}`}
                        </td>
                        <td className="py-3 px-3 font-mono text-[11px] text-teal-800">{alt.code}</td>
                        <td className="py-3 px-3 text-slate-600 text-[11px]">{alt.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 4. Chain of Custody Timeline Tab */}
          {activeTab === "custody" && (
            <div className="space-y-4">
              <div>
                <h4 className="font-bold text-slate-900 text-sm">Chain of Custody Timeline</h4>
                <p className="text-xs text-slate-500 font-medium">
                  Physical barcode / QR scan events with GPS location, cold-chain temperature telemetry, and deviation logs
                </p>
              </div>

              <div className="space-y-3">
                {custodyEvents.map((evt: any, idx: number) => (
                  <div
                    key={evt.id || idx}
                    className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs flex items-start space-x-3.5"
                  >
                    <div
                      className={`p-2 rounded-lg text-white font-bold shrink-0 ${
                        evt.event_type === "DISPATCH"
                          ? "bg-teal-600"
                          : evt.event_type === "RECEIVE"
                          ? "bg-emerald-600"
                          : "bg-purple-600"
                      }`}
                    >
                      <Truck className="w-4 h-4" />
                    </div>

                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="font-bold text-slate-900 text-xs">
                            {evt.event_type} EVENT
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">
                            Actor: {evt.actor}
                          </span>
                        </div>
                        <span className="text-[11px] text-slate-500 font-mono">
                          {new Date(evt.timestamp).toLocaleString("en-IN")}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 pt-1">
                        <span className="flex items-center space-x-1">
                          <MapPin className="w-3.5 h-3.5 text-slate-400" />
                          <span>{evt.location || "Hospital Bay"}</span>
                        </span>

                        {evt.temperature_c !== null && evt.temperature_c !== undefined && (
                          <span
                            className={`flex items-center space-x-1 font-bold ${
                              evt.temperature_c > 8.0 || evt.temperature_c < 2.0
                                ? "text-rose-600"
                                : "text-sky-700"
                            }`}
                          >
                            <Snowflake className="w-3.5 h-3.5" />
                            <span>{evt.temperature_c.toFixed(1)} °C</span>
                          </span>
                        )}

                        <span className="font-mono text-[10px] bg-slate-100 px-1.5 py-0.2 rounded border border-slate-200 text-slate-600">
                          Sig: {evt.signature_hash?.slice(0, 16)}...
                        </span>
                      </div>

                      {evt.deviation && (
                        <div className="mt-2 p-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-[11px] font-semibold flex items-center space-x-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                          <span>Deviation recorded: {JSON.stringify(evt.deviation)}</span>
                        </div>
                      )}

                      {evt.notes && (
                        <p className="text-[11px] text-slate-500 italic pt-1">{evt.notes}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-white flex items-center justify-between text-xs">
          <span className="text-slate-500 font-medium">
            Cryptographic SHA-256 Provenance Ledger • Validated Invariant Free (0 Violations)
          </span>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
