import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { ColdchainDevice } from "../../types";
import {
  ThermometerSnowflake,
  ShieldCheck,
  AlertTriangle,
  Truck,
  Battery,
  DoorClosed,
  DoorOpen,
  Wifi,
  Clock,
  Activity,
  Flame,
  CheckCircle2,
  RefreshCw,
  AlertOctagon,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceArea,
  ReferenceLine,
} from "recharts";

export const ColdchainScreen: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("DEV-CV-02");

  const { data: coldchainData, isLoading } = useQuery({
    queryKey: ["coldchain"],
    queryFn: () => api.getColdchainStatus(),
    refetchInterval: 3000,
  });

  const triggerFaultMutation = useMutation({
    mutationFn: (fault: string) => api.applyScenario(fault),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["coldchain"] });
    },
  });

  if (isLoading || !coldchainData) {
    return (
      <div className="p-8 text-center text-slate-500 font-medium">
        Loading cold chain IoT telemetry...
      </div>
    );
  }

  const devices: ColdchainDevice[] = coldchainData.devices || [];
  const activeExcursions = devices.filter((d) => d.status === "EXCURSION");

  const getStateBadge = (status: string) => {
    switch (status) {
      case "OK":
        return (
          <span className="bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center space-x-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mr-1" />
            <span>OK (Safe 2–8 °C)</span>
          </span>
        );
      case "WARNING":
        return (
          <span className="bg-amber-100 text-amber-800 border border-amber-300 text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center space-x-1">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 mr-1" />
            <span>WARNING</span>
          </span>
        );
      case "EXCURSION":
        return (
          <span className="bg-rose-600 text-white border border-rose-700 text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center space-x-1 animate-pulse shadow-xs">
            <Flame className="w-3.5 h-3.5 mr-1" />
            <span>EXCURSION</span>
          </span>
        );
      case "RECOVERED":
        return (
          <span className="bg-teal-100 text-teal-800 border border-teal-300 text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center space-x-1">
            <ShieldCheck className="w-3.5 h-3.5 text-teal-600 mr-1" />
            <span>RECOVERED</span>
          </span>
        );
      default:
        return (
          <span className="bg-slate-100 text-slate-700 border border-slate-300 text-xs font-bold px-2.5 py-0.5 rounded-full">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto select-none">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3 mb-1">
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">
              Cold Chain Telemetry & IoT Excursion Monitor
            </h1>
            <span className="bg-sky-100 text-sky-800 text-xs font-bold px-2.5 py-1 rounded-full border border-sky-300 flex items-center space-x-1">
              <ThermometerSnowflake className="w-3.5 h-3.5 text-sky-600 mr-1" />
              <span>Safe Standard: 2.0 °C to 8.0 °C</span>
            </span>
          </div>
          <p className="text-sm text-slate-500 font-medium">
            Real-time MQTT telemetry subscriber with automatic excursion state machine (OK &rarr; WARNING &rarr; EXCURSION &rarr; RECOVERED).
          </p>
        </div>

        {/* Quick Testing Actions */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => triggerFaultMutation.mutate("fridge_failure")}
            className="bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 font-bold px-3 py-2 rounded-xl text-xs transition-colors flex items-center space-x-1.5 shadow-2xs"
          >
            <Flame className="w-3.5 h-3.5 text-rose-600" />
            <span>Inject CV-02 Fridge Failure</span>
          </button>

          <button
            onClick={() => triggerFaultMutation.mutate("ilr_repaired")}
            className="bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold px-3 py-2 rounded-xl text-xs transition-colors flex items-center space-x-1.5 shadow-2xs"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>Repair H4 ILR</span>
          </button>
        </div>
      </div>

      {/* Network Health Summary Banner */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs space-y-1">
          <span className="text-[11px] font-bold uppercase text-slate-500">Monitored Fleet</span>
          <div className="text-2xl font-black text-slate-900">
            {coldchainData.monitored_vehicles_count || 2} Cold Vans
          </div>
          <span className="text-xs text-teal-700 font-semibold">Active GPS & Telemetry</span>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs space-y-1">
          <span className="text-[11px] font-bold uppercase text-slate-500">Facility ILRs</span>
          <div className="text-2xl font-black text-slate-900">
            {coldchainData.monitored_facilities_count || 5} Ice-Lined Fridges
          </div>
          <span className="text-xs text-slate-500 font-medium">H1, H2, H3, H4, W0</span>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs space-y-1">
          <span className="text-[11px] font-bold uppercase text-slate-500">Active Excursions</span>
          <div className="text-2xl font-black text-rose-600">
            {activeExcursions.length} Detected
          </div>
          <span className="text-xs text-rose-700 font-semibold">
            {activeExcursions.length > 0 ? "Route Holds Engaged" : "All Devices Nominal"}
          </span>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-xs space-y-1">
          <span className="text-[11px] font-bold uppercase text-slate-500">MQTT Broker Status</span>
          <div className="text-2xl font-black text-emerald-700 flex items-center space-x-1">
            <Wifi className="w-5 h-5 text-emerald-600" />
            <span>Connected</span>
          </div>
          <span className="text-xs text-slate-500 font-mono">district/coldchain/+/telemetry</span>
        </div>
      </div>

      {/* Device Cards Grid with Live Sparklines */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {devices.map((dev) => {
          const isExcursion = dev.status === "EXCURSION";
          const isSelected = selectedDeviceId === dev.device_id;
          const telemetryData = dev.telemetry || [
            { timestamp: "08:00", temperature_c: dev.latest_temp_c - 0.2 },
            { timestamp: "08:15", temperature_c: dev.latest_temp_c + 0.1 },
            { timestamp: "08:30", temperature_c: dev.latest_temp_c - 0.1 },
            { timestamp: "08:45", temperature_c: dev.latest_temp_c + 0.3 },
            { timestamp: "09:00", temperature_c: dev.latest_temp_c },
          ];

          return (
            <div
              key={dev.device_id}
              onClick={() => setSelectedDeviceId(dev.device_id)}
              className={`p-5 bg-white border rounded-2xl shadow-xs transition-all space-y-4 cursor-pointer ${
                isExcursion
                  ? "border-rose-400 ring-2 ring-rose-500/20 bg-rose-50/10"
                  : isSelected
                  ? "border-teal-500 ring-2 ring-teal-500/20"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              {/* Card Header */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center space-x-3">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm ${
                      dev.type === "vehicle"
                        ? "bg-cyan-100 text-cyan-800"
                        : "bg-teal-100 text-teal-800"
                    }`}
                  >
                    {dev.type === "vehicle" ? (
                      <Truck className="w-5 h-5 text-cyan-700" />
                    ) : (
                      <ThermometerSnowflake className="w-5 h-5 text-teal-700" />
                    )}
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-900 text-sm">
                      {dev.target_name || `${dev.assigned_to} Sensor`}
                    </h3>
                    <div className="flex items-center space-x-2 text-xs text-slate-500 font-mono">
                      <span>{dev.device_id}</span>
                      <span>•</span>
                      <span className="font-sans font-medium">Assigned: {dev.assigned_to}</span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col items-end space-y-1">
                  {getStateBadge(dev.status)}
                  <span className="text-[10px] text-slate-400 font-medium">
                    Updated {dev.last_ping ? dev.last_ping.split("T")[1]?.slice(0, 5) : "just now"}
                  </span>
                </div>
              </div>

              {/* Temperature Reading & Diagnostic Metrics */}
              <div className="grid grid-cols-4 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-100 text-xs">
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Current Temp
                  </span>
                  <span
                    className={`text-xl font-black ${
                      isExcursion ? "text-rose-600" : "text-slate-900"
                    }`}
                  >
                    {dev.latest_temp_c.toFixed(1)} °C
                  </span>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Safe Range
                  </span>
                  <span className="text-xs font-bold text-emerald-700 block pt-1">
                    2.0 – 8.0 °C
                  </span>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Battery Level
                  </span>
                  <span className="text-xs font-bold text-slate-800 flex items-center pt-1">
                    <Battery className="w-3.5 h-3.5 mr-1 text-slate-500" />
                    {dev.battery_percent}%
                  </span>
                </div>

                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Door Status
                  </span>
                  <span className="text-xs font-bold text-slate-800 flex items-center pt-1">
                    {dev.door_open ? (
                      <>
                        <DoorOpen className="w-3.5 h-3.5 mr-1 text-rose-500" />
                        <span className="text-rose-600">Open (&gt;2m)</span>
                      </>
                    ) : (
                      <>
                        <DoorClosed className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                        <span className="text-slate-700">Closed</span>
                      </>
                    )}
                  </span>
                </div>
              </div>

              {/* Sparkline Container with Shaded 2–8 °C Band */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span className="font-semibold text-slate-700">Temperature Telemetry Sparkline</span>
                  <span className="text-emerald-700 font-bold bg-emerald-50 px-2 py-0.2 rounded border border-emerald-200">
                    Shaded: 2.0 – 8.0 °C Safe Band
                  </span>
                </div>

                <div className="w-full h-32 bg-slate-950/5 rounded-xl border border-slate-100 p-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={telemetryData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id={`tempGrad-${dev.device_id}`} x1="0" y1="0" x2="0" y2="1">
                          <stop
                            offset="5%"
                            stopColor={isExcursion ? "#f43f5e" : "#0d9488"}
                            stopOpacity={0.4}
                          />
                          <stop
                            offset="95%"
                            stopColor={isExcursion ? "#f43f5e" : "#0d9488"}
                            stopOpacity={0.0}
                          />
                        </linearGradient>
                      </defs>

                      <XAxis dataKey="timestamp" tick={{ fontSize: 9, fill: "#94a3b8" }} />
                      <YAxis domain={[0, 14]} tick={{ fontSize: 9, fill: "#94a3b8" }} />

                      {/* Shaded 2-8 °C Safe Band */}
                      <ReferenceArea y1={2} y2={8} fill="#10b981" fillOpacity={0.12} />
                      <ReferenceLine y={8} stroke="#ef4444" strokeDasharray="3 3" opacity={0.6} />
                      <ReferenceLine y={2} stroke="#3b82f6" strokeDasharray="3 3" opacity={0.6} />

                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#0f172a",
                          borderColor: "#334155",
                          borderRadius: "6px",
                          color: "#f8fafc",
                          fontSize: "11px",
                        }}
                        formatter={(val: any) => [`${Number(val).toFixed(1)} °C`, "Temperature"]}
                      />

                      <Area
                        type="monotone"
                        dataKey="temperature_c"
                        stroke={isExcursion ? "#e11d48" : "#0d9488"}
                        strokeWidth={2.5}
                        fill={`url(#tempGrad-${dev.device_id})`}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
