import { dateTime } from "@/lib/api";
import type { HealthScore } from "@/lib/patient-dashboard-types";
import styles from "./patient-dashboard.module.css";

function number(value: number) { return Number(value.toFixed(2)).toString(); }

export function HealthScoreDetails({ score }: { score: HealthScore }) {
  const weight = score.components.reduce((total, item) => total + item.weight, 0);
  return <>
    <div className={styles.calculationResult}><strong>{score.value}<small>/ 100</small></strong><span>{score.label}</span></div>
    <p>{score.method}</p>
    {score.disclaimer && <p className="notice info">{score.disclaimer}</p>}
    <section className={styles.calculation} aria-label="Health score calculation">
      <h3>How your score is calculated</h3>
      <p>{score.explanation || "Each available component is scored, multiplied by its weight, and divided by the total weight."}</p>
      <p className={styles.formula}>{score.formula || "Score = Σ(component score × weight) ÷ Σ(weights)"}</p>
      {weight > 0 && <p className={styles.formula}>round(({score.components.map(item => `${number(item.score)} × ${number(item.weight)}`).join(" + ")}) ÷ {number(weight)}) = {score.value}</p>}
    </section>
    <div className={styles.componentList}>{score.components.map(item => <article key={item.key} className={styles.component}>
      <h3>{item.label}</h3>
      <dl><div><dt>Recorded value</dt><dd>{number(item.value)}{item.unit ? ` ${item.unit}` : ""}</dd></div><div><dt>Component score</dt><dd>{number(item.score)} / 100</dd></div><div><dt>Weight</dt><dd>{number(item.weight)}{weight > 0 ? ` (${number(item.weight / weight * 100)}%)` : ""}</dd></div></dl>
      {item.formula && <p className={styles.formula}>{item.formula}</p>}
      {item.explanation && <p>{item.explanation}</p>}
      {item.measured_at && <p className="progress-note">Measured {dateTime(item.measured_at)}</p>}
      {item.source_report_id && <a href={`/api/v1/reports/${item.source_report_id}/view/`} target="_blank" rel="noopener noreferrer">View source report{item.source_report_title ? `: ${item.source_report_title}` : ""} ↗</a>}
    </article>)}</div>
    <p className="progress-note">Calculated {dateTime(score.calculated_at)}. Values are rounded for display.</p>
  </>;
}
