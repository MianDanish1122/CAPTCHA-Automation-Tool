'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { StatsSummary } from '@/lib/types';
import { Download, RefreshCw } from 'lucide-react';

const STEPS = [
  { n: 1, title: 'Dashboard overview', href: '/evaluation', hint: 'This page: live metrics from stored data' },
  { n: 2, title: 'Inspect website', href: '/inspector', hint: 'Crawl an authorized site, find contact pages' },
  { n: 3, title: 'Review discovered pages', href: '/scans', hint: 'Pages, forms, screenshots, evidence' },
  { n: 4, title: 'CAPTCHA classifications', href: '/results', hint: 'Provider, challenge type, handling' },
  { n: 5, title: 'Run OCR evaluation', href: '/ocr', hint: 'Synthetic CAPTCHAs, labelled benchmark' },
  { n: 6, title: 'Verification results', href: '/verification', hint: 'Provider vs. test-key vs. simulated' },
  { n: 7, title: 'Human-review cases', href: '/reviews', hint: 'Real protected challenges go to a person' },
  { n: 8, title: 'Generate report', href: '/reports', hint: 'Download evaluation report / CSV' },
];

function Metric({ label, value, denom }: { label: string; value: React.ReactNode; denom: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold text-slate-900 mt-1">{value}</div>
      <div className="text-[11px] text-slate-500 mt-1 leading-snug">Denominator: {denom}</div>
    </div>
  );
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? 'n/a' : `${v}%`);

