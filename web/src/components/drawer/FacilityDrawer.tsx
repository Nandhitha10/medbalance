import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  Snowflake,
  ShieldCheck,
  AlertTriangle,
  Package,
  Layers,
  Clock,
  TrendingDown,
} from "lucide-react";
import { Facility, Drug, Position, Lot } from "../../types";
import { api } from "../../lib/api";
import { FefoBars } from "./FefoBars";
import { formatNumber } from "../../lib/utils";

interface FacilityDrawerProps {
  facility: Facility | null;
  onClose: () => void;
  todayStr?: string;
}

export const FacilityDrawer: React.FC<FacilityDrawerProps> = ({
  facility,
  onClose,
  todayStr,
}) => {
  const [activeTab, setActiveTab] = useState<"positions" | "fefo">("positions");

  const facilityId = facility?.id;

  const { data: positions = [] } = useQuery<Position[]>({
    queryKey: ["positions", facilityId],
    queryFn: () => api.getPositions(facilityId),
    enabled: !!facilityId,
  });

  const { data: lots = [] } = useQuery<Lot[]>({
    queryKey: ["lots", facilityId],
    queryFn: () => api.getLots(facilityId),
    enabled: !!facilityId,
  });

  const { data: drugs = [] } = useQuery<Drug[]>({
    queryKey: ["drugs"],
    queryFn: () => api.getDrugs(),
  });

  if (!facility) return null;

  const drugMap = new Map<string, Drug>();
  drugs.forEach((d) => drugMap.set(d.code, d));

  const totalOnHand = positions.reduce((acc, p) => acc + p.stock_on_hand, 0);
  const totalEffective = positions.reduce((acc, p) => acc + p.effective_stock, 0);
  const totalAtRisk = positions.reduce((acc, p) => acc + p.at_risk_stock, 0);
  const totalShortage = positions.reduce((acc, p) => acc + p.shortage, 0);

  const getCategoryBadge = (category?: string) => {
    switch (category) {
      case "V":
        return <span className="bg-rose-100 text-rose-800 border border-rose-300 font-bold px-1.5 py-0.5 rounded text-[10px]">Vital</span>;
      case "E":
        return <span className="bg-amber-100 text-amber-800 border border-amber-300 font-bold px-1.5 py-0.5 rounded text-[10px]">Essential</span>;
      case "N":
        return <span className="bg-slate-100 text-slate-700 border border-slate-300 font-medium px-1.5 py-0.5 rounded text-[10px]">Non-ess</span>;
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-[540px] md:w-[620px] bg-white border-l border-slate-200 shadow-2xl z-40 flex flex-col transition-all duration-300 select-none animate-in slide-in-from-right">
      {/* Header */}
      <div className="p-6 bg-slate-900 text-white border-b border-slate-800 flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <span className="bg-teal-600 text-white text-xs font-bold px-2 py-0.5 rounded">
              {facility.id}
            </span>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
              Level: {facility.facility_type}
            </span>
            {facility.cold_storage_available ? (
              <span className="flex items-center space-x-1 text-[11px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800 px-2 py-0.5 rounded-full">
                <Snowflake className="w-3 h-3 text-cyan-400" />
                <span>Cold Storage OK</span>
              </span>
            ) : (
              <span className="text-[11px] font-medium bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full">
                No Cold Chain
              </span>
            )}
          </div>
          <h2 className="text-xl font-bold tracking-tight text-white">{facility.name}</h2>
          <p className="text-xs text-slate-400 font-medium">
            Min Reserve Policy: {facility.min_reserve_days} days · Lat: {facility.latitude}, Lng: {facility.longitude}
          </p>
        </div>

        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-4 gap-2.5 p-4 bg-slate-50 border-b border-slate-200 text-center">
        <div className="p-2.5 bg-white border border-slate-200 rounded-lg shadow-2xs">
          <span className="text-[10px] uppercase font-bold text-slate-500 block">On Hand</span>
          <span className="text-base font-bold text-slate-900">{formatNumber(totalOnHand)}</span>
        </div>
        <div className="p-2.5 bg-white border border-slate-200 rounded-lg shadow-2xs">
          <span className="text-[10px] uppercase font-bold text-teal-700 block">Effective</span>
          <span className="text-base font-bold text-teal-800">{formatNumber(totalEffective)}</span>
        </div>
        <div className="p-2.5 bg-white border border-slate-200 rounded-lg shadow-2xs">
          <span className="text-[10px] uppercase font-bold text-amber-700 block">At-Risk</span>
          <span className="text-base font-bold text-amber-800">{formatNumber(totalAtRisk)}</span>
        </div>
        <div className="p-2.5 bg-white border border-slate-200 rounded-lg shadow-2xs">
          <span className="text-[10px] uppercase font-bold text-rose-700 block">Shortage</span>
          <span className="text-base font-bold text-rose-800">{formatNumber(totalShortage)}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 px-6 pt-3 space-x-6 bg-white">
        <button
          onClick={() => setActiveTab("positions")}
          className={`pb-3 text-xs font-bold transition-all border-b-2 flex items-center space-x-2 ${
            activeTab === "positions"
              ? "border-teal-600 text-teal-700"
              : "border-transparent text-slate-500 hover:text-slate-900"
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Positions Read-Model ({positions.length})</span>
        </button>
        <button
          onClick={() => setActiveTab("fefo")}
          className={`pb-3 text-xs font-bold transition-all border-b-2 flex items-center space-x-2 ${
            activeTab === "fefo"
              ? "border-teal-600 text-teal-700"
              : "border-transparent text-slate-500 hover:text-slate-900"
          }`}
        >
          <Clock className="w-4 h-4" />
          <span>FEFO Lot Expiry Bars ({lots.length})</span>
        </button>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {activeTab === "positions" ? (
          <div className="space-y-3">
            <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-2xs">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200">
                    <th className="py-2.5 px-3">Drug</th>
                    <th className="py-2.5 px-2">VEN</th>
                    <th className="py-2.5 px-2 text-right">On Hand</th>
                    <th className="py-2.5 px-2 text-right">Effective</th>
                    <th className="py-2.5 px-2 text-right">At-Risk</th>
                    <th className="py-2.5 px-2 text-right">Reserve</th>
                    <th className="py-2.5 px-2 text-right">Shortage</th>
                    <th className="py-2.5 px-3 text-right">Daily Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {positions.map((pos) => {
                    const drug = drugMap.get(pos.drug_code);
                    const hasShortage = pos.shortage > 0;
                    const hasRisk = pos.at_risk_stock > 0;

                    return (
                      <tr
                        key={pos.drug_code}
                        className={`hover:bg-slate-50 transition-colors ${
                          hasShortage ? "bg-rose-50/40" : hasRisk ? "bg-amber-50/30" : ""
                        }`}
                      >
                        <td className="py-2.5 px-3">
                          <span className="font-bold text-slate-900 block">{pos.drug_code}</span>
                          <span className="text-[10px] text-slate-500 line-clamp-1">
                            {drug?.name || pos.drug_code}
                          </span>
                        </td>
                        <td className="py-2.5 px-2">{getCategoryBadge(drug?.category)}</td>
                        <td className="py-2.5 px-2 text-right font-medium text-slate-900">
                          {formatNumber(pos.stock_on_hand)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-bold text-teal-700">
                          {formatNumber(pos.effective_stock)}
                        </td>
                        <td className={`py-2.5 px-2 text-right font-bold ${hasRisk ? "text-amber-700" : "text-slate-400"}`}>
                          {formatNumber(pos.at_risk_stock)}
                        </td>
                        <td className="py-2.5 px-2 text-right text-slate-600 font-medium">
                          {formatNumber(pos.reserve)}
                        </td>
                        <td className={`py-2.5 px-2 text-right font-bold ${hasShortage ? "text-rose-700 font-black" : "text-slate-400"}`}>
                          {formatNumber(pos.shortage)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-slate-600">
                          {pos.daily_consumption_rate.toFixed(1)}/d
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-slate-500 italic">
              Effective stock & At-risk computed strictly under FEFO consumption at forecast daily rate.
            </p>
          </div>
        ) : (
          <FefoBars lots={lots} todayStr={todayStr} />
        )}
      </div>
    </div>
  );
};
