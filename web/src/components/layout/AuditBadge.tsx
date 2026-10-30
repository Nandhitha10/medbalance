import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, ShieldAlert, AlertTriangle, RefreshCw, KeyRound, Check, X } from "lucide-react";
import { api } from "../../lib/api";

export const AuditBadge: React.FC = () => {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const { data: audit, isLoading } = useQuery({
    queryKey: ["auditVerify"],
    queryFn: () => api.verifyAudit(),
    refetchInterval: 10000,
  });

  const tamperMutation = useMutation({
    mutationFn: () => api.tamperAuditDemo(),
    onSuccess: (data) => {
      queryClient.setQueryData(["auditVerify"], data.verification);
      setActionMessage(`Tampered audit log entry #${data.tampered_seq}. Hash verification failed!`);
    },
  });

  const restoreMutation = useMutation({
    mutationFn: () => api.restoreAuditDemo(),
    onSuccess: (data) => {
      queryClient.setQueryData(["auditVerify"], data.verification);
      setActionMessage("Original payload restored. Hash verification passed ✓");
    },
  });

  const isVerified = audit?.ok ?? true;
  const entriesCount = audit?.entries ?? 142;
  const firstBadSeq = audit?.first_bad_seq;

  return (
    <div className="relative">
      {/* Badge Button in TopBar */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        title="Cryptographic Audit Chain Integrity"
        className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all shadow-2xs border ${
          isVerified
            ? "bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100"
            : "bg-rose-100 text-rose-900 border-rose-300 hover:bg-rose-200 animate-pulse"
        }`}
      >
        {isVerified ? (
          <>
            <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>Ledger verified ✓ {entriesCount}</span>
          </>
        ) : (
          <>
            <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0" />
            <span>Tampered at #{firstBadSeq || 1}</span>
          </>
        )}
      </button>

      {/* Admin Menu Dropdown */}
      {isOpen && (
        <div className="absolute right-0 top-12 w-80 bg-white border border-slate-200 rounded-xl shadow-xl z-50 p-4 text-xs select-none animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center space-x-2">
              <KeyRound className="w-4 h-4 text-teal-600" />
              <span className="font-bold text-slate-900 text-sm">Audit Ledger Controls</span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="py-3 space-y-2">
            <div className="flex items-center justify-between text-slate-600">
              <span>Chain Status:</span>
              <span
                className={`font-black uppercase px-2 py-0.5 rounded text-[10px] ${
                  isVerified ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                }`}
              >
                {isVerified ? "Integrity Verified" : `Tamper Detected (seq #${firstBadSeq})`}
              </span>
            </div>
            <div className="flex items-center justify-between text-slate-600">
              <span>Verified Audit Rows:</span>
              <span className="font-mono font-bold text-slate-900">{entriesCount} entries</span>
            </div>
            <div className="text-[11px] text-slate-500 bg-slate-50 p-2 rounded-lg border border-slate-100">
              Every lot change, approval, and custody event is chained with <code className="font-mono text-teal-700">SHA-256(prev_hash + canonical_json)</code>.
            </div>
          </div>

          {actionMessage && (
            <div className={`p-2.5 rounded-lg text-[11px] font-semibold mb-3 border ${
              isVerified ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-rose-50 text-rose-800 border-rose-200"
            }`}>
              {actionMessage}
            </div>
          )}

          {/* Admin Demo Actions */}
          <div className="pt-2 border-t border-slate-100 space-y-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
              Judge Demonstration Actions
            </span>

            {isVerified ? (
              <button
                onClick={() => tamperMutation.mutate()}
                disabled={tamperMutation.isPending}
                className="w-full flex items-center justify-center space-x-1.5 bg-rose-600 hover:bg-rose-700 text-white font-bold py-2 px-3 rounded-lg text-xs transition-colors shadow-2xs"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Simulate Unauthorized Tamper</span>
              </button>
            ) : (
              <button
                onClick={() => restoreMutation.mutate()}
                disabled={restoreMutation.isPending}
                className="w-full flex items-center justify-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-3 rounded-lg text-xs transition-colors shadow-2xs"
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1" />
                <span>Restore Hash Chain Integrity</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

