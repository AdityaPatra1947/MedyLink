"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { AlertCircle, Expand, Layers, LoaderCircle, MapPin, RotateCcw } from "lucide-react";
import type { LatLngBoundsExpression, LatLngTuple, LayerGroup, Map as LeafletMap, Marker } from "leaflet";
import type { AnalyticsCluster } from "@/lib/analytics-types";
import { groupColor, stationColor, type MappedStation, type MumbaiStationMapProps } from "@/lib/mumbai-map";
import "leaflet/dist/leaflet.css";
import styles from "./mumbai-station-map.module.css";

type MapLibrary = typeof import("leaflet");
type MapLayer = "stations" | "groups";
type ViewMode = "fit" | "selection" | "mumbai" | "manual";
type VisibleGroup = AnalyticsCluster & { centroid: { latitude: number; longitude: number }; patient_count: number };
type Runtime = {
  library: MapLibrary;
  map: LeafletMap;
  stations: LayerGroup;
  groups: LayerGroup;
  stationMarkers: Map<string, Marker>;
  groupMarkers: Map<number, Marker>;
  markerCleanup: (() => void)[];
  viewMode: ViewMode;
  settingView: boolean;
};

const MUMBAI_BOUNDS: LatLngBoundsExpression = [[18.86, 72.73], [19.52, 73.22]];
const number = new Intl.NumberFormat("en-IN");
const shortNumber = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const validPosition = (latitude: number, longitude: number) => Number.isFinite(latitude) && Number.isFinite(longitude) && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
const hiddenCount = (count: number | null, suppressed: boolean | undefined) => suppressed || count == null || !Number.isFinite(count) || count < 0 || (count > 0 && count < 5);
const roundCoordinate = (value: number) => Math.round(value * 1000) / 1000;

function groupBounds(group: VisibleGroup): LatLngTuple[] | null {
  const bounds = group.bounds;
  if (!bounds || !validPosition(bounds.south, bounds.west) || !validPosition(bounds.north, bounds.east) || bounds.south > bounds.north || bounds.west > bounds.east) return null;
  return [[roundCoordinate(bounds.south), roundCoordinate(bounds.west)], [roundCoordinate(bounds.north), roundCoordinate(bounds.east)]];
}

function updateView(runtime: Runtime, mode: ViewMode, update: () => void) {
  runtime.viewMode = mode;
  runtime.settingView = true;
  try { runtime.map.stop(); update(); } finally { runtime.settingView = false; }
}

function resetView(runtime: Runtime) {
  updateView(runtime, "mumbai", () => runtime.map.fitBounds(MUMBAI_BOUNDS, { padding: [18, 18], animate: false }));
}

function fitLocations(runtime: Runtime, layer: MapLayer, stations: MappedStation[], groups: VisibleGroup[]) {
  const points: LatLngTuple[] = layer === "stations"
    ? stations.map(station => [station.latitude, station.longitude])
    : groups.flatMap(group => {
      const bounds = groupBounds(group);
      return bounds || [[roundCoordinate(group.centroid.latitude), roundCoordinate(group.centroid.longitude)]];
    });
  updateView(runtime, "fit", () => {
    if (!points.length) runtime.map.fitBounds(MUMBAI_BOUNDS, { padding: [18, 18], animate: false });
    else runtime.map.fitBounds(points, { padding: [40, 40], maxZoom: points.length === 1 ? 13 : 14, animate: false });
  });
}

function fitSelection(runtime: Runtime, layer: MapLayer, stationId: string | null, groupId: number | null, groups: VisibleGroup[]) {
  if (layer === "stations" && stationId != null) {
    const marker = runtime.stationMarkers.get(stationId);
    if (marker) updateView(runtime, "selection", () => runtime.map.setView(marker.getLatLng(), Math.max(13, runtime.map.getZoom()), { animate: false }));
  } else if (layer === "groups" && groupId != null) {
    const group = groups.find(item => item.cluster === groupId);
    if (group) updateView(runtime, "selection", () => {
      const bounds = groupBounds(group);
      if (bounds) runtime.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15, animate: false });
      else runtime.map.setView([roundCoordinate(group.centroid.latitude), roundCoordinate(group.centroid.longitude)], 14, { animate: false });
    });
  }
}

