import React from "react";
import { Facility, TransferOrder } from "../../types";
import { Snowflake } from "lucide-react";

interface DistrictSvgFallbackProps {
  facilities: Facility[];
  orders: TransferOrder[];
  selectedFacilityId: string | null;
  onSelectFacility: (facility: Facility) => void;
}

export const DistrictSvgFallback: React.FC<DistrictSvgFallbackProps> = ({
  facilities,
  orders,
  selectedFacilityId,
  onSelectFacility,
}) => {
  // Coordinate normalization: Longitude [77.35..77.85] -> x [60..740], Latitude [12.65..13.20] -> y [540..60]
  const project = (lat: number, lng: number) => {
    const x = ((lng - 77.35) / (77.85 - 77.35)) * 680 + 60;
    const y = ((13.20 - lat) / (13.20 - 12.65)) * 480 + 60;
    return { x, y };
  };

  const facilityCoords = new Map<string, { x: number; y: number }>();
  facilities.forEach((f) => {
    facilityCoords.set(f.id, project(f.latitude, f.longitude));
  });

  return (
    <div className="relative w-full h-full bg-slate-900 overflow-hidden flex items-center justify-center select-none">
      {/* Background District Map Schematic */}
      <svg
        viewBox="0 0 800 600"
        className="w-full h-full max-w-5xl max-h-[85vh] drop-shadow-2xl"
      >
        <defs>
          {/* Gradient for ambient routes */}
          <linearGradient id="ambientRoute" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#14b8a6" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#0d9488" stopOpacity="0.95" />
          </linearGradient>

          {/* Gradient for cold chain routes */}
          <linearGradient id="coldRoute" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.95" />
          </linearGradient>

          {/* Arrow markers */}
          <marker
            id="arrow-ambient"
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#14b8a6" />
          </marker>
          <marker
            id="arrow-cold"
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#06b6d4" />
          </marker>

          {/* Glow filter */}
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Outer District Stylized Boundaries (Bengaluru Urban outline) */}
        <path
          d="M 180,90 Q 320,40 450,70 Q 640,110 710,220 Q 750,340 680,450 Q 580,560 480,550 Q 320,530 220,470 Q 90,390 110,250 Z"
          fill="#0f172a"
          stroke="#1e293b"
          strokeWidth="3"
        />

        {/* Taluk divider guidelines */}
        <path
          d="M 180,90 C 290,260 480,270 710,220"
          fill="none"
          stroke="#334155"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
        <path
          d="M 220,470 C 380,390 490,420 680,450"
          fill="none"
          stroke="#334155"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />

        {/* Taluk Label Watermarks */}
        <text x="350" y="140" fill="#475569" fontSize="13" fontWeight="bold" letterSpacing="2">
          BANGALORE NORTH TALUK
        </text>
        <text x="360" y="340" fill="#475569" fontSize="13" fontWeight="bold" letterSpacing="2">
          BANGALORE SOUTH TALUK
        </text>
        <text x="500" y="470" fill="#475569" fontSize="13" fontWeight="bold" letterSpacing="2">
          ANEKAL TALUK
        </text>

        {/* Transfer Arcs (Curved Bezier Paths) */}
        {orders.map((order) => {
          const src = facilityCoords.get(order.source_facility_id);
          const dst = facilityCoords.get(order.destination_facility_id);
          if (!src || !dst) return null;

          // Curvature midpoint
          const dx = dst.x - src.x;
          const dy = dst.y - src.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const offset = Math.min(60, dist * 0.2);

          // Normal vector for curve
          const cx = (src.x + dst.x) / 2 - (dy / dist) * offset;
          const cy = (src.y + dst.y) / 2 + (dx / dist) * offset;

          const isCold = order.temperature_controlled;
          const pathId = `path-${order.id.replace(/[/\\-]/g, "_")}`;

          return (
            <g key={order.id} className="transition-all hover:opacity-100">
              {/* Shadow arc */}
              <path
                d={`M ${src.x},${src.y} Q ${cx},${cy} ${dst.x},${dst.y}`}
                fill="none"
                stroke={isCold ? "#0891b2" : "#0d9488"}
                strokeWidth="5"
                strokeOpacity="0.2"
              />
              {/* Main transfer route arc */}
              <path
                id={pathId}
                d={`M ${src.x},${src.y} Q ${cx},${cy} ${dst.x},${dst.y}`}
                fill="none"
                stroke={isCold ? "url(#coldRoute)" : "url(#ambientRoute)"}
                strokeWidth={isCold ? 3 : 2.5}
                strokeDasharray={isCold ? "6 3" : "none"}
                markerEnd={isCold ? "url(#arrow-cold)" : "url(#arrow-ambient)"}
                filter="url(#glow)"
              />

              {/* Transfer bubble label at curve apex */}
              <g transform={`translate(${cx}, ${cy})`}>
                <rect
                  x="-38"
                  y="-11"
                  width="76"
                  height="22"
                  rx="11"
                  fill="#020617"
                  stroke={isCold ? "#06b6d4" : "#14b8a6"}
                  strokeWidth="1.5"
                />
                <text
                  x="0"
                  y="4"
                  fill="#f8fafc"
                  fontSize="10"
                  fontWeight="bold"
                  textAnchor="middle"
                >
                  {order.quantity} {order.drug_code}
                </text>
              </g>
            </g>
          );
        })}

        {/* Facility Nodes and Rings */}
        {facilities.map((facility) => {
          const pt = facilityCoords.get(facility.id);
          if (!pt) return null;

          const isSelected = selectedFacilityId === facility.id;

          // VEN Shortage Health Ring Color
          let ringColor = "#10b981"; // Emerald
          let pulseClass = "";
          if (facility.health_status === "critical") {
            ringColor = "#ef4444"; // Red
            pulseClass = "animate-pulse";
          } else if (facility.health_status === "warning") {
            ringColor = "#f59e0b"; // Amber
          }

          return (
            <g
              key={facility.id}
              transform={`translate(${pt.x}, ${pt.y})`}
              className="cursor-pointer group"
              onClick={() => onSelectFacility(facility)}
            >
              {/* Outer Health Ring */}
              <circle
                r={isSelected ? 30 : 25}
                fill={ringColor}
                fillOpacity="0.15"
                stroke={ringColor}
                strokeWidth={isSelected ? 3.5 : 2.5}
                className={pulseClass}
              />

              {/* Inner Node Pill */}
              <circle
                r="16"
                fill="#0f172a"
                stroke={isSelected ? "#ffffff" : "#475569"}
                strokeWidth="2"
                filter="url(#glow)"
              />

              {/* Facility ID Text */}
              <text
                x="0"
                y="5"
                fill="#ffffff"
                fontSize="11"
                fontWeight="bold"
                textAnchor="middle"
              >
                {facility.id}
              </text>

              {/* Cold storage indicator badge */}
              {facility.cold_storage_available && (
                <circle cx="12" cy="-12" r="6" fill="#06b6d4" stroke="#0f172a" strokeWidth="1.5" />
              )}

              {/* Facility Name & Level Card */}
              <g transform="translate(0, 36)">
                <rect
                  x="-75"
                  y="-10"
                  width="150"
                  height="34"
                  rx="6"
                  fill="#1e293b"
                  stroke={isSelected ? "#14b8a6" : "#334155"}
                  strokeWidth={isSelected ? 2 : 1}
                  className="shadow-lg"
                />
                <text
                  x="0"
                  y="4"
                  fill="#f1f5f9"
                  fontSize="11"
                  fontWeight="bold"
                  textAnchor="middle"
                >
                  {facility.name}
                </text>
                <text
                  x="0"
                  y="18"
                  fill="#94a3b8"
                  fontSize="9.5"
                  fontWeight="semibold"
                  textAnchor="middle"
                >
                  Level: {facility.facility_type}
                </text>
              </g>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
