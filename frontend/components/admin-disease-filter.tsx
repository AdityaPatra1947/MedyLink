"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import styles from "./admin-ml.module.css";

export function DiseaseFilter({ options, selected, onChange }: {
  options: { disease_code: string; label: string }[];
  selected: string[];
  onChange: (codes: string[]) => void;
}) {
  const id = useId();
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false), [search, setSearch] = useState("");
  useEffect(() => {
    if (!open) return;
    searchInput.current?.focus();
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);
  const matches = options.filter(option => `${option.label} ${option.disease_code}`.toLowerCase().includes(search.trim().toLowerCase()));
  function toggle(code: string) { onChange(selected.includes(code) ? selected.filter(item => item !== code) : [...selected, code]); }
  return <div ref={container} className={styles.diseaseFilter} onKeyDown={event => { if (event.key === "Escape" && open) { event.preventDefault(); setOpen(false); trigger.current?.focus(); } }}>
    <span id={`${id}-label`} className={styles.filterLabel}>Conditions</span>
    <button ref={trigger} type="button" className={styles.filterToggle} aria-labelledby={`${id}-label ${id}-value`} aria-expanded={open} aria-controls={`${id}-options`} onClick={() => setOpen(value => !value)}><span id={`${id}-value`}>{selected.length ? `${selected.length} selected` : "All conditions"}</span><ChevronDown size={16} aria-hidden="true"/></button>
    {open && <div className={styles.filterOptions} id={`${id}-options`}><label className={styles.searchField}><Search size={16} aria-hidden="true"/><input ref={searchInput} aria-label="Search conditions" placeholder="Search a condition…" value={search} onChange={event => setSearch(event.target.value)}/></label><div className={styles.optionList} role="group" aria-label="Select conditions">{matches.map(option => <label key={option.disease_code}><input type="checkbox" checked={selected.includes(option.disease_code)} onChange={() => toggle(option.disease_code)}/><span>{option.label}</span></label>)}{!matches.length && <p>No matching conditions.</p>}</div><div className={styles.optionFooter}><button type="button" onClick={() => { onChange([]); setSearch(""); }}>Clear conditions</button><button type="button" onClick={() => { setOpen(false); trigger.current?.focus(); }}>Done</button></div></div>}
    {!!selected.length && <div className={styles.chips}>{selected.map(code => { const label = options.find(option => option.disease_code === code)?.label || code; return <button type="button" key={code} onClick={() => toggle(code)} aria-label={`Remove ${label}`}>{label}<X size={12}/></button>; })}{!open && <button type="button" onClick={() => onChange([])}>Clear conditions</button>}</div>}
  </div>;
}