function makeMarker(runtime: Runtime, position: LatLngTuple, label: string, content: string, color: string, onSelect: () => void, group = false) {
  const circle = document.createElement("span");
  circle.className = styles.markerCircle;
  circle.style.setProperty("--marker-color", color);
  circle.textContent = content;
  const tooltip = document.createElement("span");
  tooltip.textContent = label.replace(/^Select /, "");
  const marker = runtime.library.marker(position, {
    icon: runtime.library.divIcon({ className: `${styles.marker}${group ? ` ${styles.groupMarker}` : ""}`, html: circle, iconSize: [42, 42], iconAnchor: [21, 21] }),
    keyboard: true,
    autoPanOnFocus: false,
    title: label,
    alt: label,
    riseOnHover: true,
    bubblingMouseEvents: false,
  });
  marker.bindTooltip(tooltip, { direction: "top", offset: [0, -19], className: styles.tooltip, opacity: 1 });
  marker.on("click", onSelect);
  let removeElementHandlers = () => {};
  const prepareElement = () => {
    removeElementHandlers();
    const element = marker.getElement();
    if (!element) return;
    element.setAttribute("role", "button");
    element.setAttribute("aria-label", label);
    element.setAttribute("aria-pressed", "false");
    // A div icon needs explicit keyboard activation, including in touch browsers.
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === " " || event.key === "Enter") { event.preventDefault(); event.stopPropagation(); onSelect(); }
    };
    let pointerStart: { x: number; y: number } | null = null;
    const onPointerDown = (event: PointerEvent) => { pointerStart = { x: event.clientX, y: event.clientY }; };
    const onClick = (event: MouseEvent) => {
      event.preventDefault(); event.stopPropagation();
      const dragged = pointerStart && Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 8;
      pointerStart = null;
      if (!dragged) onSelect();
    };
    element.addEventListener("keydown", onKeyDown);
    // Handle the icon directly so mouse clicks also work on touch-capable
    // browsers; Leaflet can suppress its delegated compatibility click.
    element.addEventListener("pointerdown", onPointerDown);
    element.addEventListener("click", onClick);
    removeElementHandlers = () => {
      element.removeEventListener("keydown", onKeyDown);
      element.removeEventListener("pointerdown", onPointerDown);
      element.removeEventListener("click", onClick);
    };
  };
  marker.on("add", prepareElement);
  marker.on("remove", () => removeElementHandlers());
  runtime.markerCleanup.push(() => removeElementHandlers());
  return marker;
}

function markSelected(marker: Marker, selected: boolean) {
  marker.getElement()?.classList.toggle(styles.selectedMarker, selected);
  marker.getElement()?.setAttribute("aria-pressed", String(selected));
  marker.setZIndexOffset(selected ? 1000 : 0);
}

