"use client";

import { useMemo, useRef, useState, type CSSProperties } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight, Layers3, MapPin, Search, ShieldCheck, TrainFront, UsersRound, X } from "lucide-react";
import type { AnalyticsCluster } from "@/lib/analytics-types";
import type { MLCatalog, MLInsights } from "@/lib/ml-types";
import { groupColor, RAIL_COLORS, type MappedStation } from "@/lib/mumbai-map";
import { MumbaiStationMap } from "./mumbai-station-map";
import styles from "./admin-geography.module.css";

const format = (value: number | null | undefined) => value == null ? "Unavailable" : value.toLocaleString("en-IN");
const patientCount = (value: number | null | undefined, suppressed = false, threshold = 5) =>
  suppressed || value == null || !Number.isFinite(value) || value < 0 || (value > 0 && value < threshold) ? null : value;
const countLabel = (value: number | null) => value == null ? "Hidden" : format(value);
const validLocation = (value: { latitude: number; longitude: number } | null | undefined) => !!value && Number.isFinite(value.latitude) && Number.isFinite(value.longitude) && Math.abs(value.latitude) <= 90 && Math.abs(value.longitude) <= 180;
const groupTitle = (group: AnalyticsCluster) => {
  const names = group.stations.filter(station => !station.suppressed && station.patient_count != null).map(station => station.station_name);
  const unique = [...new Set(names)];
  return unique.length ? `${unique.slice(0, 2).join(" · ")}${unique.length > 2 ? ` + ${unique.length - 2} more ${unique.length === 3 ? "area" : "areas"}` : ""}` : "Nearby station areas";
};

function RailBadges({ lines }: { lines: string[] }) {
  return <div className={styles.railBadges}>{lines.map(line => <span key={line}><i style={{ background: RAIL_COLORS[line] || RAIL_COLORS.Interchange }} aria-hidden="true"/>{line}</span>)}</div>;
}

export function AdminGeography({ data, catalog }: { data: MLInsights; catalog: MLCatalog }) {
  return <GeographyWorkspace key={JSON.stringify(data.filters)} data={data} catalog={catalog}/>;
}

