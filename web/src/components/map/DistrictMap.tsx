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
  const [viewMode, setViewMode] = useState<"leaflet" | "svg">("svg"); // Default to SVG schematic for instant zero-latency projector rendering

  // Create custom HTML DivIcon for Leaflet
  const createFacilityIcon = (facility: Facility) => {
    let ringColor = "#10b981"; // Emerald
    let pulseAnim = "";
    if (facility.health_status === "critical") {
      ringColor = "#ef4444"; // Red
      pulseAnim = "animate-ping";
    } else if (facility.health_status === "warning") {
      ringColor = "#f59e0b"; // Amber
    }

    const isSelected = selectedFacilityId === facility.id;

    return L.divIcon({
      className: "custom-facility-marker",
      html: `
        <div style="position: relative; display: flex; flex-direction: column; align-items: center; cursor: pointer;">
          <div style="width: 44px; height: 44px; border-radius: 9999px; border: 3px solid ${ringColor}; background: rgba(15, 23, 42, 0.95); display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); ${
            isSelected ? "transform: scale(1.15); border-width: 4px;" : ""
          }">
            <span style="color: white; font-weight: 800; font-size: 13px; letter-spacing: -0.5px;">${facility.id}</span>
            ${
              facility.cold_storage_available
                ? '<div style="position: absolute; top: -3px; right: -3px; width: 14px; height: 14px; border-radius: 9999px; background: #06b6d4; border: 2px solid #0f172a;"></div>'
                : ""
            }
          </div>
          <div style="margin-top: 4px; background: #0f172a; color: #f8fafc; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; border: 1px solid #334155; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
            ${facility.name}
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
    <div className="relative w-full h-full flex flex-col overflow-hidden bg-slate-900">
      {/* Top Map Floating Bar: View Toggle and District Header */}
      <div className="absolute top-4 left-4 z-20 flex items-center space-x-3 pointer-events-auto">
        <div className="bg-slate-900/90 backdrop-blur-xs border border-slate-700 px-4 py-2 rounded-xl shadow-lg flex items-center space-x-3 text-white">
          <span className="w-2.5 h-2.5 rounded-full bg-teal-400 animate-pulse"></span>
          <div>
            <h2 className="text-sm font-bold tracking-tight">Bengaluru Urban District Twin</h2>
            <p className="text-[11px] text-slate-400 font-medium">5 Facilities · Active Transfer Network</p>
          </div>
        </div>

        {/* View Toggle */}
        <div className="bg-slate-900/90 backdrop-blur-xs border border-slate-700 p-1 rounded-xl shadow-lg flex items-center space-x-1">
          <button
            onClick={() => setViewMode("svg")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              viewMode === "svg"
                ? "bg-teal-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Schematic SVG
          </button>
          <button
            onClick={() => setViewMode("leaflet")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              viewMode === "leaflet"
                ? "bg-teal-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Geographic GIS
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
                  <div className="p-1">
                    <h3 className="font-bold text-sm text-slate-900">{facility.name}</h3>
                    <p className="text-xs text-slate-600 font-semibold">Level: {facility.facility_type}</p>
                    <p className="text-xs text-teal-700 mt-1 font-medium">
                      Cold Chain: {facility.cold_storage_available ? "Available" : "None"}
                    </p>
                    <button
                      onClick={() => onSelectFacility(facility)}
                      className="mt-2 w-full bg-teal-600 text-white py-1 px-2 rounded text-xs font-bold"
                    >
                      Inspect Stock & FEFO
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
                    color: isCold ? "#06b6d4" : "#0d9488",
                    weight: isCold ? 4 : 3,
                    dashArray: isCold ? "8, 6" : undefined,
                    opacity: 0.85,
                  }}
                >
                  <Tooltip sticky>
                    <div className="text-xs font-semibold">
                      <span className="font-bold">{order.id}</span>
                      <div>
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
