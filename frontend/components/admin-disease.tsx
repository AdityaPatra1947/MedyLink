"use client";

import { useEffect, useRef, useState } from "react";
import { BarChart3, CheckCircle2, ChevronDown, Fingerprint, FlaskConical, Layers3, LoaderCircle, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { api, date, message, post } from "@/lib/api";
import type { MLDiseaseInsights, MLDiseaseReport, MLFilters, MLRun } from "@/lib/ml-types";
import styles from "./admin-disease.module.css";

const base = "/admin/analytics/ml";
const number = (value: number | null | undefined) => value == null ? "Hidden / unavailable" : value.toLocaleString("en-IN");
const percent = (value: number | null | undefined) => value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
const active = (run: MLRun<MLDiseaseReport> | null | undefined) => !!run && ["queued", "running"].includes(run.status);
const explanations: Record<string, string> = {
  logistic_regression: "Finds simple patterns, like a scoring checklist.",
  decision_tree: "Asks yes/no questions step by step.",
  random_forest: "Many decision trees voting together.",
  knn: "Looks at the most similar past patients.",
  k_nearest_neighbors: "Looks at the most similar past patients.",
};

export function DiseasePrediction({ data, filters, dirty, fallbackPatients, selectedConditions = [], onRefresh }: {
  data: MLDiseaseInsights | undefined;
  filters: MLFilters;
  dirty: boolean;
  fallbackPatients: number | null;
  selectedConditions?: string[];
  onRefresh: () => void;
}) {
  const [localRun, setLocalRun] = useState<MLRun<MLDiseaseReport> | null>(null);
  const [submitting, setSubmitting] = useState(false), [error, setError] = useState("");
  const alive = useRef(true), refresh = useRef(onRefresh);
  useEffect(() => { refresh.current = onRefresh; }, [onRefresh]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const training = localRun && (!data?.training || localRun.created_at >= data.training.created_at) ? localRun : data?.training;
  const trainingId = active(training) ? training!.id : null;
  useEffect(() => {
    if (!trainingId) return;
    let current = true, timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const run = await api<MLRun<MLDiseaseReport>>(`${base}/runs/${encodeURIComponent(trainingId!)}/`);
        if (!current) return;
        setLocalRun(run); setError("");
        if (!active(run)) { refresh.current(); return; }
      } catch (failure) { if (current) setError(`Could not check training progress. ${message(failure)} Retrying automatically.`); }
      if (current) timer = setTimeout(poll, 3000);
    }
    timer = setTimeout(poll, 1500);
    return () => { current = false; clearTimeout(timer); };
  }, [trainingId]);

  async function retrain() {
    if (submitting || trainingId || dirty) return;
    setSubmitting(true); setError("");
    try {
      const run = await post<MLRun<MLDiseaseReport>>(`${base}/runs/`, { ...filters, task: "disease" });
      if (!alive.current) return;
      setLocalRun(run);
      if (!active(run)) refresh.current();
    } catch (failure) { if (alive.current) setError(message(failure)); }
    finally { if (alive.current) setSubmitting(false); }
  }

  const report = data?.model?.report;
  const selected = report?.models.find(model => model.id === report.selection?.model_id);
  const enabled = data?.prediction.prediction_enabled === true;
  const failed = training?.status === "failed";
  const insufficient = training?.status === "insufficient_data";
  const status = trainingId ? "Training in progress" : failed ? "Latest training failed" : insufficient ? "Not enough training data" : enabled ? "Ready for demonstration" : "More evidence needed";
  const reason = trainingId ? "Comparing four methods on the same patient records." : failed ? training?.message || training?.error : insufficient ? `${training?.report?.reason || training?.message || "The selected records do not cover enough diseases to compare the methods."}${data?.model ? " Previous model remains available." : ""}` : data?.prediction.reason || report?.selection?.message || "Train the methods to see a measured comparison.";
  const importance = [...(report?.feature_importance || [])].sort((a, b) => b.importance - a.importance).slice(0, 5);
  const maximum = Math.max(.001, ...importance.map(item => item.importance));
  const predicted = enabled ? data?.prediction.counts || [] : [];
  const most = Math.max(1, ...predicted.map(item => item.count || 0));
  const recalls = Object.entries(selected?.holdout.per_disease_recall || {});
  return <section className={styles.panel} aria-labelledby="disease-prediction-heading" data-testid="disease-prediction">
    <header className={styles.heading}>
      <div className={styles.titleGroup}><span className={styles.titleIcon}><Sparkles size={23} strokeWidth={1.6}/></span><div><span className={styles.eyebrow}>Predictive insights</span><h2 id="disease-prediction-heading">Disease prediction</h2></div></div>
      <button type="button" className="button primary small" disabled={submitting || !!trainingId || dirty || (data?.source.patients ?? fallbackPatients) === 0} onClick={() => void retrain()}>{submitting || trainingId ? <LoaderCircle size={15} className="spin"/> : <RefreshCw size={15}/>} {submitting ? "Starting disease training…" : trainingId ? "Disease training in progress" : "Retrain disease models"}</button>
    </header>
    <p className={styles.introduction}>The system learns from past patient records to guess which disease a new patient most likely has.</p>
    <div className={styles.status} role="status"><div className={styles.statusLabel}><h3>Can we trust it?</h3><span className={`${styles.statusPill} ${failed ? styles.red : trainingId || insufficient ? styles.amber : enabled ? styles.green : styles.amber}`}><i/><strong>{status}</strong></span></div><p>{reason}</p></div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {dirty && <p className={styles.caption}>Apply your filters before training.</p>}

    <section className={styles.saved} aria-labelledby="disease-saved-heading" data-testid="disease-saved-results">
      <div className={styles.scopeHead}><div><div className={styles.scopeTitle}><Layers3 size={16}/><h3 id="disease-saved-heading">Saved test results</h3><span className={styles.scopeBadge}>All 10 diseases</span></div><p>Fixed model evaluation. Exploration filters do not change these results.</p></div>{report?.training_dates?.from && <span className={styles.savedDates}>{date(report.training_dates.from)} – {date(report.training_dates.through || report.training_dates.from)}</span>}</div>
      <div className={styles.stats}>
        <div className={styles.methodStat}><span>Best method</span><strong className={styles.method}>{selected?.name || "Not trained"}</strong><small>Selected in practice tests</small></div>
        <div className={styles.accuracyStat}><span>Correct answers on the final test</span><strong>{percent(selected?.holdout.accuracy)}</strong><small>Separate synthetic test data</small></div>
        <div><span>Patients used for training</span><strong>{number(report?.split?.training_patients)}</strong><small>Learning set</small></div>
        <div><span>Separate patients used for testing</span><strong>{number(report?.split?.holdout_patients)}</strong><small>Held apart from training</small></div>
      </div>
      {selected && <p className={styles.why}><CheckCircle2 size={16}/><span>{selected.name} best balanced the diseases in practice tests. The final test did not choose the winner.</span></p>}

      <div className={styles.columns}>
        <article className={styles.chartPanel} aria-labelledby="disease-algorithms-heading"><div className={styles.chartHead}><span className={styles.chartIcon}><BarChart3 size={18}/></span><div><h3 id="disease-algorithms-heading">Algorithms compared</h3><p>Final-test accuracy · higher is better</p></div></div>
          {report?.models.length ? <div className={styles.models}>{report.models.map(model => <div key={model.id} className={`${styles.model} ${selected?.id === model.id ? styles.best : ""}`}><div className={styles.barLabel}><strong>{model.name}</strong><b>{percent(model.holdout.accuracy)}</b></div><div className={styles.track} aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(1, model.holdout.accuracy)) * 100}%` }}/></div><div className={styles.modelNote}><p>{explanations[model.id] || "Learns patterns from the recorded measurements."}</p>{selected?.id === model.id && <span className={styles.badge}><CheckCircle2 size={12}/>Best in practice tests</span>}</div></div>)}</div> : <div className={styles.empty}>No completed disease comparison yet.</div>}
        </article>
        <article className={`${styles.chartPanel} ${styles.featurePanel}`} aria-labelledby="disease-features-heading"><div className={styles.chartHead}><span className={styles.chartIcon}><Fingerprint size={18}/></span><div><h3 id="disease-features-heading">What helped the selected method?</h3><p>Top five recorded features</p></div></div>
          {importance.length ? <div className={styles.importance}>{importance.map((item, index) => <div key={item.feature} className={styles.feature}><span className={styles.rank}>{String(index + 1).padStart(2, "0")}</span><div><div className={styles.barLabel}><span>{item.label}</span><b>{item.importance > 0 ? `${(item.importance * 100).toFixed(1)} points` : "No clear contribution"}</b></div><div className={styles.track} aria-hidden="true"><i style={{ width: `${Math.max(0, item.importance) / maximum * 100}%` }}/></div></div></div>)}</div> : <div className={styles.empty}>Feature contributions appear after training.</div>}
          <p className={styles.featureCaption}>Score drop when a feature is shuffled. Larger bars mean more influence on this model, not a medical cause.</p>
        </article>
      </div>
      {report?.models.length ? <details className={styles.details}><summary><span>Evaluation details</span><ChevronDown size={16}/></summary><div className={styles.detailBody}><p className={styles.detailScope}>Saved evaluation across all 10 diseases · unchanged by current filters.</p><div className={styles.tableWrap}><table><thead><tr><th>Method</th><th>Practice accuracy</th><th>Practice balance</th><th>Final accuracy</th><th>Final balance</th></tr></thead><tbody>{report.models.map(model => <tr key={model.id}><th>{model.name}</th><td>{percent(model.cv.mean.accuracy)}</td><td>{percent(model.cv.mean.macro_f1)}</td><td>{percent(model.holdout.accuracy)}</td><td>{percent(model.holdout.macro_f1)}</td></tr>)}</tbody></table></div><p>Accuracy is the share of correct answers, with equal weight per patient. Balance is macro F1: it gives each disease equal importance.</p>{!!recalls.length && <><h3 className={styles.recallHeading}>Cases found for each disease</h3><p>Recall: recorded cases identified by the selected method in the final test.</p><div className={styles.recalls}>{recalls.map(([code, recall]) => <div key={code}><div className={styles.barLabel}><span>{report.class_labels?.find(item => item.code === code)?.label || code}</span><b>{recall == null ? "Hidden" : percent(recall)}</b></div><div className={styles.track} aria-hidden="true">{recall != null && <i style={{ width: `${Math.max(0, Math.min(1, recall)) * 100}%` }}/>}</div></div>)}</div></>}</div></details> : null}
    </section>

    <section className={styles.predictions} aria-labelledby="disease-current-heading" data-testid="disease-current-predictions"><div className={styles.scopeTitle}><Sparkles size={17}/><h3 id="disease-current-heading">Predictions for selected patients</h3><span className={styles.currentBadge}>Current selection</span></div>
      <p className={styles.predictionContext}>{selectedConditions.length ? <>Patients selected by recorded conditions: <strong>{selectedConditions.join(" or ")}</strong>. Model guesses may differ and can include any of the ten diseases.</> : <>One estimate per patient’s latest eligible record. Model guesses may differ from their recorded conditions.</>}</p>
      {predicted.length ? <div className={styles.predictionGrid}>{predicted.map(item => <div className={styles.result} key={item.code}><div className={styles.barLabel}><span>{item.label}</span><strong>{item.count == null ? "Hidden" : number(item.count)}</strong></div><div className={styles.track} aria-hidden="true"><i style={{ width: `${(item.count || 0) / most * 100}%` }}/></div></div>)}</div> : <div className={styles.predictionEmpty}><ShieldCheck size={21}/><div><strong>{enabled ? "No reportable estimates for this selection" : "Estimates are not available"}</strong><p>{data?.prediction.reason || "Estimates appear after the saved model passes its checks and enough eligible records are selected."}</p></div></div>}
      <p className={styles.caption}>Patient counts only. No individual predictions are shown; counts of 1–4 are hidden.</p>
    </section>
    <footer className={styles.disclaimer}><FlaskConical size={15}/><span>Based on simulated data, not real patients. Predictions support decisions and are not a diagnosis.</span></footer>
  </section>;
}
