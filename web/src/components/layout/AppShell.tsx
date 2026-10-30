import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TopBar } from "./TopBar";
import { SidebarNav } from "./SidebarNav";
import { DistrictMap } from "../map/DistrictMap";
import { FacilityDrawer } from "../drawer/FacilityDrawer";
import { PlanView } from "../plan/PlanView";
import { IngestionScreen } from "../screens/IngestionScreen";
import { ColdchainScreen } from "../screens/ColdchainScreen";
import { BenchmarkScreen } from "../screens/BenchmarkScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import { AiHealthScreen } from "../screens/AiHealthScreen";
import { ScenariosScreen } from "../screens/ScenariosScreen";
import { ScanScreen } from "../screens/ScanScreen";
import { CopilotPanel } from "../copilot/CopilotPanel";
import { useEventSource } from "../../hooks/useEventSource";
import { api } from "../../lib/api";
import { Facility, NavPage, PlanRun, Position, Drug } from "../../types";
import { Flame, ArrowRight, ShieldAlert } from "lucide-react";

export const AppShell: React.FC = () => {
  const getUrlParams = () => {
    if (typeof window === "undefined") return { page: "map" as NavPage, facilityId: null };
    const pathname = window.location.pathname.toLowerCase();
    const params = new URLSearchParams(window.location.search);
    const pageParam = params.get("page") as NavPage | null;
    const facilityId = params.get("facility");

    if (pageParam) {
      return { page: pageParam, facilityId };
    }
    if (pathname.startsWith("/scan")) {
      return { page: "scan" as NavPage, facilityId: null };
    }
    if (pathname.includes("/hub") || pathname.includes("/planner") || pathname.includes("/plan")) {
      return { page: "plan" as NavPage, facilityId };
    }
    if (pathname.includes("/quantum") || pathname.includes("/benchmark")) {
      return { page: "benchmark" as NavPage, facilityId };
    }
    if (pathname.includes("/coldchain")) {
      return { page: "coldchain" as NavPage, facilityId };
    }
    if (pathname.includes("/scenarios") || pathname.includes("/scenario")) {
      return { page: "scenarios" as NavPage, facilityId };
    }
    if (pathname.includes("/ingestion") || pathname.includes("/review")) {
      return { page: "ingestion" as NavPage, facilityId };
    }
    if (pathname.includes("/results")) {
      return { page: "results" as NavPage, facilityId };
    }
    if (pathname.includes("/ai-health") || pathname.includes("/aihealth")) {
      return { page: "ai-health" as NavPage, facilityId };
    }
    if (pathname.includes("/dashboard") || pathname.includes("/map")) {
      return { page: "map" as NavPage, facilityId };
    }

    return { page: "map" as NavPage, facilityId };
  };

  const initialParams = getUrlParams();
  const [activePage, setActivePage] = useState<NavPage>(initialParams.page);
  const [selectedFacility, setSelectedFacility] = useState<Facility | null>(null);

  const {
    latestEvents,
    isConnected,
    planProgress,
    emitSimulatedProgress,
    clearPlanProgress,
  } = useEventSource();

  const { data: rawFacilities = [] } = useQuery<Facility[]>({
    queryKey: ["facilities"],
    queryFn: () => api.getFacilities(),
  });

  const { data: positions = [] } = useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: () => api.getPositions(),
  });

  const { data: drugs = [] } = useQuery<Drug[]>({
    queryKey: ["drugs"],
    queryFn: () => api.getDrugs(),
  });

  const { data: plan } = useQuery<PlanRun>({
    queryKey: ["plan"],
    queryFn: () => api.getLatestPlan(),
  });

  const { data: clock } = useQuery({
    queryKey: ["clock"],
    queryFn: () => api.getClock(),
  });

  const { data: coldchainStatus } = useQuery({
    queryKey: ["coldchain"],
    queryFn: () => api.getColdchainStatus(),
    refetchInterval: 3000,
  });

  // Calculate VEN-weighted stock health ring status per facility
  const drugMap = new Map<string, Drug>();
  drugs.forEach((d) => drugMap.set(d.code, d));

  const enrichedFacilities: Facility[] = rawFacilities.map((f) => {
    const facPositions = positions.filter((p) => p.facility_id === f.id);
    let health: "healthy" | "warning" | "critical" = "healthy";

    let vitalShortage = false;
    let anyShortage = false;
    let anyAtRisk = false;

    facPositions.forEach((pos) => {
      const cat = drugMap.get(pos.drug_code)?.category || "E";
      if (pos.shortage > 0) {
        anyShortage = true;
        if (cat === "V") vitalShortage = true;
      }
      if (pos.at_risk_stock > 0) {
        anyAtRisk = true;
      }
    });

    if (vitalShortage) {
      health = "critical";
    } else if (anyShortage || anyAtRisk) {
      health = "warning";
    }

    return {
      ...f,
      health_status: health,
    };
  });

  const orders = plan?.orders || [];

  // Excursion detection for global red banner
  const excursionDevices = (coldchainStatus?.devices || []).filter(
    (d: any) => d.status === "EXCURSION"
  );
  const recentExcursionEvent = latestEvents.find(
    (e) =>
      e.event_type === "coldchain.alert" &&
      (e.data?.severity === "CRITICAL" || e.data?.alert_type === "EXCURSION")
  );
  const isExcursionActive =
    excursionDevices.length > 0 ||
    Boolean(recentExcursionEvent) ||
    (coldchainStatus?.active_excursions_count || 0) > 0;

  const excursionDevice =
    excursionDevices[0] ||
    (recentExcursionEvent?.data
      ? {
          device_id: recentExcursionEvent.data.device_id,
          target_name: recentExcursionEvent.data.vehicle_id || "Cold Van CV-02",
          latest_temp_c: recentExcursionEvent.data.temperature_c || 11.4,
        }
      : null);

  // Deep linking sync: on mount or facilities change, open drawer if facility param provided
  React.useEffect(() => {
    if (initialParams.facilityId && enrichedFacilities.length > 0 && !selectedFacility) {
      const match = enrichedFacilities.find((f) => f.id === initialParams.facilityId);
      if (match) setSelectedFacility(match);
    }
  }, [enrichedFacilities, initialParams.facilityId]);

  // Sync state with browser history (back/forward)
  React.useEffect(() => {
    const handlePopState = () => {
      const { page, facilityId } = getUrlParams();
      setActivePage(page);
      if (facilityId && enrichedFacilities.length > 0) {
        const match = enrichedFacilities.find((f) => f.id === facilityId);
        setSelectedFacility(match || null);
      } else {
        setSelectedFacility(null);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [enrichedFacilities]);

  const handleSelectPage = (page: NavPage) => {
    setActivePage(page);
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("page", page);
      window.history.pushState({}, "", url);
    } catch {}
  };

  const handleSelectFacility = (fac: Facility | null) => {
    setSelectedFacility(fac);
    try {
      const url = new URL(window.location.href);
      if (fac) {
        url.searchParams.set("facility", fac.id);
      } else {
        url.searchParams.delete("facility");
      }
      window.history.pushState({}, "", url);
    } catch {}
  };

  // Dedicated full-screen mobile layout when opened via /scan on a phone over LAN
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/scan")) {
    return (
      <ScanScreen
        onNavigateHome={() => {
          try {
            window.history.pushState({}, "", "/?page=map");
          } catch {}
          setActivePage("map");
        }}
      />
    );
  }

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-100">
      {/* Top Bar with Simulation Clock and Live Event Ticker */}
      <TopBar events={latestEvents} isConnected={isConnected} />

      {/* Global Red Excursion Banner Across App */}
      {isExcursionActive && (
        <div className="bg-rose-600 text-white px-5 py-2 text-xs font-bold flex items-center justify-between shadow-md z-40 animate-in slide-in-from-top duration-300">
          <div className="flex items-center space-x-2.5">
            <Flame className="w-4 h-4 text-amber-300 animate-bounce shrink-0" />
            <span>
              CRITICAL COLD CHAIN EXCURSION DETECTED — Device{" "}
              <strong className="underline">{excursionDevice?.device_id || "DEV-CV-02"}</strong> (
              {excursionDevice?.target_name || "Cold Van CV-02"}):{" "}
              <strong className="text-amber-200">
                {excursionDevice?.latest_temp_c ? `${excursionDevice.latest_temp_c.toFixed(1)} °C` : "11.4 °C"}
              </strong>{" "}
              exceeding safe 2.0–8.0 °C threshold. Associated transit routes marked UNSAFE. Automated transfer locks applied.
            </span>
          </div>

          <button
            onClick={() => handleSelectPage("coldchain")}
            className="ml-4 bg-white text-rose-700 hover:bg-rose-50 px-3 py-1 rounded-lg text-[11px] font-black uppercase tracking-wide shrink-0 transition-colors shadow-2xs flex items-center space-x-1"
          >
            <span>Inspect Monitor</span>
            <ArrowRight className="w-3 h-3 ml-0.5" />
          </button>
        </div>
      )}

      {/* Main Workspace with Sidebar Nav and Active Screen */}
      <div className="flex flex-1 overflow-hidden relative min-h-0">
        <SidebarNav activePage={activePage} onSelectPage={handleSelectPage} />

        <main className={`flex-1 relative ${activePage === "map" ? "overflow-hidden" : "overflow-y-auto"} bg-slate-50 min-h-0`}>
          {activePage === "map" && (
            <DistrictMap
              facilities={enrichedFacilities}
              orders={orders}
              selectedFacilityId={selectedFacility?.id || null}
              onSelectFacility={handleSelectFacility}
            />
          )}

          {activePage === "plan" && (
            <PlanView
              planProgress={planProgress}
              onSimulateProgress={emitSimulatedProgress}
              onClearProgress={clearPlanProgress}
            />
          )}

          {activePage === "ingestion" && <IngestionScreen />}
          {activePage === "coldchain" && <ColdchainScreen />}
          {activePage === "benchmark" && <BenchmarkScreen />}
          {activePage === "results" && <ResultsScreen />}
          {activePage === "ai-health" && <AiHealthScreen />}
          {activePage === "scenarios" && <ScenariosScreen />}
          {activePage === "scan" && <ScanScreen onNavigateHome={() => handleSelectPage("map")} />}
        </main>

        {/* Facility Inspection Drawer */}
        {selectedFacility && (
          <FacilityDrawer
            facility={selectedFacility}
            onClose={() => handleSelectFacility(null)}
            todayStr={clock?.today}
          />
        )}
      </div>

      {/* Floating Persistently Available Copilot Drawer */}
      <CopilotPanel />
    </div>
  );
};
