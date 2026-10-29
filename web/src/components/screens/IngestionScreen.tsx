import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { StockReport, ExtractionItem, Drug } from "../../types";
import {
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  Clock,
  Sparkles,
  Check,
  X,
  Edit3,
  RotateCcw,
  RefreshCw,
  Languages,
  ChevronRight,
  ArrowLeft,
  ShieldCheck,
  AlertTriangle,
  FileText,
  MessageSquare,
  Activity,
  Layers,
} from "lucide-react";

export const IngestionScreen: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedReportId, setSelectedReportId] = useState<string>("REP-H3-20261101");
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editDrugCode, setEditDrugCode] = useState<string>("");
  const [editBatchNo, setEditBatchNo] = useState<string>("");
  const [editExpiry, setEditExpiry] = useState<string>("");
  const [editQuantity, setEditQuantity] = useState<number>(0);
  const [isPulling, setIsPulling] = useState<boolean>(false);

  const { data: reports = [], isLoading: isReportsLoading } = useQuery<StockReport[]>({
    queryKey: ["reports"],
    queryFn: () => api.getReports(),
    refetchInterval: 5000,
  });

  const { data: drugs = [] } = useQuery<Drug[]>({
    queryKey: ["drugs"],
    queryFn: () => api.getDrugs(),
  });

  const pullMutation = useMutation({
    mutationFn: () => api.triggerIngestPull(),
    onMutate: () => setIsPulling(true),
    onSuccess: () => {
      setTimeout(() => {
        setIsPulling(false);
        queryClient.invalidateQueries({ queryKey: ["reports"] });
        queryClient.invalidateQueries({ queryKey: ["reviews"] });
      }, 800);
    },
    onError: () => setIsPulling(false),
  });

  const resolveMutation = useMutation({
    mutationFn: ({
      reviewId,
      action,
      overrideData,
    }: {
      reviewId: string;
      action: string;
      overrideData?: any;
    }) => api.resolveReview(reviewId, action, overrideData),
    onSuccess: () => {
      setEditingItemId(null);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["reviews"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["lots"] });
    },
  });

  const selectedReport = reports.find((r) => r.id === selectedReportId) || reports[0];

  const handleStartEdit = (item: ExtractionItem) => {
    setEditingItemId(item.id);
    setEditDrugCode(item.suggested_patch?.drug_code || item.drug_code || (drugs[0]?.code || "INS-REG"));
    setEditBatchNo(item.suggested_patch?.batch_no || item.batch_no || `BATCH-${item.id}`);
    setEditExpiry(item.suggested_patch?.expiry || item.expiry || "2026-11-30");
    setEditQuantity(item.suggested_patch?.quantity ?? item.quantity ?? 10);
  };

  const handleSaveCorrection = (reviewId: string) => {
    resolveMutation.mutate({
      reviewId,
      action: "CORRECT",
      overrideData: {
        drug_code: editDrugCode,
        batch_no: editBatchNo,
        expiry: editExpiry,
        quantity: editQuantity,
      },
    });
  };

  const channels = [
    {
      code: "H1",
      facility: "H1 SIM-DH Jayanagar",
      format: "FHIR R4 InventoryReport",
      status: "Automated Polling",
      confidence: "99.8%",
      badgeColor: "bg-teal-50 text-teal-800 border-teal-300",
      type: "FHIR JSON",
      icon: <Layers className="w-4 h-4 text-teal-600" />,
    },
    {
      code: "H2",
      facility: "H2 SIM-TGH Anekal",
      format: "Nightly CSV Export",
      status: "Auto-Ingested",
      confidence: "98.4%",
      badgeColor: "bg-teal-50 text-teal-800 border-teal-300",
      type: "CSV Stream",
      icon: <FileSpreadsheet className="w-4 h-4 text-emerald-600" />,
    },
    {
      code: "H3",
      facility: "H3 SIM-CHC Yelahanka",
      format: "Kannada WhatsApp / Chat",
      status: "AI Grounded (RapidFuzz)",
      confidence: "95.2%",
      badgeColor: "bg-indigo-50 text-indigo-800 border-indigo-300",
      type: "Multilingual LLM",
      icon: <MessageSquare className="w-4 h-4 text-indigo-600" />,
    },
    {
      code: "H4",
      facility: "H4 SIM-PHC Sarjapura",
      format: "Messy Text / Handwritten",
      status: "Vision & OCR Extraction",
      confidence: "91.5%",
      badgeColor: "bg-amber-50 text-amber-800 border-amber-300",
      type: "LLM Extraction",
      icon: <FileText className="w-4 h-4 text-amber-600" />,
    },
  ];

  const getConfidenceChip = (confidence: number = 0.85) => {
    const pct = Math.round(confidence * 100);
    if (confidence >= 0.85) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
          <Sparkles className="w-3 h-3 mr-1 text-emerald-600" />
          {pct}% Match (High)
        </span>
      );
    }
    if (confidence >= 0.6) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
          <AlertCircle className="w-3 h-3 mr-1 text-amber-600" />
          {pct}% Match (Review)
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
        <AlertTriangle className="w-3 h-3 mr-1 text-rose-600" />
        {pct}% Match (Low)
      </span>
    );
  };

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            Hospital Ingestion & Pharmacist Review Queue
          </h1>
          <p className="text-sm text-slate-500 font-medium">
            Heterogeneous multi-source ingestion (FHIR, CSV, Kannada WhatsApp, OCR) with deterministic grounding and safety verification
          </p>
        </div>

        <button
          onClick={() => pullMutation.mutate()}
          disabled={isPulling}
          className={`flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-bold shadow-xs transition-all ${
            isPulling
              ? "bg-slate-300 text-slate-600 cursor-not-allowed"
              : "bg-teal-700 hover:bg-teal-800 text-white active:scale-95"
          }`}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isPulling ? "animate-spin" : ""}`} />
          <span>{isPulling ? "Polling Facilities..." : "Trigger Hospital Pull"}</span>
        </button>
      </div>

      {/* Hospital Channels Protocol Strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {channels.map((ch) => (
          <div
            key={ch.code}
            onClick={() => {
              const match = reports.find((r) => r.facility_code === ch.code);
              if (match) setSelectedReportId(match.id);
            }}
            className={`p-4 bg-white border rounded-xl shadow-xs space-y-2 cursor-pointer transition-all ${
              selectedReport?.facility_code === ch.code
                ? "border-teal-500 ring-2 ring-teal-500/20 bg-teal-50/20"
                : "border-slate-200 hover:border-slate-300"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${ch.badgeColor}`}>
                {ch.type}
              </span>
              <span className="text-[11px] font-bold text-teal-700">{ch.confidence} Match</span>
            </div>
            <div className="flex items-center space-x-2">
              {ch.icon}
              <h4 className="font-bold text-slate-900 text-sm leading-tight truncate">{ch.facility}</h4>
            </div>
            <div className="text-xs text-slate-500 flex items-center justify-between pt-1 border-t border-slate-100">
              <span className="truncate">{ch.format}</span>
              <span className="flex items-center text-teal-700 font-semibold shrink-0 ml-1">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                Live
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Main Two-Column Master / Detail Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Side: Report List */}
        <div className="lg:col-span-4 bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <FileSpreadsheet className="w-4 h-4 text-teal-700" />
              <h3 className="font-bold text-slate-900 text-sm">Ingested Reports</h3>
            </div>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
              {reports.length} Total
            </span>
          </div>

          <div className="divide-y divide-slate-100 max-h-[640px] overflow-y-auto">
            {reports.map((rep) => {
              const isSelected = rep.id === selectedReport?.id;
              const hasAnomaly = (rep.anomalies_detected || 0) > 0 || rep.status === "NEEDS_REVIEW";

              return (
                <div
                  key={rep.id}
                  onClick={() => setSelectedReportId(rep.id)}
                  className={`p-3.5 cursor-pointer transition-all flex items-start justify-between gap-2 ${
                    isSelected
                      ? "bg-teal-50/70 border-l-4 border-l-teal-600"
                      : "hover:bg-slate-50"
                  }`}
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-xs font-bold text-slate-900">
                        {rep.id}
                      </span>
                      <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 border border-slate-200">
                        {rep.source_type}
                      </span>
                    </div>

                    <div className="text-xs font-semibold text-slate-800">
                      Facility: <span className="text-teal-900 font-bold">{rep.facility_code}</span>
                    </div>

                    <div className="text-[11px] text-slate-500 flex items-center space-x-2">
                      <span className="flex items-center">
                        <Clock className="w-3 h-3 mr-1 text-slate-400" />
                        {rep.received_at ? rep.received_at.split("T")[1]?.slice(0, 5) || "08:15" : "08:15"}
                      </span>
                      <span>•</span>
                      <span className="truncate">{rep.language || "English"}</span>
                    </div>
                  </div>

                  <div className="flex flex-col items-end space-y-1 shrink-0">
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        rep.status === "RESOLVED"
                          ? "bg-emerald-100 text-emerald-800"
                          : rep.status === "NEEDS_REVIEW"
                          ? "bg-amber-100 text-amber-800 border border-amber-300"
                          : "bg-teal-100 text-teal-800"
                      }`}
                    >
                      {rep.status}
                    </span>

                    {hasAnomaly && (
                      <span className="text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200 px-1.5 py-0.2 rounded flex items-center">
                        <AlertCircle className="w-3 h-3 mr-0.5" />
                        {rep.anomalies_detected || 1} Review
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Side: Report Detail (Raw Text Left vs Grounded Rows Right) */}
        <div className="lg:col-span-8 bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden flex flex-col">
          {/* Detail Header */}
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center space-x-3">
              <span className="font-mono text-sm font-bold bg-slate-900 text-white px-2.5 py-1 rounded">
                {selectedReport?.id}
              </span>
              <div>
                <h3 className="font-bold text-slate-900 text-sm">
                  Facility {selectedReport?.facility_code} Stock Report Detail
                </h3>
                <span className="text-xs text-slate-500 font-medium flex items-center space-x-2">
                  <span>Channel: {selectedReport?.source_type.toUpperCase()}</span>
                  <span>•</span>
                  <span className="text-teal-700 font-semibold flex items-center">
                    <Languages className="w-3 h-3 mr-1" />
                    {selectedReport?.language || "English"}
                  </span>
                </span>
              </div>
            </div>

            <span
              className={`text-xs font-bold px-2.5 py-1 rounded border ${
                selectedReport?.status === "NEEDS_REVIEW"
                  ? "bg-amber-50 text-amber-800 border-amber-300"
                  : selectedReport?.status === "RESOLVED"
                  ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                  : "bg-teal-50 text-teal-800 border-teal-300"
              }`}
            >
              Status: {selectedReport?.status}
            </span>
          </div>

          {/* Two-Pane Inspection: Raw Text (Left) vs Extracted Grounded Rows (Right) */}
          <div className="grid grid-cols-1 md:grid-cols-12 divide-y md:divide-y-0 md:divide-x divide-slate-200">
            {/* Raw Ingestion Payload Pane (with Noto Sans Kannada) */}
            <div className="md:col-span-5 p-4 space-y-3 bg-slate-50/50">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase font-bold tracking-wider text-slate-600 flex items-center space-x-1">
                  <FileText className="w-3.5 h-3.5 text-slate-500 mr-1" />
                  <span>Raw Ingest Payload</span>
                </span>
                {selectedReport?.language?.includes("Kannada") && (
                  <span className="text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded">
                    Noto Sans Kannada Active
                  </span>
                )}
              </div>

              {/* Raw Payload Display Box */}
              <div
                className={`p-3.5 rounded-lg border border-slate-200 bg-white font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap ${
                  selectedReport?.source_type === "chat" || selectedReport?.language?.includes("Kannada")
                    ? "font-kannada text-slate-900 text-sm leading-relaxed"
                    : "text-slate-800"
                }`}
                style={{ minHeight: "280px" }}
              >
                {selectedReport?.raw_content || "No raw content recorded."}
              </div>

              <div className="p-3 bg-slate-100 rounded-lg text-slate-600 text-[11px] space-y-1">
                <span className="font-bold text-slate-800 block">Grounding Protocol</span>
                <p>
                  Zero invented drug codes. LLM extracts candidate mentions; RapidFuzz string search matches against canonical drug catalog and multilingual aliases (including Kannada script).
                </p>
              </div>
            </div>

            {/* Extracted Rows & Pharmacist Review Pane */}
            <div className="md:col-span-7 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase font-bold tracking-wider text-slate-600">
                  Extracted Canonical Rows ({selectedReport?.items?.length || 0})
                </span>
                <span className="text-[11px] text-slate-500 font-medium">
                  {selectedReport?.items?.filter((i) => i.is_anomalous).length || 0} Anomalies Flagged
                </span>
              </div>

              <div className="space-y-3">
                {(!selectedReport?.items || selectedReport.items.length === 0) ? (
                  <div className="p-6 text-center text-xs text-slate-400">
                    No rows extracted for this report.
                  </div>
                ) : (
                  selectedReport.items.map((item) => {
                    const isEditing = editingItemId === item.id;
                    const isPending = item.is_anomalous && item.review_status === "PENDING";
                    const isResolved = item.review_status === "RESOLVED";
                    const isRejected = item.review_status === "REJECTED";

                    return (
                      <div
                        key={item.id}
                        className={`p-3.5 rounded-xl border transition-all text-xs space-y-2.5 ${
                          isPending
                            ? "border-amber-300 bg-amber-50/40 ring-1 ring-amber-400/30"
                            : isResolved
                            ? "border-emerald-200 bg-emerald-50/20"
                            : isRejected
                            ? "border-slate-200 bg-slate-50 opacity-60"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        {/* Row Header */}
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div className="flex items-center space-x-2">
                            <span className="font-mono font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded text-xs">
                              {item.drug_code || "UNKNOWN"}
                            </span>
                            {getConfidenceChip(item.confidence)}
                          </div>

                          <div className="flex items-center space-x-1.5">
                            {isResolved && (
                              <span className="text-[11px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded border border-emerald-300 flex items-center">
                                <Check className="w-3 h-3 mr-1" /> Approved
                              </span>
                            )}
                            {isRejected && (
                              <span className="text-[11px] font-bold text-rose-800 bg-rose-100 px-2 py-0.5 rounded border border-rose-300 flex items-center">
                                <X className="w-3 h-3 mr-1" /> Rejected
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Extracted Details Grid */}
                        <div className="grid grid-cols-3 gap-2 bg-slate-50/80 p-2 rounded-lg font-mono text-[11px]">
                          <div>
                            <span className="text-[10px] text-slate-400 block font-sans">Batch No</span>
                            <span className="font-bold text-slate-800 truncate block">
                              {item.batch_no || "N/A"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400 block font-sans">Expiry</span>
                            <span className="font-bold text-slate-800 truncate block">
                              {item.expiry || "N/A"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400 block font-sans">Quantity</span>
                            <span className="font-bold text-teal-800 truncate block">
                              {item.quantity?.toLocaleString() || 0} units
                            </span>
                          </div>
                        </div>

                        {/* Raw span reference */}
                        <div className="text-[11px] text-slate-500 font-mono italic">
                          "{item.raw_text}"
                        </div>

                        {/* Anomaly Flag & LLM Explanation */}
                        {item.is_anomalous && (
                          <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg space-y-1">
                            <div className="flex items-center space-x-1.5 text-amber-900 font-bold text-[11px]">
                              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                              <span>Anomaly Flag: {item.anomaly_type || "SUSPICIOUS_EXPIRY"}</span>
                            </div>
                            <p className="text-[11px] text-amber-800 font-medium leading-tight">
                              {item.anomaly_reason || "Clerical anomaly detected during grounding. Requires pharmacist review."}
                            </p>
                          </div>
                        )}

                        {/* Inline Pharmacist Correction Form */}
                        {isEditing && (
                          <div className="p-3 bg-teal-50 border border-teal-300 rounded-lg space-y-3 mt-2">
                            <span className="text-xs font-bold text-teal-900 block">
                              Pharmacist Correction Form
                            </span>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div>
                                <label className="block text-[10px] font-bold text-slate-600 mb-0.5">
                                  Drug Code (from Grounded Catalog)
                                </label>
                                <select
                                  value={editDrugCode}
                                  onChange={(e) => setEditDrugCode(e.target.value)}
                                  className="w-full bg-white border border-slate-300 rounded px-2 py-1 text-xs font-mono font-bold"
                                >
                                  {drugs.map((d) => (
                                    <option key={d.code} value={d.code}>
                                      {d.code} — {d.name}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-slate-600 mb-0.5">
                                  Batch Number
                                </label>
                                <input
                                  type="text"
                                  value={editBatchNo}
                                  onChange={(e) => setEditBatchNo(e.target.value)}
                                  className="w-full bg-white border border-slate-300 rounded px-2 py-1 text-xs font-mono font-bold"
                                />
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-slate-600 mb-0.5">
                                  Clinical Expiry (YYYY-MM-DD)
                                </label>
                                <input
                                  type="date"
                                  value={editExpiry}
                                  onChange={(e) => setEditExpiry(e.target.value)}
                                  className="w-full bg-white border border-slate-300 rounded px-2 py-1 text-xs font-mono font-bold"
                                />
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-slate-600 mb-0.5">
                                  Quantity (Base Units)
                                </label>
                                <input
                                  type="number"
                                  value={editQuantity}
                                  onChange={(e) => setEditQuantity(Number(e.target.value))}
                                  className="w-full bg-white border border-slate-300 rounded px-2 py-1 text-xs font-mono font-bold"
                                />
                              </div>
                            </div>

                            <div className="flex items-center space-x-2 pt-1">
                              <button
                                onClick={() => handleSaveCorrection(item.id)}
                                className="bg-teal-700 hover:bg-teal-800 text-white font-bold px-3 py-1.5 rounded text-xs flex items-center space-x-1"
                              >
                                <Check className="w-3.5 h-3.5 mr-1" />
                                <span>Save & Upsert Lot</span>
                              </button>
                              <button
                                onClick={() => setEditingItemId(null)}
                                className="bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded text-xs font-semibold"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Review Action Buttons */}
                        {isPending && !isEditing && (
                          <div className="flex items-center space-x-2 pt-1">
                            <button
                              onClick={() => resolveMutation.mutate({ reviewId: item.id, action: "ACCEPT" })}
                              className="bg-teal-700 hover:bg-teal-800 text-white font-bold px-3 py-1.5 rounded text-xs flex items-center space-x-1 shadow-2xs transition-colors"
                            >
                              <Check className="w-3.5 h-3.5 mr-1" />
                              <span>Accept Lot</span>
                            </button>

                            <button
                              onClick={() => handleStartEdit(item)}
                              className="bg-white hover:bg-slate-100 text-slate-800 font-bold px-3 py-1.5 rounded text-xs border border-slate-300 flex items-center space-x-1 transition-colors"
                            >
                              <Edit3 className="w-3.5 h-3.5 mr-1 text-slate-600" />
                              <span>Correct (Pick Drug)</span>
                            </button>

                            <button
                              onClick={() => resolveMutation.mutate({ reviewId: item.id, action: "REJECT" })}
                              className="bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold px-3 py-1.5 rounded text-xs border border-rose-200 flex items-center space-x-1 transition-colors"
                            >
                              <X className="w-3.5 h-3.5 mr-1 text-rose-600" />
                              <span>Reject</span>
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
