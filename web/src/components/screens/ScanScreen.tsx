import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  QrCode,
  Truck,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Snowflake,
  ShieldCheck,
  ArrowRight,
  Package,
  Thermometer,
  UserCheck,
  MapPin,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { api } from "../../lib/api";
import { TransferOrder, PlanRun, Facility, Drug } from "../../types";
import { formatNumber, formatDateTime } from "../../lib/utils";

interface ScanScreenProps {
  initialToken?: string;
  onNavigateHome?: () => void;
}

export const ScanScreen: React.FC<ScanScreenProps> = ({ initialToken, onNavigateHome }) => {
  const queryClient = useQueryClient();

  // Extract token from prop, query parameter, or pathname
  const getDetectedToken = (): string => {
    if (initialToken) return initialToken;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const queryToken = params.get("token");
      if (queryToken) return queryToken;

      const pathParts = window.location.pathname.split("/");
      const scanIdx = pathParts.indexOf("scan");
      if (scanIdx !== -1 && pathParts[scanIdx + 1]) {
        return pathParts[scanIdx + 1];
      }
    }
    return "";
  };

  const [tokenInput, setTokenInput] = useState<string>(getDetectedToken());
  const [activeToken, setActiveToken] = useState<string>(getDetectedToken());

  // Input states for custody scan actions
  const [actorName, setActorName] = useState<string>("Ramesh (Dispatcher / Pharmacist)");
  const [scanLocation, setScanLocation] = useState<string>("Central Medical Store Dock");
  const [scannedQty, setScannedQty] = useState<number>(0);
  const [temperatureC, setTemperatureC] = useState<number>(4.5);
  const [scanNotes, setScanNotes] = useState<string>("");
  const [lastDeviation, setLastDeviation] = useState<any>(null);
  const [scanSuccessMessage, setScanSuccessMessage] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  // Fetch current plan to find orders and tokens
  const { data: plan, isLoading: planLoading } = useQuery<PlanRun>({
    queryKey: ["plan"],
    queryFn: () => api.getLatestPlan(),
  });

  const { data: facilities = [] } = useQuery<Facility[]>({
    queryKey: ["facilities"],
    queryFn: () => api.getFacilities(),
  });

  const { data: drugs = [] } = useQuery<Drug[]>({
    queryKey: ["drugs"],
    queryFn: () => api.getDrugs(),
  });

  const facilityMap = new Map<string, Facility>();
  facilities.forEach((f) => facilityMap.set(f.id, f));

  const drugMap = new Map<string, Drug>();
  drugs.forEach((d) => drugMap.set(d.code, d));

  // Find order associated with the active token or default to first order
  const orders = plan?.orders || [];
  const matchedOrder = orders.find((o) => {
    if (!activeToken) return false;
    return o.qr_token === activeToken || o.id === activeToken;
  }) || (activeToken ? null : orders[0] || null);

  // Auto-initialize token and quantity when matched order is available
  useEffect(() => {
    if (matchedOrder) {
      if (!activeToken && matchedOrder.qr_token) {
        setActiveToken(matchedOrder.qr_token);
        setTokenInput(matchedOrder.qr_token);
      }
      setScannedQty(matchedOrder.quantity);
      if (matchedOrder.status === "APPROVED") {
        setActorName("Ramesh Kumar (Dispatcher)");
        setScanLocation(`${matchedOrder.source_facility_id} Medical Stores`);
      } else if (matchedOrder.status === "IN_TRANSIT") {
        setActorName("Sister Sunitha (Receiving Pharmacist)");
        setScanLocation(`${matchedOrder.destination_facility_id} Inward Receiving Bay`);
      } else if (matchedOrder.status === "DELIVERED") {
        setActorName("Staff Nurse Deepa (Pediatric Ward)");
        setScanLocation(`${matchedOrder.destination_facility_id} Emergency Ward`);
      }
    }
  }, [matchedOrder?.id, matchedOrder?.status]);

  // Fetch custody trail for the matched order
  const { data: custodyTrail = [], refetch: refetchCustody } = useQuery({
    queryKey: ["custody", matchedOrder?.id],
    queryFn: () => (matchedOrder ? api.getCustodyTrail(matchedOrder.id) : Promise.resolve([])),
    enabled: Boolean(matchedOrder?.id),
    refetchInterval: 3000,
  });

  // Scan mutation
  const scanMutation = useMutation({
    mutationFn: (payload: {
      token: string;
      event: string;
      qty: number;
      actor: string;
      location?: string;
      temperature_c?: number;
      order_id?: string;
      notes?: string;
    }) => api.recordCustodyScan(payload),
    onSuccess: (data) => {
      setScanError(null);
      if (data.deviations && Object.keys(data.deviations).length > 0) {
        setLastDeviation(data.deviations);
      } else {
        setLastDeviation(null);
      }
      setScanSuccessMessage(
        `Consignment scan recorded! Status updated to ${data.order_status || "PROCESSED"}.`
      );
      queryClient.invalidateQueries({ queryKey: ["plan"] });
      queryClient.invalidateQueries({ queryKey: ["custody", matchedOrder?.id] });
      queryClient.invalidateQueries({ queryKey: ["auditVerify"] });
      refetchCustody();
    },
    onError: (err: any) => {
      setScanSuccessMessage(null);
      setScanError(err.message || "Failed to record scan event");
    },
  });

  const handleScanAction = (eventName: "dispatch" | "receive" | "consume") => {
    if (!matchedOrder) {
      setScanError("No valid consignment selected");
      return;
    }
    const token = activeToken || matchedOrder.qr_token || matchedOrder.id;
    setScanError(null);
    setScanSuccessMessage(null);

    scanMutation.mutate({
      token,
      event: eventName,
      qty: scannedQty || matchedOrder.quantity,
      actor: actorName,
      location: scanLocation,
      temperature_c: matchedOrder.temperature_controlled ? temperatureC : undefined,
      order_id: matchedOrder.id,
      notes: scanNotes || undefined,
    });
  };

  const drug = matchedOrder ? drugMap.get(matchedOrder.drug_code) : null;
  const srcFac = matchedOrder ? facilityMap.get(matchedOrder.source_facility_id) : null;
  const dstFac = matchedOrder ? facilityMap.get(matchedOrder.destination_facility_id) : null;

  const currentStatus = matchedOrder?.status || "PENDING";
  const isColdChain = Boolean(matchedOrder?.temperature_controlled);
  const isTempExcursion = isColdChain && (temperatureC < 2.0 || temperatureC > 8.0);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col justify-between select-none">
      {/* Mobile-First Header */}
      <header className="p-4 bg-slate-800 border-b border-slate-700 flex items-center justify-between sticky top-0 z-20 shadow-md">
        <div className="flex items-center space-x-2">
          <div className="w-9 h-9 rounded-xl bg-teal-500 text-slate-900 flex items-center justify-center font-black shadow-sm">
            <QrCode className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-black tracking-tight text-white flex items-center space-x-1.5">
              <span>Custody QR Scanner</span>
              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-teal-900/80 text-teal-300 border border-teal-700">
                LAN Ready
              </span>
            </h1>
            <p className="text-[11px] text-slate-400 font-medium">Chain-of-Custody Mobile Verification</p>
          </div>
        </div>

        {onNavigateHome && (
          <button
            onClick={onNavigateHome}
            className="text-xs font-bold text-teal-400 hover:text-teal-300 bg-slate-700/80 px-3 py-1.5 rounded-lg border border-slate-600 transition-colors"
          >
            Console
          </button>
        )}
      </header>

      {/* Main Container */}
      <main className="max-w-md w-full mx-auto p-4 space-y-4 flex-1 overflow-y-auto">
        {/* Token Picker / Switcher for Demo Convenience */}
        <div className="bg-slate-800/90 border border-slate-700 rounded-2xl p-3.5 shadow-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Active Consignment Token
            </span>
            <span className="text-[10px] font-mono text-teal-400">HMAC-SHA256</span>
          </div>

          <div className="flex space-x-2">
            <input
              type="text"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Paste or scan 24-char QR token..."
              className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-teal-200 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            <button
              onClick={() => setActiveToken(tokenInput)}
              className="px-3.5 py-2 bg-teal-600 hover:bg-teal-500 active:scale-95 text-white font-bold text-xs rounded-xl transition-all shadow-xs"
            >
              Load
            </button>
          </div>

          {/* Quick Select Buttons from Plan */}
          {orders.length > 0 && (
            <div className="pt-1 overflow-x-auto no-scrollbar whitespace-nowrap space-x-1.5">
              <span className="text-[10px] font-bold text-slate-500 mr-1">Quick Select:</span>
              {orders.slice(0, 5).map((o) => (
                <button
                  key={o.id}
                  onClick={() => {
                    const tk = o.qr_token || o.id;
                    setTokenInput(tk);
                    setActiveToken(tk);
                  }}
                  className={`inline-block px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold border transition-colors ${
                    (o.qr_token && activeToken === o.qr_token) || activeToken === o.id
                      ? "bg-teal-700 text-white border-teal-500"
                      : "bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500"
                  }`}
                >
                  {o.id} ({o.status})
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Consignment Order Summary Card */}
        {matchedOrder ? (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-4 shadow-md space-y-4">
            {/* Header with DTA and Status Badge */}
            <div className="flex items-start justify-between pb-3 border-b border-slate-700">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                  Official Transfer Advice
                </span>
                <span className="text-base font-black font-mono text-white tracking-tight">
                  {matchedOrder.id}
                </span>
              </div>

              <span
                className={`inline-flex items-center space-x-1 px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider ${
                  currentStatus === "APPROVED"
                    ? "bg-amber-900/60 text-amber-300 border border-amber-600"
                    : currentStatus === "IN_TRANSIT"
                    ? "bg-sky-900/60 text-sky-300 border border-sky-600 animate-pulse"
                    : currentStatus === "DELIVERED"
                    ? "bg-purple-900/60 text-purple-300 border border-purple-600"
                    : "bg-emerald-900/60 text-emerald-300 border border-emerald-600"
                }`}
              >
                {currentStatus === "APPROVED" && <Clock className="w-3.5 h-3.5 mr-1" />}
                {currentStatus === "IN_TRANSIT" && <Truck className="w-3.5 h-3.5 mr-1" />}
                {currentStatus === "DELIVERED" && <Package className="w-3.5 h-3.5 mr-1" />}
                {currentStatus === "COMPLETED" && <CheckCircle2 className="w-3.5 h-3.5 mr-1" />}
                <span>{currentStatus}</span>
              </span>
            </div>

            {/* Medicine, Lot, and Physical Requirements */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-black text-white">
                    {drug?.name || matchedOrder.drug_code}
                  </h3>
                  <div className="flex items-center space-x-2 text-xs text-slate-400 mt-0.5">
                    <span className="font-mono bg-slate-900 px-1.5 py-0.5 rounded border border-slate-700 text-teal-300">
                      Lot: {matchedOrder.batch_no}
                    </span>
                    <span>•</span>
                    <span>Code: {matchedOrder.drug_code}</span>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-xl font-black text-white">
                    {formatNumber(matchedOrder.quantity)}{" "}
                    <span className="text-xs text-slate-400 font-normal">units</span>
                  </div>
                  <span className="text-[10px] text-emerald-400 font-bold bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800">
                    F4 Usable: {formatNumber(matchedOrder.usable_quantity || matchedOrder.quantity)}
                  </span>
                </div>
              </div>

              {/* Transit Facility Route */}
              <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-700/80 flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2">
                  <div className="w-7 h-7 rounded-lg bg-teal-900/80 text-teal-300 font-bold flex items-center justify-center text-[11px] border border-teal-700">
                    {matchedOrder.source_facility_id}
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Origin Dispatch</span>
                    <span className="font-bold text-slate-200">
                      {srcFac?.name || matchedOrder.source_facility_id}
                    </span>
                  </div>
                </div>

                <ArrowRight className="w-4 h-4 text-slate-500 shrink-0 mx-2" />

                <div className="flex items-center space-x-2 text-right">
                  <div>
                    <span className="text-[10px] text-slate-400 block">Destination Bay</span>
                    <span className="font-bold text-slate-200">
                      {dstFac?.name || matchedOrder.destination_facility_id}
                    </span>
                  </div>
                  <div className="w-7 h-7 rounded-lg bg-purple-900/80 text-purple-300 font-bold flex items-center justify-center text-[11px] border border-purple-700">
                    {matchedOrder.destination_facility_id}
                  </div>
                </div>
              </div>

              {/* Cold Chain Badge */}
              {isColdChain && (
                <div className="p-2.5 bg-sky-950/60 border border-sky-800 rounded-xl flex items-center justify-between text-xs text-sky-200">
                  <div className="flex items-center space-x-2">
                    <Snowflake className="w-4 h-4 text-sky-400 shrink-0" />
                    <span>Cold Chain Consignment (2.0°C – 8.0°C Required)</span>
                  </div>
                  <span className="font-mono font-bold bg-sky-900/80 px-2 py-0.5 rounded text-[11px]">
                    Cold Van CV-02
                  </span>
                </div>
              )}
            </div>

            {/* Notification Alerts */}
            {scanSuccessMessage && (
              <div className="p-3 bg-emerald-950/80 border border-emerald-700 text-emerald-200 rounded-xl text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{scanSuccessMessage}</span>
              </div>
            )}

            {scanError && (
              <div className="p-3 bg-rose-950/80 border border-rose-700 text-rose-200 rounded-xl text-xs flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{scanError}</span>
              </div>
            )}

            {/* Deviation Alert with GenAI Summary */}
            {lastDeviation && (
              <div className="p-3.5 bg-rose-950/90 border border-rose-600 rounded-xl text-xs text-rose-200 space-y-2 animate-in fade-in">
                <div className="flex items-center space-x-2 font-bold text-rose-300">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>Physical Consignment Deviation Detected!</span>
                </div>

                {lastDeviation.qty_mismatch && (
                  <div className="text-[11px] bg-rose-900/50 p-2 rounded border border-rose-800">
                    <strong>Quantity Mismatch:</strong> Expected {lastDeviation.qty_mismatch.dispatched}{" "}
                    units, received {lastDeviation.qty_mismatch.received} units (Discrepancy:{" "}
                    {lastDeviation.qty_mismatch.diff}).
                  </div>
                )}

                {lastDeviation.temperature_excursion && (
                  <div className="text-[11px] bg-rose-900/50 p-2 rounded border border-rose-800">
                    <strong>Critical Temperature Excursion:</strong> Recorded{" "}
                    {lastDeviation.temperature_excursion.recorded_c}°C. Batch quarantined automatically.
                  </div>
                )}

                {lastDeviation.summary && (
                  <div className="text-[11px] italic text-rose-100 font-serif border-t border-rose-800 pt-1.5">
                    "{lastDeviation.summary}"
                  </div>
                )}
              </div>
            )}

            {/* Scan Inputs (Touch-optimized >= 48px height) */}
            <div className="pt-2 border-t border-slate-700 space-y-3">
              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-300 uppercase flex items-center space-x-1">
                  <UserCheck className="w-3.5 h-3.5 text-teal-400 mr-1" />
                  <span>Scanning Staff / Operator</span>
                </label>
                <input
                  type="text"
                  value={actorName}
                  onChange={(e) => setActorName(e.target.value)}
                  className="w-full min-h-[48px] bg-slate-900 border border-slate-700 rounded-xl px-3.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-300 uppercase flex items-center space-x-1">
                  <MapPin className="w-3.5 h-3.5 text-teal-400 mr-1" />
                  <span>Location Bay</span>
                </label>
                <input
                  type="text"
                  value={scanLocation}
                  onChange={(e) => setScanLocation(e.target.value)}
                  className="w-full min-h-[48px] bg-slate-900 border border-slate-700 rounded-xl px-3.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>

              {/* If receiving, show quantity and temperature input */}
              {currentStatus === "IN_TRANSIT" && (
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="space-y-1">
                    <label className="text-[11px] font-bold text-slate-300 uppercase">
                      Physical Received Qty
                    </label>
                    <input
                      type="number"
                      value={scannedQty}
                      onChange={(e) => setScannedQty(parseInt(e.target.value) || 0)}
                      className="w-full min-h-[48px] bg-slate-900 border border-slate-700 rounded-xl px-3.5 text-base font-black text-teal-300 focus:outline-none focus:ring-2 focus:ring-teal-500 text-center"
                    />
                    <span className="text-[10px] text-slate-500 block text-center">
                      Change to test shortage deviation
                    </span>
                  </div>

                  {isColdChain && (
                    <div className="space-y-1">
                      <label className="text-[11px] font-bold text-slate-300 uppercase flex items-center justify-between">
                        <span>Logger Temp (°C)</span>
                        <Thermometer className="w-3 h-3 text-sky-400" />
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={temperatureC}
                        onChange={(e) => setTemperatureC(parseFloat(e.target.value) || 0)}
                        className={`w-full min-h-[48px] bg-slate-900 border rounded-xl px-3.5 text-base font-black text-center focus:outline-none focus:ring-2 ${
                          isTempExcursion
                            ? "border-rose-500 text-rose-300 focus:ring-rose-500"
                            : "border-slate-700 text-sky-300 focus:ring-teal-500"
                        }`}
                      />
                      <span className="text-[10px] text-slate-500 block text-center">
                        Safe: 2.0°C – 8.0°C
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Critical Temperature Excursion Warning Banner if out of range */}
              {currentStatus === "IN_TRANSIT" && isColdChain && isTempExcursion && (
                <div className="p-2.5 bg-rose-950/80 border border-rose-600 rounded-xl text-[11px] text-rose-200 flex items-center space-x-2">
                  <AlertTriangle className="w-4 h-4 text-amber-300 shrink-0 animate-bounce" />
                  <span>
                    Warning: <strong>{temperatureC.toFixed(1)}°C</strong> exceeds cold-chain limit.
                    Receiving will auto-quarantine this lot!
                  </span>
                </div>
              )}
            </div>

            {/* Big Action Buttons (Touch Targets >= 48px) */}
            <div className="pt-2">
              {currentStatus === "APPROVED" && (
                <button
                  disabled={scanMutation.isPending}
                  onClick={() => handleScanAction("dispatch")}
                  className="w-full min-h-[52px] bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white text-base font-black rounded-2xl shadow-lg transition-all flex items-center justify-center space-x-2"
                >
                  <Truck className="w-5 h-5" />
                  <span>
                    {scanMutation.isPending ? "Recording Dispatch..." : "DISPATCH CONSIGNMENT"}
                  </span>
                </button>
              )}

              {currentStatus === "IN_TRANSIT" && (
                <button
                  disabled={scanMutation.isPending}
                  onClick={() => handleScanAction("receive")}
                  className="w-full min-h-[52px] bg-sky-600 hover:bg-sky-500 active:scale-95 text-white text-base font-black rounded-2xl shadow-lg transition-all flex items-center justify-center space-x-2"
                >
                  <Package className="w-5 h-5" />
                  <span>
                    {scanMutation.isPending ? "Verifying Inbound..." : "RECEIVE CONSIGNMENT"}
                  </span>
                </button>
              )}

              {currentStatus === "DELIVERED" && (
                <button
                  disabled={scanMutation.isPending}
                  onClick={() => handleScanAction("consume")}
                  className="w-full min-h-[52px] bg-purple-600 hover:bg-purple-500 active:scale-95 text-white text-base font-black rounded-2xl shadow-lg transition-all flex items-center justify-center space-x-2"
                >
                  <CheckCircle2 className="w-5 h-5" />
                  <span>
                    {scanMutation.isPending ? "Logging Dispense..." : "MARK CONSUMED / ADMINISTERED"}
                  </span>
                </button>
              )}

              {currentStatus === "COMPLETED" && (
                <div className="w-full min-h-[52px] bg-emerald-950/60 border border-emerald-600 rounded-2xl flex items-center justify-center space-x-2 text-emerald-300 font-black text-sm">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <span>CONSIGNMENT FULLY CONSUMED & LOGGED</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="p-8 text-center bg-slate-800 border border-slate-700 rounded-2xl text-slate-400 text-xs">
            No order found for token "{activeToken}". Please enter or select a valid consignment token.
          </div>
        )}

        {/* Live Custody Trail Timeline */}
        {matchedOrder && custodyTrail.length > 0 && (
          <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-700">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                <ShieldCheck className="w-4 h-4 text-teal-400 mr-1" />
                <span>Custody Event Timeline ({custodyTrail.length})</span>
              </span>
              <span className="text-[10px] text-slate-500 font-mono">SHA-256 Ledger</span>
            </div>

            <div className="space-y-2">
              {custodyTrail.map((ev: any, idx: number) => (
                <div
                  key={ev.id || idx}
                  className="p-2.5 bg-slate-900 rounded-xl border border-slate-800 text-xs flex items-center justify-between"
                >
                  <div className="flex items-center space-x-2.5">
                    <div
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                        ev.event_type === "DISPATCH"
                          ? "bg-teal-900 text-teal-300"
                          : ev.event_type === "RECEIVE"
                          ? "bg-sky-900 text-sky-300"
                          : "bg-purple-900 text-purple-300"
                      }`}
                    >
                      {idx + 1}
                    </div>
                    <div>
                      <span className="font-bold text-white block">{ev.event_type}</span>
                      <span className="text-[10px] text-slate-400">
                        {ev.actor} • {ev.location || "Facility"}
                      </span>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="text-[10px] font-mono text-slate-400 block">
                      {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : "--"}
                    </span>
                    {ev.temperature_c !== null && ev.temperature_c !== undefined && (
                      <span className="text-[10px] font-bold text-sky-400 font-mono">
                        {ev.temperature_c}°C
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Mobile Footer */}
      <footer className="p-3 bg-slate-800 border-t border-slate-700 text-center text-[11px] text-slate-500">
        MedBalance-Q District Cold Chain & Physical Custody Engine • Auto-Scan Enabled
      </footer>
    </div>
  );
};