function GeographyWorkspace({ data, catalog }: { data: MLInsights; catalog: MLCatalog }) {
  const mapArea = useRef<HTMLDivElement>(null);
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("patients");
  const [page, setPage] = useState(0);
  const threshold = Math.max(5, catalog.suppression_threshold || 5);
  const stations = useMemo<MappedStation[]>(() => data.summary.stations.map(row => {
    const anchor = catalog.stations.find(station => station.station_id === row.station_id);
    const count = patientCount(row.patient_count, row.suppressed, threshold);
    return { ...row, latitude: anchor?.latitude ?? NaN, longitude: anchor?.longitude ?? NaN, lines: anchor?.lines || [], patient_count: count, suppressed: count == null };
  }), [catalog.stations, data.summary.stations, threshold]);
  const mappedStations = useMemo(() => stations.filter(validLocation), [stations]);
  const groups = useMemo(() => (data.hotspots?.clusters || []).map(group => {
    const count = patientCount(group.patient_count, group.suppressed, threshold);
    return {
      ...group, patient_count: count, suppressed: count == null,
      centroid: count == null ? null : group.centroid,
      bounds: count == null ? null : group.bounds,
      stations: count == null ? [] : group.stations.map(station => {
        const count = patientCount(station.patient_count, station.suppressed, threshold);
        return { ...station, patient_count: count, suppressed: count == null };
      }),
    };
  }), [data.hotspots?.clusters, threshold]);
  const mappedGroups = useMemo(() => groups.filter(group => !group.suppressed && validLocation(group.centroid)), [groups]);
  const selectedStation = stations.find(station => station.station_id === selectedStationId);
  const selectedGroup = mappedGroups.find(group => group.cluster === selectedGroupId);
  const stationConditions = (station: MappedStation) => (data.summary.station_disease_counts?.find(row => row.station_id === station.station_id)?.diseases || []).map(condition => ({
    ...condition, count: patientCount(condition.count, station.suppressed, threshold),
  }));
  function selectStation(id: string) { setSelectedStationId(id); setSelectedGroupId(null); }
  function selectGroup(id: number) { setSelectedGroupId(id); setSelectedStationId(null); }
  function clearSelection() { setSelectedStationId(null); setSelectedGroupId(null); }
  function scrollToMap() { mapArea.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); }
  function showStation(id: string) { selectStation(id); scrollToMap(); }
  function showGroup(id: number) { selectGroup(id); scrollToMap(); }
  const stationRows = stations.filter(station => `${station.station_name} ${station.lines.join(" ")}`.toLowerCase().includes(search.trim().toLowerCase())).sort((a, b) => sort === "name" ? a.station_name.localeCompare(b.station_name) : (b.patient_count ?? -1) - (a.patient_count ?? -1) || a.station_name.localeCompare(b.station_name));
  const pageSize = 8, lastPage = Math.max(0, Math.ceil(stationRows.length / pageSize) - 1), currentPage = Math.min(page, lastPage);
  const displayedStations = stationRows.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const visibleConditions = selectedStation ? stationConditions(selectedStation) : [];
  const maxConditionCount = Math.max(1, ...visibleConditions.map(condition => condition.count || 0));
  const groupCards = (items: AnalyticsCluster[]) => items.map(group => <article key={group.cluster} data-testid={`nearby-group-${group.cluster}`} className={`${styles.groupCard} ${selectedGroup?.cluster === group.cluster ? styles.activeGroup : ""}`} style={{ "--group-color": group.suppressed ? "#89978e" : groupColor(group.cluster) } as CSSProperties}>
    <div className={styles.groupTop}><span className={styles.groupReference}><i aria-hidden="true"/>Group {group.cluster + 1}</span><strong>{countLabel(group.patient_count)}<small>{group.suppressed ? "small count" : "patients"}</small></strong></div>
    <h4>{group.suppressed ? "Small group hidden" : groupTitle(group)}</h4>
    {group.suppressed ? <p>This group and its location breakdown are hidden because it is too small.</p> : <><p>Nearby recorded cases in the selected history.</p><div className={styles.stationChips}>{group.stations.filter(station => !station.suppressed && station.patient_count != null).map(station => <button type="button" key={station.station_id} aria-label={`View ${station.station_name} station details`} onClick={() => showStation(station.station_id)}>{station.station_name}<span>{countLabel(station.patient_count)}</span></button>)}</div><button type="button" className={styles.mapButton} data-testid={`select-group-${group.cluster}`} disabled={!validLocation(group.centroid)} aria-pressed={selectedGroup?.cluster === group.cluster} aria-label={`Show group ${group.cluster + 1} near ${groupTitle(group)} on map`} onClick={() => showGroup(group.cluster)}><MapPin size={14}/>{selectedGroup?.cluster === group.cluster ? "Shown on map" : "Show on map"}<ArrowUpRight size={13}/></button></>}
  </article>);

  return <section className={styles.panel} data-testid="admin-geography" aria-labelledby="geography-heading">
    <header className={styles.heading}><span className={styles.headingIcon}><MapPin size={23}/></span><div><span className={styles.eyebrow}>Explore Mumbai</span><h2 id="geography-heading">Where recorded conditions are concentrated</h2><p>Explore station areas and nearby patient groups in your current selection.</p></div></header>
    <div className={styles.overview} aria-label="Geography overview">
      <div><UsersRound size={18}/><span>Patients in selection</span><strong>{countLabel(patientCount(data.summary.patients, false, threshold))}</strong></div>
      <div><TrainFront size={18}/><span>Mapped station areas</span><strong>{format(mappedStations.length)}</strong></div>
      <div><Layers3 size={18}/><span>Nearby groups</span><strong>{format(data.hotspots?.counts?.cluster_count)}</strong></div>
      <div><MapPin size={18}/><span>Outside nearby groups</span><strong>{data.hotspots?.counts ? countLabel(patientCount(data.hotspots.counts.noise_patients, false, threshold)) : "Unavailable"}</strong></div>
    </div>
    <div className={styles.mapLayout}>
      <div className={styles.mapArea} ref={mapArea}><MumbaiStationMap stations={mappedStations} groups={mappedGroups} selectedStationId={selectedStation?.station_id || null} selectedGroupId={selectedGroup?.cluster ?? null} onStationSelect={selectStation} onGroupSelect={selectGroup} onClearSelection={clearSelection}/><div className={styles.railLegend} aria-label="Station rail line colours"><strong>Station colours</strong>{Object.entries(RAIL_COLORS).map(([line, colour]) => <span key={line}><i style={{ background: colour }} aria-hidden="true"/>{line}</span>)}<span><i style={{ background: "#96a39b" }} aria-hidden="true"/>Hidden count</span></div><p className={styles.mapCaption}><ShieldCheck size={14}/>Public station locations represent simulated areas. No home addresses or individual patients are mapped.</p></div>
      <aside className={styles.selection} data-testid="selected-station" aria-label="Selected map location">
        {selectedStation || selectedGroup ? <>
          <div className={styles.selectionHead}><span className={styles.eyebrow}>{selectedStation ? "Station details" : "Nearby group details"}</span><button type="button" aria-label="Clear map selection" onClick={clearSelection}><X size={16}/></button></div>
          <h3>{selectedStation?.station_name || groupTitle(selectedGroup!)}</h3>
          {selectedStation ? <>
            <RailBadges lines={selectedStation.lines}/>
            <div className={styles.selectionCount}><strong>{countLabel(selectedStation.patient_count)}</strong><span>patients at this station area</span></div>
            <h4>Recorded conditions at this station</h4>
            <p className={styles.scope}>The full station selection, using the conditions and dates applied above.</p>
            {visibleConditions.length ? <div className={styles.conditionBars}>{visibleConditions.map(condition => <div key={condition.code}><div><span>{condition.label}</span><strong>{countLabel(condition.count)}</strong></div><div className={styles.track} aria-hidden="true">{condition.count != null && <i style={{ width: `${condition.count / maxConditionCount * 100}%` }}/>}</div></div>)}</div> : <p className={styles.scope}>A condition breakdown is unavailable for this station.</p>}
            <p className={styles.smallNote}>A patient can have more than one condition. Hidden values are not zero.</p>
          </> : <>
            <p className={styles.scope}>Group {selectedGroup!.cluster + 1} · grouped by nearby recorded locations.</p>
            <div className={styles.selectionCount}><strong>{countLabel(selectedGroup!.patient_count)}</strong><span>patients in this group</span></div>
            <h4>Stations represented in this group</h4>
            <div className={styles.groupStations}>{selectedGroup!.stations.filter(station => !station.suppressed && station.patient_count != null).map(station => <button type="button" key={station.station_id} aria-label={`View ${station.station_name} station details`} onClick={() => showStation(station.station_id)}><span>{station.station_name}</span><strong>{countLabel(station.patient_count)}</strong><ChevronRight size={14}/></button>)}</div>
            <p className={styles.smallNote}>These counts belong to this group. Select a station to see its full filtered condition breakdown; it may include patients outside this group.</p>
          </>}
        </> : <div className={styles.selectionEmpty}><span><MapPin size={24}/></span><h3>Choose a station</h3><p>Select a marker or a station below to see its patient count and recorded conditions.</p><div><Layers3 size={16}/><p>Switch to nearby groups to explore geographic patterns.</p></div></div>}
      </aside>
    </div>

    <section className={styles.section} aria-labelledby="geography-groups-heading"><div className={styles.sectionHead}><div><h3 id="geography-groups-heading">Nearby patient groups</h3><p>Station names identify each area. Group numbers are references, not a ranking of health or risk.</p></div><span className={styles.method}>DBSCAN</span></div>
      {groups.length ? <><div className={styles.groupGrid}>{groupCards(groups.slice(0, 6))}</div>{groups.length > 6 && <details className={styles.moreGroups}><summary>Show remaining {groups.length - 6} groups</summary><div className={styles.groupGrid}>{groupCards(groups.slice(6))}</div></details>}</> : <div className={styles.empty}><Layers3 size={21}/><p>{data.hotspots?.reason || "No dense geographic groups were found for this selection."}</p></div>}
    </section>

    <section className={styles.section} aria-labelledby="geography-stations-heading"><div className={styles.sectionHead}><div><h3 id="geography-stations-heading">Conditions by station area</h3><p>All station counts below follow the filters applied above.</p></div><span className={styles.stationTotal}>{stations.length} station areas</span></div>
      <div className={styles.directoryTools}><label className={styles.search}><Search size={16}/><input aria-label="Search station areas" type="search" placeholder="Find a station or rail line" value={search} onChange={event => { setSearch(event.target.value); setPage(0); }}/></label><label className={styles.sort}>Sort station areas<select value={sort} onChange={event => { setSort(event.target.value); setPage(0); }}><option value="patients">Most patients</option><option value="name">Station name</option></select></label></div>
      {displayedStations.length ? <><div className={styles.tableWrap}><table><thead><tr><th scope="col">Station area</th><th scope="col">Patients</th><th scope="col">Recorded conditions</th><th scope="col"><span className={styles.srOnly}>Station details</span></th></tr></thead><tbody>{displayedStations.map(station => {
        const conditions = stationConditions(station);
        return <tr key={station.station_id} className={selectedStation?.station_id === station.station_id ? styles.selectedRow : undefined}><th scope="row"><button type="button" onClick={() => showStation(station.station_id)} aria-label={`View ${station.station_name} station details`}>{station.station_name}</button><RailBadges lines={station.lines}/></th><td className={styles.patientCell}>{countLabel(station.patient_count)}</td><td><span>{conditions.length ? conditions.map(condition => `${condition.label}: ${countLabel(condition.count)}`).join(" · ") : "Unavailable"}</span></td><td><button type="button" className={styles.rowAction} aria-label={`Show ${station.station_name} on map`} onClick={() => showStation(station.station_id)}><ArrowUpRight size={16}/></button></td></tr>;
      })}</tbody></table></div><div className={styles.pagination}><p>{currentPage * pageSize + 1}–{Math.min((currentPage + 1) * pageSize, stationRows.length)} of {stationRows.length} station areas</p><div><button type="button" aria-label="Previous station page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={15}/></button><span>Page {currentPage + 1} of {lastPage + 1}</span><button type="button" aria-label="Next station page" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}><ChevronRight size={15}/></button></div></div></> : <div className={styles.empty}><Search size={20}/><p>No station areas match this search.</p></div>}
      <p className={styles.smallNote}>Counts of 1–{threshold - 1} are hidden; 0 means no recorded cases. Patients may have more than one condition, so condition counts should not be added together.</p>
    </section>
    <details className={styles.methodDetails}><summary>About these geographic groups</summary><p>DBSCAN groups nearby recorded observations. Counts describe the selected records, not disease rates or confirmed outbreaks. Patients outside dense groups are still part of the selected records.</p><p>Selected patients without usable coordinates: {countLabel(patientCount(data.hotspots?.counts?.missing_coordinates, false, threshold))}.</p>{data.hotspots?.notes?.map((note, index) => <p key={index}>{note}</p>)}</details>
  </section>;
}
