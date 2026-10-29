import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import {
  FileSpreadsheet,
  AlertCircle,
  CheckCircle,
  Clock,
  Layers,
  Sparkles,
  Check,
  RotateCcw,
  CheckCircle2,
} from "lucide-react";

export const IngestionScreen: React.FC = () => {
  const { data: reviews = [] } = useQuery({
    queryKey: ["reviews"],
    queryFn: () => api.getReviews(),
  });

  const [resolvedIds, setResolvedIds] = useState<string[]>([]);

  const handleResolve = (id: string) => {
    setResolvedIds((prev) => [...prev, id]);
  };

  const channels = [
    {
      facility: "H1 SIM-DH Jayanagar",
      format: "FHIR R4 InventoryReport",
      status: "Automated Polling",
      confidence: "99.8%",
      badgeColor: "bg-teal-50 text-teal-800 border-teal-300",
      type: "FHIR JSON",
    },
    {
      facility: "H2 SIM-TGH Anekal",
      format: "Nightly CSV Export",
      status: "Auto-Ingested",
      confidence: "98.4%",
      badgeColor: "bg-teal-50 text-teal-800 border-teal-300",
      type: "CSV Stream",
    },
    {
      facility: "H3 SIM-CHC Yelahanka",
      format: "Kannada WhatsApp / Chat",
      status: "AI Grounded (RapidFuzz)",
      confidence: "94.2%",
      badgeColor: "bg-indigo-50 text-indigo-800 border-indigo-300",
      type: "Multilingual LLM",
    },
    {
      facility: "H4 SIM-PHC Sarjapura",
      format: "Messy Text / Handwritten",
      status: "Vision & OCR Extraction",
      confidence: "91.5%",
      badgeColor: "bg-amber-50 text-amber-800 border-amber-300",
      type: "LLM Extraction",
    },
  ];

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">
          Hospital Ingestion & Pharmacist Review Queue
        </h1>
        <p className="text-sm text-slate-500 font-medium">
          Heterogeneous multi-source ingestion (FHIR, CSV, Kannada WhatsApp, OCR) with deterministic grounding and safety verification
        </p>
      </div>

      {/* Hospital Channels Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {channels.map((ch) => (
          <div
            key={ch.facility}
            className="p-4 bg-white border border-slate-200 rounded-xl shadow-2xs space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${ch.badgeColor}`}>
                {ch.type}
              </span>
              <span className="text-[11px] font-bold text-teal-700">{ch.confidence} Match</span>
            </div>
            <h4 className="font-bold text-slate-900 text-sm leading-tight">{ch.facility}</h4>
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

      {/* Review Queue Container */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-amber-500" />
            <h3 className="font-bold text-slate-900 text-sm">Pharmacist Anomaly Review Queue</h3>
          </div>
          <span className="text-xs font-semibold px-2.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
            {reviews.filter((r: any) => !resolvedIds.includes(r.id)).length} Pending Pharmacist Review
          </span>
        </div>

        <div className="divide-y divide-slate-200">
          {reviews.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500">
              No pending anomaly review items. All hospital stock reports processed cleanly.
            </div>
          ) : (
            reviews.map((rev: any) => {
              const isResolved = resolvedIds.includes(rev.id);

              return (
                <div
                  key={rev.id}
                  className={`p-5 transition-colors flex flex-col lg:flex-row lg:items-center justify-between gap-4 text-xs ${
                    isResolved ? "bg-teal-50/40 opacity-70" : "hover:bg-slate-50"
                  }`}
                >
                  <div className="space-y-2 max-w-3xl">
                    <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                      <span className="bg-slate-900 text-white font-mono font-bold px-2 py-0.5 rounded text-[11px]">
                        {rev.id}
                      </span>
                      <span className="font-bold text-slate-800">
                        Facility: {rev.facility_code}
                      </span>
                      <span className="font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                        {rev.anomaly_type}
                      </span>
                      <span className="text-slate-500 font-medium">
                        Grounding Confidence: {(rev.confidence * 100).toFixed(0)}%
                      </span>
                      {isResolved && (
                        <span className="text-teal-700 font-bold bg-teal-100 border border-teal-300 px-2 py-0.5 rounded flex items-center">
                          <Check className="w-3 h-3 mr-1" /> Approved
                        </span>
                      )}
                    </div>

                    <div className="font-mono bg-slate-100 p-2.5 rounded-lg text-slate-800 border border-slate-200">
                      <span className="text-[10px] text-slate-400 uppercase font-semibold block mb-0.5">
                        Raw Ingest Text
                      </span>
                      "{rev.raw_text}"
                    </div>

                    {rev.suggested_patch && (
                      <div className="p-2.5 bg-teal-50/60 border border-teal-200 rounded-lg">
                        <span className="text-[10px] text-teal-800 uppercase font-bold block mb-1">
                          Suggested Grounded Lot Patch
                        </span>
                        <div className="grid grid-cols-4 gap-2 text-[11px] font-mono">
                          <div>
                            <span className="text-slate-500 block text-[9px]">Drug Code</span>
                            <span className="font-bold text-teal-900">{rev.suggested_patch.drug_code}</span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[9px]">Batch No</span>
                            <span className="font-bold text-teal-900">{rev.suggested_patch.batch_no}</span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[9px]">Parsed Expiry</span>
                            <span className="font-bold text-teal-900">{rev.suggested_patch.expiry}</span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[9px]">Quantity</span>
                            <span className="font-bold text-teal-900">{rev.suggested_patch.quantity} units</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 shrink-0">
                    {!isResolved ? (
                      <>
                        <button
                          onClick={() => handleResolve(rev.id)}
                          className="bg-teal-600 hover:bg-teal-700 text-white font-bold px-4 py-2 rounded-lg text-xs shadow-xs transition-colors flex items-center space-x-1"
                        >
                          <Check className="w-3.5 h-3.5 mr-1" />
                          <span>Accept & Upsert Lot</span>
                        </button>
                        <button
                          onClick={() => handleResolve(rev.id)}
                          className="bg-white hover:bg-slate-100 text-slate-700 font-semibold px-3 py-2 rounded-lg text-xs border border-slate-300 transition-colors"
                        >
                          Correct Manually
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setResolvedIds((prev) => prev.filter((id) => id !== rev.id))}
                        className="text-slate-500 hover:text-slate-800 text-xs flex items-center space-x-1 underline p-1"
                      >
                        <RotateCcw className="w-3 h-3 mr-1" />
                        <span>Undo Decision</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
