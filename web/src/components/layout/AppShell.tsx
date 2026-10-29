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
import { useEventSource } from "../../hooks/useEventSource";
import { api } from "../../lib/api";
import { Facility, NavPage, PlanRun, Position, Drug } from "../../types";

export const AppShell: React.FC = () => {
  const getUrlParams = () => {
    if (typeof window === "undefined") return { page: "map" as NavPage, facilityId: null };
    const params = new URLSearchParams(window.location.search);
    const page = (params.get("page") as NavPage) || "map";
    const facilityId = params.get("facility");
    return { page, facilityId };
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

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-100">
      {/* Top Bar with Simulation Clock and Live Event Ticker */}
      <TopBar events={latestEvents} isConnected={isConnected} />

      {/* Main Workspace with Sidebar Nav and Active Screen */}
      <div className="flex flex-1 overflow-hidden relative">
        <SidebarNav activePage={activePage} onSelectPage={handleSelectPage} />

        <main className="flex-1 overflow-hidden relative bg-slate-50">
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
    </div>
  );
};
