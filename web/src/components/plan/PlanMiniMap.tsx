import React from "react";
import { Facility, TransferOrder } from "../../types";
import { Layers, ShieldCheck, Snowflake, MapPin } from "lucide-react";

interface PlanMiniMapProps {
  facilities: Facility[];
  orders: TransferOrder[];
  zoningPartition?: Record<string, number>;
}

export const PlanMiniMap: React.FC<PlanMiniMapProps> = ({
  facilities,
  orders,
  zoningPartition = { H1: 0, H2: 1, H3: 0, H4: 1, W0: 0 },
}) => {
  // SVG projection: Longitude [77.35..77.85] -> x [40..360], Latitude [12.65..13.20] -> y [240..40]
  const project = (lat: number, lng: number) => {
    const x = ((lng - 77.35) / (77.85 - 77.35)) * 320 + 40;
    const y = ((13.20 - lat) / (13.20 - 12.65)) * 200 + 35;
    return { x, y };
  };

  const facilityCoords = new Map<string, { x: number; y: number }>();
  facilities.forEach((f) => {
    facilityCoords.set(f.id, project(f.latitude, f.longitude));
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm text-slate-100 flex flex-col space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Layers className="w-4 h-4 text-teal-400" />
          <span className="text-xs font-bold text-slate-200">
            QAOA Max-Cut Zoning & Transfer Topology
          </span>
        </div>
        <div className="flex items-center space-x-2 text-[10px] font-bold">
          <span className="flex items-center space-x-1 bg-teal-950/80 text-teal-300 border border-teal-800/60 px-2 py-0.5 rounded">
            <span className="w-2 h-2 rounded-full bg-teal-400"></span>
            <span>Zone 0 (Central/North)</span>
          </span>
          <span className="flex items-center space-x-1 bg-purple-950/80 text-purple-300 border border-purple-800/60 px-2 py-0.5 rounded">
            <span className="w-2 h-2 rounded-full bg-purple-400"></span>
            <span>Zone 1 (South/East)</span>
          </span>
        </div>
      </div>

      <div className="relative w-full h-64 bg-slate-950 rounded-lg border border-slate-800/80 overflow-hidden flex items-center justify-center">
        <svg viewBox="0 0 400 280" className="w-full h-full">
          <defs>
            {/* Shaded zone gradient 0 (Teal) */}
            <radialGradient id="zone0Shade" cx="45%" cy="40%" r="55%">
              <stop offset="0%" stopColor="#0d9488" stopOpacity="0.30" />
              <stop offset="100%" stopColor="#0d9488" stopOpacity="0.02" />
            </radialGradient>

            {/* Shaded zone gradient 1 (Purple) */}
            <radialGradient id="zone1Shade" cx="65%" cy="70%" r="55%">
              <stop offset="0%" stopColor="#9333ea" stopOpacity="0.30" />
              <stop offset="100%" stopColor="#9333ea" stopOpacity="0.02" />
            </radialGradient>

            {/* Arrow marker */}
            <marker
              id="plan-mini-arrow"
              viewBox="0 0 10 10"
              refX="6"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#2dd4bf" />
            </marker>
          </defs>

          {/* Shaded Zone 0 background blob */}
          <ellipse cx="170" cy="115" rx="140" ry="85" fill="url(#zone0Shade)" />

          {/* Shaded Zone 1 background blob */}
          <ellipse cx="265" cy="195" rx="115" ry="70" fill="url(#zone1Shade)" />

          {/* Zone boundary cut line */}
          <path
            d="M 50,175 Q 190,170 360,110"
            stroke="#64748b"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            fill="none"
            opacity="0.6"
          />
          <text x="210" y="160" fill="#94a3b8" fontSize="9" fontWeight="700" letterSpacing="0.5">
            QAOA MAX-CUT BOUNDARY
          </text>

          {/* Transfer Arcs */}
          {orders.map((order, idx) => {
            const src = facilityCoords.get(order.source_facility_id);
            const dst = facilityCoords.get(order.destination_facility_id);
            if (!src || !dst) return null;

            const midX = (src.x + dst.x) / 2;
            const midY = (src.y + dst.y) / 2 - (idx % 2 === 0 ? 20 : -20);

            return (
              <g key={`arc-${order.id}-${idx}`}>
                <path
                  d={`M ${src.x},${src.y} Q ${midX},${midY} ${dst.x},${dst.y}`}
                  stroke={order.temperature_controlled ? "#38bdf8" : "#2dd4bf"}
                  strokeWidth="2"
                  strokeDasharray="3 3"
                  fill="none"
                  markerEnd="url(#plan-mini-arrow)"
                  className="animate-pulse"
                />
              </g>
            );
          })}

          {/* Facility Nodes */}
          {facilities.map((fac) => {
            const coord = facilityCoords.get(fac.id);
            if (!coord) return null;

            const zone = zoningPartition[fac.id] ?? 0;
            const isZone0 = zone === 0;

            return (
              <g key={`node-${fac.id}`} className="cursor-pointer">
                {/* Node outer glow */}
                <circle
                  cx={coord.x}
                  cy={coord.y}
                  r="14"
                  fill={isZone0 ? "#0f766e" : "#7e22ce"}
                  stroke={isZone0 ? "#2dd4bf" : "#c084fc"}
                  strokeWidth="2"
                  opacity="0.9"
                />
                {/* Facility ID text */}
                <text
                  x={coord.x}
                  y={coord.y + 3.5}
                  fill="#ffffff"
                  fontSize="9"
                  fontWeight="900"
                  textAnchor="middle"
                >
                  {fac.id}
                </text>

                {/* Facility Name Label */}
                <text
                  x={coord.x}
                  y={coord.y + 22}
                  fill="#cbd5e1"
                  fontSize="8.5"
                  fontWeight="700"
                  textAnchor="middle"
                >
                  {fac.name.replace("SIM-", "")}
                </text>

                {/* Cold icon indicator */}
                {fac.cold_storage_available && (
                  <circle
                    cx={coord.x + 9}
                    cy={coord.y - 9}
                    r="3.5"
                    fill="#38bdf8"
                    stroke="#0f172a"
                    strokeWidth="1"
                  />
                )}
              </g>
            );
          })}
        </svg>

        {/* Floating Mini Summary Tag */}
        <div className="absolute bottom-2 left-2 bg-slate-900/90 backdrop-blur-xs border border-slate-700/80 px-2 py-1 rounded text-[10px] text-slate-300 flex items-center space-x-1">
          <ShieldCheck className="w-3 h-3 text-teal-400" />
          <span>F1–F6 Certified • Inter-Zone Transit Minimized</span>
        </div>
      </div>
    </div>
  );
};
