'use client';

import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { CsvImportResult, BatchJob, BatchResultsResponse, WebsiteInspectionItem } from '@/lib/types';
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
  CheckCircle2,
  XCircle,
  FileText,
  ExternalLink,
  Layers,
  Eye,
} from 'lucide-react';

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
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanError, setScanError] = useState<string | null>(null);

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
              // Load full itemized results
              const resultsRes = await api.getBatchResults(batchId);
              if (resultsRes.success) {
                setBatchResults(resultsRes.results);
              }
              if (interval) clearInterval(interval);
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
                Required columns: company_name, website_url (Max file size: 5MB)
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
              <a
                href={api.getBatchReportUrl(batchJob.id)}
                download
                className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium px-4 py-2 rounded-xl transition flex items-center gap-1.5 shadow-sm"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download CSV Audit Report</span>
              </a>
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

            {scanError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{scanError}</span>
              </div>
            )}

            {/* Results Table if completed */}
            {batchResults.length > 0 && (
              <div className="pt-4 border-t border-slate-100">
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
                  Inspected Websites ({batchResults.length})
                </h4>
                <div className="overflow-x-auto border border-slate-200 rounded-xl">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                        <th className="py-2.5 px-3">Company</th>
                        <th className="py-2.5 px-3">Website URL</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3">CAPTCHA</th>
                        <th className="py-2.5 px-3">Forms</th>
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
                            <Badge variant="status" value={item.status} size="sm" />
                          </td>
                          <td className="py-2.5 px-3">
                            <Badge
                              variant="provider"
                              value={item.captcha_provider || (item.captcha_detected ? 'detected' : 'no_captcha')}
                              size="sm"
                            />
                          </td>
                          <td className="py-2.5 px-3 font-mono font-medium">
                            {item.forms_found_count}
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
          <EvidenceViewer
            pageUrl={selectedInspection.website_url}
            screenshotPath={selectedInspection.evidence?.screenshot_path || null}
            provider={selectedInspection.captcha_provider}
            confidence={selectedInspection.confidence_score}
            evidence={selectedInspection.evidence}
            handlingStrategy={selectedInspection.human_review_required ? 'human_review' : 'no_challenge'}
          />
        </Modal>
      )}
    </div>
  );
}
