import type { AnalyticsCluster, StationAnchor } from "./analytics-types";

export type MappedStation = StationAnchor & {
  patient_count: number | null;
  suppressed?: boolean;
};

export interface MumbaiStationMapProps {
  stations: MappedStation[];
  groups: AnalyticsCluster[];
  selectedStationId: string | null;
  selectedGroupId: number | null;
  onStationSelect: (stationId: string) => void;
  onGroupSelect: (groupId: number) => void;
  onClearSelection?: () => void;
}

export const RAIL_COLORS: Record<string, string> = {
  Central: "#2d6aab",
  Western: "#a54b75",
  Harbour: "#19816c",
  Interchange: "#7656a3",
};

export function stationColor(station: Pick<MappedStation, "lines" | "suppressed" | "patient_count">) {
  if (station.suppressed || station.patient_count == null) return "#96a39b";
  return station.lines.length > 1 ? RAIL_COLORS.Interchange : RAIL_COLORS[station.lines[0]] || RAIL_COLORS.Harbour;
}

const GROUP_COLORS = ["#176d5a", "#326c9f", "#97642e", "#80529a", "#557d35", "#a24f62"];

export function groupColor(groupId: number) {
  return GROUP_COLORS[Math.abs(groupId) % GROUP_COLORS.length];
}
