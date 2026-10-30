import React, { useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, Tooltip } from "react-leaflet";
import L from "leaflet";
import { Facility, TransferOrder } from "../../types";
import { DistrictSvgFallback } from "./DistrictSvgFallback";
import { MapLegend } from "./MapLegend";
import { Map as MapIcon, SlidersHorizontal, Snowflake } from "lucide-react";

interface DistrictMapProps {
  facilities: Facility[];
  orders: TransferOrder[];
  selectedFacilityId: string | null;
  onSelectFacility: (facility: Facility) => void;
}

export const DistrictMap: React.FC<DistrictMapProps> = ({
  facilities,
  orders,
  selectedFacilityId,
  onSelectFacility,
}) => {
  // Default to genuine Leaflet OpenStreetMap geographic view
  const [viewMode, setViewMode] = useState<"leaflet" | "svg">("leaflet");

  // Create clean White & Blue themed custom HTML DivIcon for Leaflet
  const createFacilityIcon = (facility: Facility) => {
    let ringColor = "#10b981"; // Emerald for healthy
    if (facility.health_status === "critical") {
      ringColor = "#ef4444"; // Red for critical shortage
    } else if (facility.health_status === "warning") {
      ringColor = "#f59e0b"; // Amber for warning
    }

    const isSelected = selectedFacilityId === facility.id;

    return L.divIcon({
      className: "custom-facility-marker",
      html: `
        <div style="position: relative; display: flex; flex-direction: column; align-items: center; cursor: pointer;">
          <div style="width: 44px; height: 44px; border-radius: 9999px; border: 3px solid ${ringColor}; background: #ffffff; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(15, 23, 42, 0.18); transition: transform 0.15s ease; ${
            isSelected ? "transform: scale(1.18); border-width: 4px; box-shadow: 0 6px 14px rgba(37, 99, 235, 0.35);" : ""
          }">
            <span style="color: #1e3a8a; font-weight: 900; font-size: 14px; letter-spacing: -0.5px;">${facility.id}</span>
            ${
              facility.cold_storage_available
                ? '<div style="position: absolute; top: -3px; right: -3px; width: 14px; height: 14px; border-radius: 9999px; background: #0284c7; border: 2px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.2);"></div>'
                : ""
            }
          </div>
          <div style="margin-top: 4px; background: #ffffff; color: #0f172a; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; border: 1px solid #cbd5e1; white-space: nowrap; box-shadow: 0 2px 6px rgba(0,0,0,0.12); display: flex; align-items: center; gap: 4px;">
            <span style="width: 6px; height: 6px; border-radius: 9999px; background: ${ringColor}; display: inline-block;"></span>
            <span>${facility.name}</span>
          </div>
        </div>
      `,
      iconSize: [60, 60],
      iconAnchor: [30, 22],
    });
  };

  const facilityMap = new Map<string, Facility>();
  facilities.forEach((f) => facilityMap.set(f.id, f));

  return (
    <div className="relative w-full h-full flex flex-col overflow-hidden bg-slate-100">
      {/* Top Map Floating Bar: View Toggle and District Header */}
      <div className="absolute top-4 left-4 z-20 flex items-center space-x-3 pointer-events-auto">
        <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 px-4 py-2.5 rounded-2xl shadow-md flex items-center space-x-3 text-slate-800">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-600 animate-pulse"></span>
          <div>
            <h2 className="text-sm font-black tracking-tight text-slate-900">
              Bengaluru Urban District Overview
            </h2>
            <p className="text-[11px] text-slate-500 font-medium">
              5 Primary Facilities · Real-Time Geographic Routing
            </p>
          </div>
        </div>

        {/* View Toggle */}
        <div className="bg-white/95 backdrop-blur-md border border-slate-200/90 p-1 rounded-2xl shadow-md flex items-center space-x-1">
          <button
            onClick={() => setViewMode("leaflet")}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              viewMode === "leaflet"
                ? "bg-blue-600 text-white shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Geographic GIS (Original Map)
          </button>
          <button
            onClick={() => setViewMode("svg")}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              viewMode === "svg"
                ? "bg-blue-600 text-white shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Schematic Diagram
          </button>
        </div>
      </div>

      {/* Floating Map Legend (Bottom Left) */}
      <div className="absolute bottom-6 left-6 z-20 pointer-events-auto">
        <MapLegend />
      </div>

      {/* Viewport Rendering */}
      {viewMode === "svg" ? (
        <DistrictSvgFallback
          facilities={facilities}
          orders={orders}
          selectedFacilityId={selectedFacilityId}
          onSelectFacility={onSelectFacility}
        />
      ) : (
        <div className="w-full h-full">
          <MapContainer
            center={[12.9716, 77.5946]}
            zoom={11}
            scrollWheelZoom={true}
            className="w-full h-full"
            style={{ height: "100%", width: "100%" }}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* Facility Markers */}
            {facilities.map((facility) => (
              <Marker
                key={facility.id}
                position={[facility.latitude, facility.longitude]}
                icon={createFacilityIcon(facility)}
                eventHandlers={{
                  click: () => onSelectFacility(facility),
                }}
              >
                <Popup>
                  <div className="p-1 space-y-1">
                    <h3 className="font-bold text-sm text-slate-900">{facility.name}</h3>
                    <p className="text-xs text-slate-600 font-semibold">Level: {facility.facility_type}</p>
                    <p className="text-xs text-blue-700 font-semibold">
                      Cold Storage: {facility.cold_storage_available ? "Operational (2–8 °C)" : "None"}
                    </p>
                    <button
                      onClick={() => onSelectFacility(facility)}
                      className="mt-2 w-full bg-blue-600 hover:bg-blue-700 text-white py-1.5 px-3 rounded-lg text-xs font-bold shadow-xs transition-colors"
                    >
                      Inspect Stock & FEFO Drawer
                    </button>
                  </div>
                </Popup>
              </Marker>
            ))}

            {/* Transfer Route Polylines */}
            {orders.map((order) => {
              const src = facilityMap.get(order.source_facility_id);
              const dst = facilityMap.get(order.destination_facility_id);
              if (!src || !dst) return null;

              const isCold = order.temperature_controlled;

              return (
                <Polyline
                  key={order.id}
                  positions={[
                    [src.latitude, src.longitude],
                    [dst.latitude, dst.longitude],
                  ]}
                  pathOptions={{
                    color: isCold ? "#0284c7" : "#2563eb",
                    weight: isCold ? 4 : 3,
                    dashArray: isCold ? "6, 6" : undefined,
                    opacity: 0.9,
                  }}
                >
                  <Tooltip sticky>
                    <div className="text-xs font-semibold p-1">
                      <span className="font-bold text-blue-900">{order.id}</span>
                      <div className="text-slate-800">
                        {order.quantity} units of {order.drug_code}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {src.name} &rarr; {dst.name}
                      </div>
                    </div>
                  </Tooltip>
                </Polyline>
              );
            })}
          </MapContainer>
        </div>
      )}
    </div>
  );
};
