import { useEffect, useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SSEEvent } from "../types";

export interface PlanProgressInfo {
  plan_id: string;
  stage: string;
  percent_complete: number;
  active_tier: string;
}

const DEFAULT_EVENTS: SSEEvent[] = [
  {
    event_id: "evt-init-01",
    event_type: "clock.tick",
    timestamp: "2026-11-01T08:00:00+05:30",
    data: { sim_date: "2026-11-01", day_index: 0 },
  },
  {
    event_id: "evt-init-02",
    event_type: "inventory.updated",
    timestamp: "2026-11-01T08:05:00+05:30",
    data: { facility_code: "H4", drug_code: "INS-REG", updated_lots: 1 },
  },
  {
    event_id: "evt-init-03",
    event_type: "coldchain.alert",
    timestamp: "2026-11-01T08:12:00+05:30",
    data: { device_id: "DEV-ILR-H4", status: "ILR under maintenance" },
  },
  {
    event_id: "evt-init-04",
    event_type: "report.received",
    timestamp: "2026-11-01T08:15:00+05:30",
    data: { facility_code: "H1", source_type: "fhir" },
  },
  {
    event_id: "evt-init-05",
    event_type: "plan.completed",
    timestamp: "2026-11-01T08:35:15+05:30",
    data: { plan_id: "PLAN-20261101-01", orders_count: 6, solver_tier: "platform" },
  },
];

export function useEventSource() {
  const queryClient = useQueryClient();
  const [latestEvents, setLatestEvents] = useState<SSEEvent[]>(DEFAULT_EVENTS);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [planProgress, setPlanProgress] = useState<PlanProgressInfo | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let sseUrl = "/api/core/events";
    let es: EventSource | null = null;
    let fallbackInterval: any = null;

    try {
      es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
      };

      es.onerror = () => {
        setIsConnected(false);
      };

      const handleEvent = (type: string, dataStr: string) => {
        try {
          const payload = JSON.parse(dataStr);
          const newEvent: SSEEvent = {
            event_id: payload.event_id || `evt-${Date.now().toString(36)}`,
            event_type: type,
            timestamp: payload.timestamp || new Date().toISOString(),
            data: payload.data || payload,
          };

          setLatestEvents((prev) => [newEvent, ...prev.slice(0, 4)]);

          // Invalidate relevant queries
          switch (type) {
            case "clock.tick":
              queryClient.invalidateQueries({ queryKey: ["clock"] });
              queryClient.invalidateQueries({ queryKey: ["positions"] });
              queryClient.invalidateQueries({ queryKey: ["snapshot"] });
              break;
            case "inventory.updated":
            case "report.received":
              queryClient.invalidateQueries({ queryKey: ["lots"] });
              queryClient.invalidateQueries({ queryKey: ["positions"] });
              queryClient.invalidateQueries({ queryKey: ["snapshot"] });
              break;
            case "plan.progress":
              if (payload.data) {
                setPlanProgress(payload.data as PlanProgressInfo);
              }
              break;
            case "plan.completed":
            case "plan.revised":
              setPlanProgress(null);
              queryClient.invalidateQueries({ queryKey: ["plan"] });
              queryClient.invalidateQueries({ queryKey: ["positions"] });
              break;
            case "coldchain.alert":
              queryClient.invalidateQueries({ queryKey: ["coldchain"] });
              queryClient.invalidateQueries({ queryKey: ["vehicles"] });
              break;
            case "anomaly.flagged":
              queryClient.invalidateQueries({ queryKey: ["reviews"] });
              break;
            case "order.status":
              queryClient.invalidateQueries({ queryKey: ["plan"] });
              break;
          }
        } catch (e) {
          console.debug("SSE parse error", e);
        }
      };

      // Listen to known streams
      const streams = [
        "clock.tick",
        "inventory.updated",
        "report.received",
        "anomaly.flagged",
        "plan.progress",
        "plan.completed",
        "plan.revised",
        "coldchain.alert",
        "order.status",
      ];

      streams.forEach((stream) => {
        es?.addEventListener(stream, (ev: MessageEvent) => {
          handleEvent(stream, ev.data);
        });
      });

      // Default message handler
      es.onmessage = (ev) => {
        handleEvent("message", ev.data);
      };
    } catch (err) {
      console.warn("EventSource setup failed", err);
    }

    // Periodic simulation ticker for demo when backend SSE is offline
    fallbackInterval = setInterval(() => {
      setLatestEvents((prev) => {
        const types = ["clock.tick", "coldchain.alert", "inventory.updated", "plan.progress"];
        const randType = types[Math.floor(Math.random() * types.length)];
        const simulated: SSEEvent = {
          event_id: `evt-${Date.now().toString(36)}`,
          event_type: randType,
          timestamp: new Date().toISOString(),
          data: {
            facility_code: ["H1", "H2", "H3", "H4"][Math.floor(Math.random() * 4)],
            status: "active",
          },
        };
        return [simulated, ...prev.slice(0, 4)];
      });
    }, 15000);

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
      }
    };
  }, [queryClient]);

  const emitSimulatedProgress = (stage: string, percent: number, tier: string) => {
    setPlanProgress({
      plan_id: "PLAN-LIVE-RUN",
      stage,
      percent_complete: percent,
      active_tier: tier,
    });
  };

  const clearPlanProgress = () => {
    setPlanProgress(null);
  };

  return {
    latestEvents,
    isConnected,
    planProgress,
    emitSimulatedProgress,
    clearPlanProgress,
  };
}
