import React from "react";
import { TransferOrder, Drug, Facility } from "../../types";
import { Snowflake, ArrowRight, CheckCircle2, Clock, FileText, Check, ShieldCheck, MapPin } from "lucide-react";
import { formatNumber } from "../../lib/utils";

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

  // Group transfer orders by destination facility
  const ordersByDestination = orders.reduce<Record<string, TransferOrder[]>>((acc, order) => {
    const dst = order.destination_facility_id || "UNKNOWN";
    if (!acc[dst]) acc[dst] = [];
    acc[dst].push(order);
    return acc;
  }, {});

  const destinationIds = Object.keys(ordersByDestination);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-slate-900 text-base">
            Transfer Orders Grouped by Destination Facility ({orders.length} Orders across {destinationIds.length} Hubs)
          </h3>
          <p className="text-xs text-slate-500 font-medium">
            Sequential DTA voucher allocation with FEFO reserve protection and exact usable quantity capping
          </p>
        </div>

        <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-teal-50 text-teal-800 border border-teal-200 flex items-center space-x-1">
          <ShieldCheck className="w-3.5 h-3.5 text-teal-600 mr-1" />
          <span>F1–F6 Feasibility Enforced</span>
        </span>
      </div>

      {destinationIds.length === 0 ? (
        <div className="p-8 text-center bg-white border border-slate-200 rounded-xl text-xs text-slate-400">
          No active transfer orders generated. Run the optimizer to create redistribution orders.
        </div>
      ) : (
        destinationIds.map((dstId) => {
          const destFac = facilityMap.get(dstId);
          const destOrders = ordersByDestination[dstId];
          const totalUnits = destOrders.reduce((sum, o) => sum + o.quantity, 0);
          const coldUnits = destOrders
            .filter((o) => o.temperature_controlled)
            .reduce((sum, o) => sum + o.quantity, 0);
          const approvedCount = destOrders.filter((o) => o.status === "APPROVED").length;

          return (
            <div
              key={dstId}
              className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden"
            >
              {/* Destination Facility Group Header */}
              <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center space-x-3">
                  <div className="w-9 h-9 rounded-lg bg-teal-700 text-white font-bold flex items-center justify-center text-xs shadow-xs">
                    {dstId}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <h4 className="font-black text-slate-900 text-sm">
                        Destination: {destFac?.name || dstId}
                      </h4>
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                        {destFac?.facility_type || "Facility"}
                      </span>
                    </div>
                    <span className="text-xs text-slate-500 font-medium">
                      Receiving {formatNumber(totalUnits)} units • {destOrders.length} DTA Vouchers
                    </span>
                  </div>
                </div>

                <div className="flex items-center space-x-2 text-xs">
                  {coldUnits > 0 && (
                    <span className="text-[11px] font-bold text-sky-800 bg-sky-50 border border-sky-200 px-2.5 py-0.5 rounded flex items-center space-x-1">
                      <Snowflake className="w-3 h-3 text-sky-600 mr-1" />
                      <span>{formatNumber(coldUnits)} Cold Chain Units</span>
                    </span>
                  )}
                  <span
                    className={`text-[11px] font-bold px-2.5 py-0.5 rounded ${
                      approvedCount === destOrders.length
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {approvedCount}/{destOrders.length} Approved
                  </span>
                </div>
              </div>

              {/* Table of Orders in this destination */}
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-100/70 text-slate-700 font-bold border-b border-slate-200">
                      <th className="py-2.5 px-4">DTA Voucher No</th>
                      <th className="py-2.5 px-3">Medicine & Batch</th>
                      <th className="py-2.5 px-3">Dispatching Facility</th>
                      <th className="py-2.5 px-3 text-right">Transfer Qty</th>
                      <th className="py-2.5 px-3 text-right">Usable Qty (F4)</th>
                      <th className="py-2.5 px-3">Storage / Temp</th>
                      <th className="py-2.5 px-3 text-center">Status</th>
                      <th className="py-2.5 px-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {destOrders.map((order) => {
                      const drug = drugMap.get(order.drug_code);
                      const src = facilityMap.get(order.source_facility_id);
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
                            <span className="font-bold text-slate-900 block text-xs">
                              {order.drug_code}
                            </span>
                            <div className="flex items-center space-x-2 text-[11px] text-slate-500">
                              <span>{drug?.name || order.drug_code}</span>
                              <span className="font-mono bg-slate-100 px-1 py-0.2 rounded border border-slate-200 text-slate-600">
                                {order.batch_no}
                              </span>
                            </div>
                          </td>

                          {/* Source */}
                          <td className="py-3 px-3 font-medium text-slate-700">
                            <div className="flex items-center space-x-1">
                              <span className="font-bold text-slate-900">{order.source_facility_id}</span>
                              <span className="text-slate-400">({src?.name || "Facility"})</span>
                            </div>
                          </td>

                          {/* Qty */}
                          <td className="py-3 px-3 text-right font-black text-slate-900">
                            {formatNumber(order.quantity)} <span className="text-[10px] text-slate-400 font-normal">units</span>
                          </td>

                          {/* Usable Qty (F4) */}
                          <td className="py-3 px-3 text-right">
                            <span className="font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded text-[11px]">
                              {formatNumber(order.usable_quantity || order.quantity)} units
                            </span>
                          </td>

                          {/* Cold chain */}
                          <td className="py-3 px-3">
                            {order.temperature_controlled ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-sky-100 text-sky-800 border border-sky-300">
                                <Snowflake className="w-3 h-3 mr-1 text-sky-600" />
                                2–8 °C Cold Van
                              </span>
                            ) : (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                                Ambient
                              </span>
                            )}
                          </td>

                          {/* Status */}
                          <td className="py-3 px-3 text-center">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                                isApproved
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-amber-100 text-amber-800"
                              }`}
                            >
                              {isApproved ? (
                                <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
                              ) : (
                                <Clock className="w-3 h-3 mr-1 text-amber-600" />
                              )}
                              {order.status}
                            </span>
                          </td>

                          {/* Action */}
                          <td className="py-3 px-4 text-right">
                            {!isApproved ? (
                              <button
                                onClick={() => onApproveOrder(order.id)}
                                className="bg-teal-700 hover:bg-teal-800 active:scale-95 text-white font-bold px-3 py-1.5 rounded text-xs transition-colors shadow-2xs inline-flex items-center space-x-1"
                              >
                                <Check className="w-3 h-3 mr-1" />
                                <span>Approve</span>
                              </button>
                            ) : (
                              <span className="text-[11px] text-emerald-700 font-bold">
                                Ready for Dispatch
                              </span>
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
        })
      )}
    </div>
  );
};
