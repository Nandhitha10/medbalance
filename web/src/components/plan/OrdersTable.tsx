import React from "react";
import { TransferOrder, Drug, Facility } from "../../types";
import { Snowflake, ArrowRight, CheckCircle2, Clock, FileText } from "lucide-react";
import { formatNumber, formatCurrencyINR } from "../../lib/utils";

interface OrdersTableProps {
  orders: TransferOrder[];
  drugs: Drug[];
  facilities: Facility[];
  onApproveOrder: (orderId: string) => void;
}

export const OrdersTable: React.FC<OrdersTableProps> = ({
  orders,
  drugs,
  facilities,
  onApproveOrder,
}) => {
  const drugMap = new Map<string, Drug>();
  drugs.forEach((d) => drugMap.set(d.code, d));

  const facilityMap = new Map<string, Facility>();
  facilities.forEach((f) => facilityMap.set(f.id, f));

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
      <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
        <div>
          <h3 className="font-bold text-slate-900 text-sm">
            Drug Transfer Advice (DTA) Vouchers ({orders.length})
          </h3>
          <p className="text-xs text-slate-500 font-medium">
            Modelled on Ni-kshay Aushadhi DTA voucher standards with HMAC-SHA256 custody tokens
          </p>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-teal-50 text-teal-800 border border-teal-200">
          Auditable Transfer Orders
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200">
              <th className="py-3 px-4">DTA Voucher No</th>
              <th className="py-3 px-3">Medicine & Batch</th>
              <th className="py-3 px-3">Transfer Route (Src &rarr; Dst)</th>
              <th className="py-3 px-3 text-right">Transfer Qty</th>
              <th className="py-3 px-3 text-right">Usable Qty</th>
              <th className="py-3 px-3">Temp Condition</th>
              <th className="py-3 px-3 text-center">Status</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {orders.map((order) => {
              const drug = drugMap.get(order.drug_code);
              const src = facilityMap.get(order.source_facility_id);
              const dst = facilityMap.get(order.destination_facility_id);
              const isApproved = order.status === "APPROVED";

              return (
                <tr key={order.id} className="hover:bg-slate-50 transition-colors">
                  {/* DTA Voucher */}
                  <td className="py-3 px-4 font-mono font-bold text-slate-900">
                    <div className="flex items-center space-x-1.5">
                      <FileText className="w-3.5 h-3.5 text-teal-600 shrink-0" />
                      <span>{order.id}</span>
                    </div>
                  </td>

                  {/* Drug & Batch */}
                  <td className="py-3 px-3">
                    <span className="font-bold text-slate-900 block text-sm">
                      {order.drug_code}
                    </span>
                    <div className="flex items-center space-x-2 text-[11px] text-slate-500">
                      <span>{drug?.name || order.drug_code}</span>
                      <span className="font-mono bg-slate-100 px-1 py-0.2 rounded border border-slate-200 text-slate-600">
                        {order.batch_no}
                      </span>
                    </div>
                  </td>

                  {/* Route */}
                  <td className="py-3 px-3">
                    <div className="flex items-center space-x-1.5 font-semibold text-slate-800 text-xs">
                      <span>{src?.name || order.source_facility_id}</span>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="text-teal-700 font-bold">
                        {dst?.name || order.destination_facility_id}
                      </span>
                    </div>
                  </td>

                  {/* Qty */}
                  <td className="py-3 px-3 text-right font-black text-slate-900 text-sm">
                    {formatNumber(order.quantity)} <span className="text-[10px] text-slate-500 font-normal">units</span>
                  </td>

                  {/* Usable Qty */}
                  <td className="py-3 px-3 text-right font-bold text-teal-700 text-sm">
                    {formatNumber(order.usable_quantity)} <span className="text-[10px] text-teal-600 font-normal">usable</span>
                  </td>

                  {/* Temp Condition */}
                  <td className="py-3 px-3">
                    {order.temperature_controlled ? (
                      <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-50 text-cyan-800 border border-cyan-200">
                        <Snowflake className="w-3 h-3 text-cyan-600" />
                        <span>Cold Chain (2–8 °C)</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                        Ambient Transport
                      </span>
                    )}
                  </td>

                  {/* Status */}
                  <td className="py-3 px-3 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${
                        isApproved
                          ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                          : "bg-amber-100 text-amber-800 border border-amber-300"
                      }`}
                    >
                      {order.status}
                    </span>
                  </td>

                  {/* Action */}
                  <td className="py-3 px-4 text-right">
                    {isApproved ? (
                      <span className="inline-flex items-center space-x-1 text-emerald-600 font-bold text-xs">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Approved</span>
                      </span>
                    ) : (
                      <button
                        onClick={() => onApproveOrder(order.id)}
                        className="bg-teal-600 hover:bg-teal-700 text-white font-bold px-3 py-1 rounded-md text-xs shadow-2xs transition-colors"
                      >
                        Approve DTA
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