/** Only public station anchors and already-aggregated group positions reach this map. */
export function MumbaiStationMap({ stations, groups, selectedStationId, selectedGroupId, onStationSelect, onGroupSelect, onClearSelection }: MumbaiStationMapProps) {
  const mapElement = useRef<HTMLDivElement>(null);
  const runtime = useRef<Runtime | null>(null);
  const callbacks = useRef({ onStationSelect, onGroupSelect });
  const descriptionId = useId();
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [tilesFailed, setTilesFailed] = useState(false);
  const [layer, setLayer] = useState<MapLayer>("stations");
  const visibleStations = useMemo(() => stations.filter(station => validPosition(station.latitude, station.longitude)), [stations]);
  const visibleGroups = useMemo(() => groups.filter((group): group is VisibleGroup => !hiddenCount(group.patient_count, group.suppressed) && !!group.centroid && validPosition(group.centroid.latitude, group.centroid.longitude)), [groups]);
  const viewData = useRef({ layer, stations: visibleStations, groups: visibleGroups, selectedStationId, selectedGroupId });

  useEffect(() => { callbacks.current = { onStationSelect, onGroupSelect }; }, [onStationSelect, onGroupSelect]);
  useEffect(() => { viewData.current = { layer, stations: visibleStations, groups: visibleGroups, selectedStationId, selectedGroupId }; }, [layer, visibleStations, visibleGroups, selectedStationId, selectedGroupId]);

  useEffect(() => {
    let active = true;
    let localRuntime: Runtime | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let resizeFrame = 0;
    const element = mapElement.current;
    if (!element) return;
    const onKeyboardPan = (event: KeyboardEvent) => {
      if (localRuntime && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) localRuntime.viewMode = "manual";
    };
    import("leaflet").then(library => {
      if (!active) return;
      const map = library.map(element, {
        attributionControl: false, scrollWheelZoom: false, minZoom: 8, maxZoom: 18, zoomControl: true,
        // Keep Fit/Reset reliable even immediately after repeated zoom clicks.
        zoomAnimation: false, markerZoomAnimation: false,
      });
      localRuntime = { library, map, stations: library.layerGroup(), groups: library.layerGroup(), stationMarkers: new Map(), groupMarkers: new Map(), markerCleanup: [], viewMode: "fit", settingView: false };
      runtime.current = localRuntime;
      map.fitBounds(MUMBAI_BOUNDS, { padding: [18, 18], animate: false });
      map.on("dragstart", () => { if (localRuntime) localRuntime.viewMode = "manual"; });
      map.on("zoomstart", () => { if (localRuntime && !localRuntime.settingView) localRuntime.viewMode = "manual"; });
      element.addEventListener("keydown", onKeyboardPan);
      library.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        referrerPolicy: "strict-origin-when-cross-origin",
        // Request the current viewport only, without off-screen tile buffering.
        keepBuffer: 0,
        updateWhenIdle: true,
      }).on("tileerror", () => { if (active) setTilesFailed(true); }).addTo(map);
      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => {
          cancelAnimationFrame(resizeFrame);
          resizeFrame = requestAnimationFrame(() => {
            if (!active || !localRuntime || !element.clientWidth || !element.clientHeight) return;
            // Keep the geographic centre when layout changes. Refit automatic
            // views to the new size, while leaving a user's pan/zoom intact.
            map.invalidateSize({ pan: true, animate: false });
            const view = viewData.current;
            if (localRuntime.viewMode === "fit") fitLocations(localRuntime, view.layer, view.stations, view.groups);
            else if (localRuntime.viewMode === "selection") fitSelection(localRuntime, view.layer, view.selectedStationId, view.selectedGroupId, view.groups);
            else if (localRuntime.viewMode === "mumbai") resetView(localRuntime);
          });
        });
        resizeObserver.observe(element);
      }
      setStatus("ready");
    }).catch(() => {
      if (!active) return;
      cancelAnimationFrame(resizeFrame);
      resizeObserver?.disconnect();
      element.removeEventListener("keydown", onKeyboardPan);
      localRuntime?.map.remove();
      localRuntime = null;
      runtime.current = null;
      setStatus("failed");
    });
    return () => {
      active = false;
      cancelAnimationFrame(resizeFrame);
      resizeObserver?.disconnect();
      element.removeEventListener("keydown", onKeyboardPan);
      localRuntime?.markerCleanup.forEach(cleanup => cleanup());
      localRuntime?.map.remove();
      if (runtime.current === localRuntime) runtime.current = null;
    };
  }, []);

  useEffect(() => {
    const current = runtime.current;
    if (status !== "ready" || !current) return;
    current.markerCleanup.forEach(cleanup => cleanup());
    current.markerCleanup = [];
    current.stationMarkers.forEach(marker => { marker.closeTooltip(); marker.off(); });
    current.groupMarkers.forEach(marker => { marker.closeTooltip(); marker.off(); });
    current.stations.clearLayers(); current.groups.clearLayers();
    current.stationMarkers.clear(); current.groupMarkers.clear();
    visibleStations.forEach(station => {
      const hidden = hiddenCount(station.patient_count, station.suppressed);
      const label = `Select ${station.station_name}: ${hidden ? "small count hidden" : `${number.format(station.patient_count!)} recorded patients`}`;
      const marker = makeMarker(current, [station.latitude, station.longitude], label, hidden ? "—" : shortNumber.format(station.patient_count!), stationColor({ ...station, suppressed: Boolean(hidden) }), () => callbacks.current.onStationSelect(station.station_id));
      marker.addTo(current.stations);
      current.stationMarkers.set(station.station_id, marker);
    });
    visibleGroups.forEach(group => {
      const color = groupColor(group.cluster);
      const bounds = groupBounds(group);
      if (bounds) current.library.rectangle(bounds, { color, weight: 1.5, dashArray: "5 5", fillOpacity: .1, interactive: false }).addTo(current.groups);
      const marker = makeMarker(current, [roundCoordinate(group.centroid.latitude), roundCoordinate(group.centroid.longitude)], `Select nearby group ${group.cluster + 1}: ${number.format(group.patient_count)} recorded patients`, `G${group.cluster + 1}`, color, () => callbacks.current.onGroupSelect(group.cluster), true);
      marker.addTo(current.groups);
      current.groupMarkers.set(group.cluster, marker);
    });
  }, [status, visibleStations, visibleGroups]);

  useEffect(() => {
    if (selectedGroupId != null) setLayer("groups");
    else if (selectedStationId != null) setLayer("stations");
  }, [selectedStationId, selectedGroupId]);

  useEffect(() => {
    const current = runtime.current;
    if (status !== "ready" || !current) return;
    current.map.removeLayer(layer === "stations" ? current.groups : current.stations);
    current.map.addLayer(layer === "stations" ? current.stations : current.groups);
    fitLocations(current, layer, visibleStations, visibleGroups);
  }, [status, layer, visibleStations, visibleGroups]);

  useEffect(() => {
    const current = runtime.current;
    if (status !== "ready" || !current) return;
    current.stationMarkers.forEach((marker, id) => markSelected(marker, id === selectedStationId));
    current.groupMarkers.forEach((marker, id) => markSelected(marker, id === selectedGroupId));
    fitSelection(current, layer, selectedStationId, selectedGroupId, visibleGroups);
  }, [status, layer, selectedStationId, selectedGroupId, visibleStations, visibleGroups]);

  function fitVisible() { if (runtime.current) fitLocations(runtime.current, layer, visibleStations, visibleGroups); }
  function resetMumbai() { if (runtime.current) resetView(runtime.current); }
  function changeLayer(next: MapLayer) { if (next !== layer) { onClearSelection?.(); setLayer(next); } }

  return <div className={styles.wrapper} data-testid="mumbai-station-map">
    <div className={styles.toolbar}>
      <div className={styles.layers} role="group" aria-label="Map layer">
        <button type="button" aria-pressed={layer === "stations"} onClick={() => changeLayer("stations")}><MapPin size={14} aria-hidden="true"/>Stations</button>
        <button type="button" aria-pressed={layer === "groups"} onClick={() => changeLayer("groups")}><Layers size={14} aria-hidden="true"/>Nearby groups</button>
      </div>
      <div className={styles.viewControls}>
        <button type="button" onClick={fitVisible} disabled={status !== "ready"} aria-label="Fit visible locations" title="Fit visible locations"><Expand size={15} aria-hidden="true"/><span>Fit view</span></button>
        <button type="button" onClick={resetMumbai} disabled={status !== "ready"} aria-label="Reset Mumbai view" title="Reset Mumbai view"><RotateCcw size={14} aria-hidden="true"/><span>Reset</span></button>
      </div>
    </div>
    <div className={styles.frame}>
      <div ref={mapElement} className={styles.map} role="region" aria-label="Interactive Mumbai station map" aria-describedby={descriptionId}/>
      {status === "loading" && <div className={styles.overlay} role="status"><LoaderCircle className="spin" size={18} aria-hidden="true"/>Loading the Mumbai map…</div>}
      {status === "failed" && <div className={styles.overlay} role="status"><AlertCircle size={20} aria-hidden="true"/><p>The interactive map could not load. Use the station list and area details below.</p></div>}
      <div className={styles.attribution}>© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a></div>
    </div>
    {tilesFailed && status === "ready" && <p className={styles.tileStatus} role="status"><AlertCircle size={14} aria-hidden="true"/>Map tiles could not load. Station markers and area details are still available.</p>}
    {status === "ready" && !(layer === "stations" ? visibleStations.length : visibleGroups.length) && <p className={styles.emptyStatus} role="status">{layer === "stations" ? "No station locations match this selection. Showing Mumbai." : "No nearby groups have locations that can be shown for this selection."}</p>}
    <p className={styles.instructions} id={descriptionId}>{layer === "stations" ? "Select a station for details. Marker numbers show recorded patients." : "Select a group for details. Shaded bounds show approximate grouped areas."} Drag to pan; use + and − to zoom. Keyboard: Tab to a marker, then Enter or Space.</p>
  </div>;
}