export default function EvaluationPage() {
  const [days, setDays] = useState<number | undefined>(undefined);
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStats(await api.getStatsSummary(days));
    } catch (e: any) {
      setError(e?.message || 'Could not load metrics');
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const download = async () => {
    setDownloading(true);
    try {
      await api.downloadEvaluationReport(days);
    } catch (e: any) {
      setError(e?.message || 'Report download failed');
    } finally {
      setDownloading(false);
    }
  };

  const range = stats
    ? stats.time_range.all_time
      ? 'all recorded data'
      : `last ${stats.time_range.days} days (since ${new Date(stats.time_range.since as string).toLocaleDateString()})`
    : '';

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 text-white rounded-2xl p-6 border border-slate-800">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">Evaluation Dashboard</h1>
        <p className="text-sm text-slate-300 mt-1 max-w-3xl">
          Every number below is computed from records stored in the database. Each block states its
          denominator and time range; with no data it shows zeros, never placeholder values.
        </p>
      </div>

      <ol className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3" aria-label="Evaluator workflow">
        {STEPS.map((s) => (
          <li key={s.n}>
            <Link href={s.href} className="block bg-white border border-slate-200 hover:border-blue-400 rounded-xl p-3 h-full">
              <div className="text-xs font-bold text-blue-600">STEP {s.n}</div>
              <div className="text-sm font-semibold text-slate-900">{s.title}</div>
              <div className="text-[11px] text-slate-500">{s.hint}</div>
            </Link>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs font-semibold text-slate-600">
          Time range{' '}
          <select
            value={days ?? ''}
            onChange={(e) => setDays(e.target.value ? Number(e.target.value) : undefined)}
            className="border border-slate-300 rounded-lg px-2 py-1 text-sm font-normal"
          >
            <option value="">All time</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </select>
        </label>
        <button onClick={load} className="inline-flex items-center gap-1 text-sm text-slate-700 border border-slate-300 rounded-lg px-3 py-1.5 hover:bg-slate-50">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
        <button
          onClick={download}
          disabled={downloading}
          className="inline-flex items-center gap-1 text-sm bg-slate-900 text-white rounded-lg px-3 py-1.5 hover:bg-slate-700 disabled:opacity-50"
        >
          <Download className="w-3.5 h-3.5" /> Download evaluation report
        </button>
        {stats && <span className="text-xs text-slate-500">Showing: {range}</span>}
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      {stats && !stats.has_data && (
        <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg p-3">
          No inspections, OCR evaluations or verification attempts have been recorded yet. Run the workflow above to
          populate these metrics.
        </p>
      )}

      {stats && (
        <>
          <section>
            <h2 className="font-semibold text-slate-900 mb-2">Inspections &amp; pages</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <Metric label="URL scans" value={stats.inspections.url_scans_total} denom={stats.inspections.denominator} />
              <Metric label="Pages inspected" value={stats.pages.pages_inspected} denom={stats.pages.denominator} />
              <Metric
                label="Pages with a CAPTCHA"
                value={`${stats.pages.pages_with_captcha} (${pct(stats.pages.pages_with_captcha_pct)})`}
                denom={`${stats.pages.pages_inspected} pages inspected`}
              />
              <Metric
                label="Failed scans"
                value={`${stats.failures.failed_scans} (${pct(stats.failures.failed_scans_pct)})`}
                denom={stats.failures.denominator}
              />
            </div>
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-4">
            <h2 className="font-semibold text-slate-900">CAPTCHA types detected</h2>
            <p className="text-[11px] text-slate-500 mb-2">Denominator: {stats.captcha_types.denominator}</p>
            {Object.keys(stats.captcha_types.by_provider).length === 0 ? (
              <p className="text-sm text-slate-500">None recorded.</p>
            ) : (
              <ul className="space-y-1.5">
                {Object.entries(stats.captcha_types.by_provider).map(([k, v]) => (
                  <li key={k} className="flex items-center gap-3 text-sm">
                    <span className="w-44 font-mono text-slate-700">{k}</span>
                    <span className="flex-1 bg-slate-100 rounded h-2">
                      <span className="block bg-blue-500 h-2 rounded" style={{ width: `${stats.captcha_types.share_pct[k] ?? 0}%` }} />
                    </span>
                    <span className="w-28 text-right text-slate-600">{v} ({pct(stats.captcha_types.share_pct[k])})</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-4">
            <h2 className="font-semibold text-slate-900">OCR evaluation</h2>
            <p className="text-[11px] text-slate-500 mb-3">Denominator: {stats.ocr.denominator}</p>
            <div className="grid sm:grid-cols-4 gap-3 mb-4">
              <Metric label="Labelled evaluations" value={stats.ocr.evaluations} denom="OCR runs with a known true label" />
              <Metric label="Exact match" value={pct(stats.ocr.exact_match_pct)} denom={`${stats.ocr.evaluations} labelled evaluations`} />
              <Metric label="Mean character accuracy" value={pct(stats.ocr.mean_char_accuracy_pct)} denom={`${stats.ocr.evaluations} labelled evaluations`} />
              <Metric label="Mean latency" value={stats.ocr.mean_latency_ms === null ? 'n/a' : `${stats.ocr.mean_latency_ms} ms`} denom={`${stats.ocr.evaluations} labelled evaluations`} />
            </div>
            <h3 className="text-sm font-semibold text-slate-800">Held-out benchmark (latest per engine)</h3>
            <p className="text-[11px] text-slate-500 mb-2">{stats.ocr.heldout_benchmarks.denominator}</p>
            {Object.keys(stats.ocr.heldout_benchmarks.by_engine).length === 0 ? (
              <p className="text-sm text-slate-500">
                No held-out results imported. Run <code>python -m scripts.ocr_benchmark evaluate</code> then <code>import-results</code>.
              </p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 border-b">
                    <th className="py-1">Engine</th><th>Samples</th><th>Exact match</th><th>Char accuracy</th><th>Mean latency</th><th>Failures</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.values(stats.ocr.heldout_benchmarks.by_engine).map((r) => (
                    <tr key={r.engine} className="border-b border-slate-100">
                      <td className="py-1 font-mono">{r.engine}</td>
                      <td>{r.samples}</td>
                      <td>{r.exact_matches}/{r.samples} ({r.exact_match_pct}%)</td>
                      <td>{r.char_accuracy_pct}%</td>
                      <td>{r.latency_ms_mean} ms</td>
                      <td>{r.failures}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-4">
            <h2 className="font-semibold text-slate-900">Verification outcomes by scenario</h2>
            <p className="text-[11px] text-slate-500 mb-2">Denominator: {stats.verification.denominator}</p>
            <div className="grid sm:grid-cols-3 gap-3 mb-3">
              <Metric label="Attempts" value={stats.verification.attempts} denom="all recorded verification attempts" />
              <Metric label="Confirmed by a provider" value={stats.verification.provider_confirmed} denom={`${stats.verification.attempts} attempts`} />
              <Metric label="Simulated (no provider call)" value={stats.verification.simulated_attempts} denom={`${stats.verification.attempts} attempts`} />
            </div>
            {Object.keys(stats.verification.by_mode_and_outcome).length === 0 ? (
              <p className="text-sm text-slate-500">No attempts recorded.</p>
            ) : (
              <ul className="text-xs space-y-1">
                {Object.entries(stats.verification.by_mode_and_outcome).map(([mode, outs]) => (
                  <li key={mode}>
                    <span className="font-mono font-semibold">{mode}</span>:{' '}
                    {Object.entries(outs).map(([o, n]) => `${o} × ${n}`).join(', ')}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] text-slate-500 mt-2">{stats.verification.note}</p>
          </section>

          <section className="grid md:grid-cols-2 gap-3">
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <h2 className="font-semibold text-slate-900">Human-review cases</h2>
              <p className="text-[11px] text-slate-500 mb-2">Denominator: {stats.human_review.denominator}</p>
              <div className="text-2xl font-bold">{stats.human_review.cases}</div>
              <div className="text-xs text-slate-600 mt-1">
                {Object.entries(stats.human_review.by_status).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'none'}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Decisions recorded (all time): {stats.human_review.decisions_recorded}</div>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <h2 className="font-semibold text-slate-900">Most common scan errors</h2>
              <p className="text-[11px] text-slate-500 mb-2">Denominator: {stats.failures.denominator}</p>
              {stats.failures.top_errors.length === 0 ? (
                <p className="text-sm text-slate-500">None recorded.</p>
              ) : (
                <ul className="text-xs space-y-1">
                  {stats.failures.top_errors.map((e, i) => (
                    <li key={i}><b>{e.count}×</b> {e.message}</li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
