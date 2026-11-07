'use client';

import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import {
  CsvImportResult,
  BatchJob,
  WebsiteInspectionItem,
  BatchEvaluation,
  ResultCategory,
} from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { EvidenceViewer } from '@/components/EvidenceViewer';
import {
  Upload,
  FileSpreadsheet,
  Play,
  RefreshCw,
  Download,
  AlertTriangle,
  Eye,
} from 'lucide-react';

const RESULT_STYLE: Record<ResultCategory, { label: string; cls: string }> = {
  match: { label: 'Match', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  mismatch: { label: 'Mismatch', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  not_detected: { label: 'Not detected', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  not_accessible: { label: 'Not accessible', cls: 'bg-slate-100 text-slate-700 border-slate-300' },
  not_verified: { label: 'Not verified', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
};

function ResultPill({ value }: { value: ResultCategory | null | undefined }) {
  if (!value) return <span className="text-slate-400">-</span>;
  const s = RESULT_STYLE[value];
  return (
    <span
      data-testid="result-pill"
      className={`inline-block px-2 py-0.5 rounded-md border text-[10px] font-semibold ${s.cls}`}
    >
      {s.label}
    </span>
  );
}

export default function BatchManagerPage() {
  const [file, setFile] = useState<File | null>(null);
  const [autoScan, setAutoScan] = useState<boolean>(false);
  const [importing, setImporting] = useState<boolean>(false);
  const [importResult, setImportResult] = useState<CsvImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Batch Job State
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchJob, setBatchJob] = useState<BatchJob | null>(null);
  const [batchResults, setBatchResults] = useState<WebsiteInspectionItem[]>([]);
  const [evaluation, setEvaluation] = useState<BatchEvaluation | null>(null);
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Evidence viewer modal
  const [selectedInspection, setSelectedInspection] = useState<WebsiteInspectionItem | null>(null);

  // Poll batch progress when scanning
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (batchId && scanning) {
      interval = setInterval(async () => {
        try {
          const res = await api.getBatch(batchId);
          if (res.success && res.batch) {
            setBatchJob(res.batch);
            if (res.batch.status === 'completed' || res.batch.status === 'failed') {
              setScanning(false);
              if (interval) clearInterval(interval);
              const [resultsRes, evalRes] = await Promise.allSettled([
                api.getBatchResults(batchId),
                api.getBatchEvaluation(batchId),
              ]);
              if (resultsRes.status === 'fulfilled' && resultsRes.value.success) {
                setBatchResults(resultsRes.value.results);
              }
              if (evalRes.status === 'fulfilled' && evalRes.value.success) {
                setEvaluation(evalRes.value);
              }
            }
          }
        } catch {
          // Keep polling
        }
      }, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [batchId, scanning]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setImportResult(null);
      setImportError(null);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setImporting(true);
    setImportError(null);

    try {
      const res = await api.uploadCsv(file, autoScan);
      if (res.success) {
        setImportResult(res);
        if (res.batch_id) {
          setBatchId(res.batch_id);
          setScanning(true);
        }
      }
    } catch (err: any) {
      setImportError(err?.message || 'Failed to upload and validate CSV file.');
    } finally {
      setImporting(false);
    }
  };

  const handleStartBatch = async () => {
    if (!importResult || !importResult.websites || importResult.websites.length === 0) return;

    setScanning(true);
    setScanError(null);

    try {
      const res = await api.scanBatch(importResult.websites);
      if (res.success) {
        setBatchId(res.batch_id);
        const batchData = await api.getBatch(res.batch_id);
        if (batchData.success) {
          setBatchJob(batchData.batch);
        }
      }
    } catch (err: any) {
      setScanError(err?.message || 'Failed to initiate batch scan.');
      setScanning(false);
    }
  };

  const runDownload = async (fn: () => Promise<void>) => {
    setDownloadError(null);
    try {
      await fn();
    } catch (err: any) {
      setDownloadError(err?.message || 'Download failed.');
    }
  };

  const progressPercent =
    batchJob && batchJob.total_records > 0
      ? Math.round((batchJob.processed_records / batchJob.total_records) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* Upload & Import Card */}
      <Card
        title="CSV Batch Importer & Validator"
        subtitle="Import organization lists, validate domain schemes, and execute batch CAPTCHA audits"
      >
        <form onSubmit={handleUpload} className="space-y-4">
          <div className="border-2 border-dashed border-slate-300 hover:border-blue-400 bg-slate-50/50 rounded-2xl p-6 text-center transition cursor-pointer">
            <input
              type="file"
              accept=".csv"
              id="csvFileInput"
              onChange={handleFileChange}
              className="hidden"
            />
            <label htmlFor="csvFileInput" className="cursor-pointer space-y-2 block">
              <FileSpreadsheet className="w-10 h-10 mx-auto text-blue-600" />
              <div className="text-xs font-semibold text-slate-700">
                {file ? (
                  <span className="text-blue-600 font-bold">{file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
                ) : (
                  <span>Click to select CSV file, or drag and drop here</span>
                )}
              </div>
              <p className="text-[11px] text-slate-400">
                Required columns: Company / company_name and Website / website_url. Optional: Captcha (expected),
                Contact Page, Platform, City, State, Category. All columns are preserved. (Max file size: 5MB)
              </p>
            </label>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={autoScan}
                onChange={(e) => setAutoScan(e.target.checked)}
                className="rounded text-blue-600 focus:ring-blue-500 h-4 w-4 border-slate-300"
              />
              <span className="font-medium text-slate-700">
                Automatically start batch scan upon successful import
              </span>
            </label>

            <button
              type="submit"
              disabled={importing || !file}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium px-6 py-2 rounded-xl text-xs transition flex items-center gap-1.5 shadow-md shadow-blue-600/20"
            >
              {importing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Validating CSV...</span>
                </>
              ) : (
                <>
                  <Upload className="w-3.5 h-3.5" />
                  <span>Import & Validate CSV</span>
                </>
              )}
            </button>
          </div>
        </form>

        {importError && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{importError}</span>
          </div>
        )}
      </Card>

      {/* Validation Results Card */}
      {importResult && (
        <Card
          title="CSV Validation Summary"
          subtitle={importResult.message}
          action={
            importResult.valid_count > 0 && !scanning && !batchJob ? (
              <button
                onClick={handleStartBatch}
                className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-4 py-2 rounded-xl transition flex items-center gap-1.5 shadow-sm"
              >
                <Play className="w-3.5 h-3.5" />
                <span>Launch Batch Scan ({importResult.valid_count} sites)</span>
              </button>
            ) : null
          }
        >
          <div className="space-y-4">
            {/* KPI Badges */}
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-center">
                <span className="text-[10px] font-semibold uppercase text-slate-400">Total Rows</span>
                <p className="text-xl font-bold text-slate-900 mt-1">{importResult.total_rows}</p>
              </div>
              <div className="bg-emerald-50 p-3.5 rounded-xl border border-emerald-200 text-center">
                <span className="text-[10px] font-semibold uppercase text-emerald-600">Valid Rows</span>
                <p className="text-xl font-bold text-emerald-700 mt-1">{importResult.valid_count}</p>
              </div>
              <div className="bg-rose-50 p-3.5 rounded-xl border border-rose-200 text-center">
                <span className="text-[10px] font-semibold uppercase text-rose-600">Invalid Rows</span>
                <p className="text-xl font-bold text-rose-700 mt-1">{importResult.invalid_count}</p>
              </div>
            </div>

            {importResult.columns && importResult.columns.length > 0 && (
              <div data-testid="preserved-columns" className="text-xs text-slate-600">
                <span className="font-semibold text-slate-700">Columns preserved ({importResult.columns.length}): </span>
                {importResult.columns.join(' · ')}
                {importResult.unmapped_columns && importResult.unmapped_columns.length > 0 && (
                  <span className="text-slate-500">
                    {' '}
                    (stored but not used for scanning: {importResult.unmapped_columns.join(', ')})
                  </span>
                )}
              </div>
            )}

            {/* Error Table if any */}
            {importResult.errors && importResult.errors.length > 0 && (
              <div className="mt-3">
                <h4 className="text-xs font-semibold text-rose-700 uppercase tracking-wider mb-2">
                  Validation Errors ({importResult.errors.length})
                </h4>
                <div className="border border-rose-200 rounded-xl overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-rose-50 border-b border-rose-200 text-rose-800 font-semibold">
                        <th className="py-2 px-3">Row #</th>
                        <th className="py-2 px-3">Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-rose-100 bg-white text-slate-700">
                      {importResult.errors.map((err, idx) => (
                        <tr key={idx}>
                          <td className="py-2 px-3 font-mono text-rose-600 font-semibold">{err.row}</td>
                          <td className="py-2 px-3">{err.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {importResult.warnings && importResult.warnings.length > 0 && (
              <div className="mt-3">
                <h4 className="text-xs font-semibold text-amber-700 uppercase tracking-wider mb-2">
                  Warnings ({importResult.warnings.length}) - rows kept, value ignored or not scored
                </h4>
                <ul className="text-xs text-slate-700 space-y-1 border border-amber-200 bg-amber-50/50 rounded-xl p-3">
                  {importResult.warnings.slice(0, 20).map((w, idx) => (
                    <li key={idx}>
                      <span className="font-mono font-semibold text-amber-700">Row {w.row}:</span> {w.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Live Batch Execution Monitor */}
      {batchJob && (
        <Card
          title={`Batch Audit Pipeline: ${batchJob.id.slice(0, 8)}...`}
          subtitle={`Status: ${batchJob.status.toUpperCase()}`}
          action={
            batchJob.status === 'completed' && (
              <button
                onClick={() => runDownload(() => api.downloadBatchReport(batchJob.id))}
                className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium px-4 py-2 rounded-xl transition flex items-center gap-1.5 shadow-sm"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download CSV Audit Report</span>
              </button>
            )
          }
        >
          <div className="space-y-4">
            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
                <span className="flex items-center gap-2">
                  {scanning && <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />}
                  Processing: {batchJob.processed_records} of {batchJob.total_records} targets completed
                </span>
                <span className="font-bold font-mono">{progressPercent}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
                <div
                  className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {(scanError || downloadError) && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{scanError || downloadError}</span>
              </div>
            )}

            {/* Results Table if completed */}
            {batchResults.length > 0 && (
              <div className="pt-4 border-t border-slate-100">
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
                  Inspected Websites ({batchResults.length})
                </h4>
                <div className="overflow-x-auto border border-slate-200 rounded-xl">
                  <table className="w-full text-left text-xs" data-testid="batch-results-table">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                        <th className="py-2.5 px-3">Company</th>
                        <th className="py-2.5 px-3">Website URL</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3">Detected</th>
                        <th className="py-2.5 px-3">Contact form</th>
                        <th className="py-2.5 px-3">Result</th>
                        <th className="py-2.5 px-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-700">
                      {batchResults.map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50">
                          <td className="py-2.5 px-3 font-semibold text-slate-900">
                            {item.company_name}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-slate-500 text-[11px] max-w-[200px] truncate">
                            {item.website_url}
                          </td>
                          <td className="py-2.5 px-3">
                            <Badge variant="status" value={item.scan_status} size="sm" />
                          </td>
                          <td className="py-2.5 px-3">
                            <Badge
                              variant="provider"
                              value={item.captcha_provider || (item.captcha_detected ? 'detected' : 'no_captcha')}
                              size="sm"
                            />
                            {item.captcha_subtype && (
                              <span className="ml-1 text-[10px] text-slate-500">{item.captcha_subtype}</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-medium">
                            {item.contact_form_found ? 'Yes' : 'No'}
                          </td>
                          <td className="py-2.5 px-3">
                            <ResultPill value={item.result_category} />
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              onClick={() => setSelectedInspection(item)}
                              className="text-blue-600 hover:text-blue-800 font-semibold inline-flex items-center gap-1"
                            >
                              <Eye className="w-3.5 h-3.5" />
                              <span>Details</span>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Expected vs detected evaluation */}
      {evaluation && (
        <Card
          title="Expected vs Detected CAPTCHA"
          subtitle="Compares the CSV's expected CAPTCHA with what the inspection actually observed"
          action={
            <div className="flex gap-2">
              <button
                onClick={() => runDownload(() => api.downloadBatchEvaluation(evaluation.batch_id, 'csv'))}
                className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium px-3 py-2 rounded-xl flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>CSV</span>
              </button>
              <button
                onClick={() => runDownload(() => api.downloadBatchEvaluation(evaluation.batch_id, 'md'))}
                className="bg-slate-100 hover:bg-slate-200 text-slate-900 text-xs font-medium px-3 py-2 rounded-xl flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Markdown</span>
              </button>
            </div>
          }
        >
          <div className="space-y-4" data-testid="evaluation-card">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              {(Object.keys(RESULT_STYLE) as ResultCategory[]).map((k) => (
                <div key={k} className={`p-3 rounded-xl border text-center ${RESULT_STYLE[k].cls}`}>
                  <span className="text-[10px] font-semibold uppercase">{RESULT_STYLE[k].label}</span>
                  <p className="text-xl font-bold mt-1" data-testid={`eval-count-${k}`}>
                    {evaluation.summary.counts[k]}
                  </p>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-700" data-testid="eval-note">
              <span className="font-semibold">
                Agreement:{' '}
                {evaluation.summary.agreement_pct !== null ? `${evaluation.summary.agreement_pct}%` : 'n/a'}
              </span>{' '}
              over {evaluation.summary.eligible_records} eligible record(s) of {evaluation.summary.total_records}.{' '}
              {evaluation.summary.sample_size_note} <em>Not accessible</em> and <em>Not verified</em> records are
              excluded from the percentage.
            </p>
            <div className="overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-left text-xs" data-testid="evaluation-table">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                    <th className="py-2.5 px-3">Website</th>
                    <th className="py-2.5 px-3">Expected</th>
                    <th className="py-2.5 px-3">Detected</th>
                    <th className="py-2.5 px-3">Contact page</th>
                    <th className="py-2.5 px-3">Widget loaded</th>
                    <th className="py-2.5 px-3">Result</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {evaluation.rows.map((r, idx) => (
                    <tr key={idx}>
                      <td className="py-2.5 px-3 font-semibold text-slate-900">{r.company}</td>
                      <td className="py-2.5 px-3">{r.expected || <span className="text-slate-400">(not provided)</span>}</td>
                      <td className="py-2.5 px-3">{r.detected}</td>
                      <td className="py-2.5 px-3 font-mono text-[11px] max-w-[220px] truncate">{r.contact_page || '-'}</td>
                      <td className="py-2.5 px-3">{r.widget_loaded ? 'Yes' : 'No'}</td>
                      <td className="py-2.5 px-3">
                        <ResultPill value={r.result_category} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      )}

      {/* Modal for Website Item Details */}
      {selectedInspection && (
        <Modal
          isOpen={!!selectedInspection}
          onClose={() => setSelectedInspection(null)}
          title={`Batch Result: ${selectedInspection.company_name}`}
          subtitle={selectedInspection.website_url}
          maxWidth="4xl"
          footer={
            <button
              onClick={() => setSelectedInspection(null)}
              className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-medium"
            >
              Close
            </button>
          }
        >
          <div className="mb-3 text-xs text-slate-600 grid grid-cols-2 gap-x-6 gap-y-1">
            <div>Robots: <b>{selectedInspection.robots_status || 'not checked'}</b></div>
            <div>Widget: <b>{selectedInspection.widget_state || 'n/a'}</b></div>
            <div>Expected: <b>{selectedInspection.expected_captcha_raw || '(not provided)'}</b></div>
            <div>Result: <ResultPill value={selectedInspection.result_category} /></div>
            {selectedInspection.error_details && (
              <div className="col-span-2 text-rose-700">Error: {selectedInspection.error_details}</div>
            )}
          </div>
          <EvidenceViewer
            pageUrl={selectedInspection.contact_page_url || selectedInspection.website_url}
            screenshotPath={selectedInspection.screenshot_path}
            provider={selectedInspection.captcha_provider}
            evidence={{
              evidence: selectedInspection.evidence,
              form_probe: selectedInspection.form_probe,
              source_row: selectedInspection.source_row,
            }}
            handlingStrategy={selectedInspection.human_review_required ? 'human_review' : 'no_challenge'}
          />
        </Modal>
      )}
    </div>
  );
}
