import React from "react";
import { Lot } from "../../types";
import { formatDate, calculateDaysRemaining, formatNumber } from "../../lib/utils";
import { AlertCircle, Clock, ShieldCheck } from "lucide-react";

interface FefoBarsProps {
  lots: Lot[];
  todayStr?: string;
}

export const FefoBars: React.FC<FefoBarsProps> = ({ lots, todayStr }) => {
  // Sort by expiry ascending (FEFO order)
  const sortedLots = [...lots].sort((a, b) => new Date(a.expiry).getTime() - new Date(b.expiry).getTime());

  if (sortedLots.length === 0) {
    return (
      <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-center text-xs text-slate-500">
        No active inventory lots found for this facility.
      </div>
    );
  }

  const maxDays = 90;

  return (
    <div className="space-y-3">
      {sortedLots.map((lot, idx) => {
        const daysLeft = calculateDaysRemaining(lot.expiry, todayStr);
        const percent = Math.min(100, Math.max(5, (daysLeft / maxDays) * 100));

        let statusColor = "bg-teal-500 border-teal-600";
        let statusBadge = "bg-teal-50 text-teal-800 border-teal-200";
        let icon = <ShieldCheck className="w-3.5 h-3.5 text-teal-600" />;

        if (daysLeft <= 21) {
          statusColor = "bg-rose-500 border-rose-600 animate-pulse";
          statusBadge = "bg-rose-50 text-rose-800 border-rose-200";
          icon = <AlertCircle className="w-3.5 h-3.5 text-rose-600" />;
        } else if (daysLeft <= 45) {
          statusColor = "bg-amber-500 border-amber-600";
          statusBadge = "bg-amber-50 text-amber-800 border-amber-200";
          icon = <Clock className="w-3.5 h-3.5 text-amber-600" />;
        }

        return (
          <div
            key={lot.id || lot.batch_no || idx}
            className="p-3 bg-white border border-slate-200 rounded-lg shadow-2xs hover:border-slate-300 transition-all text-xs"
          >
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-900 text-sm">{lot.drug_code}</span>
                <span className="font-mono text-[11px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                  {lot.batch_no}
                </span>
                <span className="text-slate-400 font-semibold text-[10px]">#FEFO-{idx + 1}</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-900 text-sm">
                  {formatNumber(lot.quantity)} units
                </span>
                <span className={`flex items-center space-x-1 px-2 py-0.5 rounded-full border text-[11px] font-bold ${statusBadge}`}>
                  {icon}
                  <span>{daysLeft} days left</span>
                </span>
              </div>
            </div>

            {/* FEFO Timeline Bar */}
            <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden border border-slate-200 relative my-1.5">
              <div
                className={`h-full rounded-full transition-all duration-500 border-r ${statusColor}`}
                style={{ width: `${percent}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-500 mt-1">
              <span>Expiry Date: <strong className="text-slate-800">{formatDate(lot.expiry)}</strong></span>
              <span className="italic">
                {daysLeft <= 21 ? "Priority Redistribution Eligible" : "Normal Shelf Life"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
