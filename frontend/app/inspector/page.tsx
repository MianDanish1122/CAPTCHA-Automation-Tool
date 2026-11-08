'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { DiscoveredPage, UrlScanResultsResponse } from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { EvidenceViewer } from '@/components/EvidenceViewer';
import {
  Search,
  Globe,
  Sliders,
  Play,
  RefreshCw,
  ExternalLink,
  ShieldAlert,
  CheckCircle2,
  FileText,
  AlertCircle,
  Eye,
  Layers,
  ChevronRight,
} from 'lucide-react';

function InspectorContent() {
  const searchParams = useSearchParams();
  const initialUrl = searchParams.get('url') || '';

  const [url, setUrl] = useState(initialUrl);
  const [maxPages, setMaxPages] = useState<number>(5);
  const [maxDepth, setMaxDepth] = useState<number>(2);
  const [allowLoopback, setAllowLoopback] = useState<boolean>(true);
  const [runInBackground, setRunInBackground] = useState<boolean>(false);

  const [scanning, setScanning] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<string>('idle');
  const [scanResult, setScanResult] = useState<UrlScanResultsResponse | null>(null);
  const [scanId, setScanId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Evidence Modal state
  const [selectedPage, setSelectedPage] = useState<DiscoveredPage | null>(null);

  useEffect(() => {
    if (initialUrl && !scanning && !scanResult) {
      setUrl(initialUrl);
    }
  }, [initialUrl]);

  // Polling for background or running scan
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (scanId && scanning) {
      interval = setInterval(async () => {
        try {
          const res = await api.getScanResults(scanId);
          if (res.status === 'completed' || res.status === 'failed') {
            setScanResult(res);
            setScanning(false);
            setCurrentStep(res.status === 'failed' ? 'failed' : 'done');
            if (res.status === 'failed') {
              setError((res as any).error_message || 'The scan failed; no page could be inspected.');
            }
            if (interval) clearInterval(interval);
          } else {
            setCurrentStep('crawling');
            setScanResult(res);
          }
        } catch {
          // Keep polling
        }
      }, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [scanId, scanning]);

  const handleStartScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setError(null);
    setScanResult(null);
    setScanning(true);
    setCurrentStep('initializing');

    try {
      setCurrentStep('crawling');
      const response = await api.inspectUrl({
        url: url.trim(),
        max_pages: maxPages,
        max_depth: maxDepth,
        allow_loopback: allowLoopback,
        background: runInBackground,
      });

      if (!response.success) {
        // a failed crawl returns its reason in `error` (e.g. "No page could be inspected: ... timed out")
        throw new Error((response as any).error || response.message || 'Inspection failed');
      }

      setScanId(response.scan_id);

      if (runInBackground) {
        setCurrentStep('crawling');
      } else {
        // Synchronous scan completed
        const fullResults = await api.getScanResults(response.scan_id);
        setScanResult(fullResults);
        setScanning(false);
        setCurrentStep('done');
      }
    } catch (err: any) {
      setError(err?.message || 'Inspection failed to execute');
      setScanning(false);
      setCurrentStep('failed');
    }
  };

  return (
    <div className="space-y-6">
      {/* Configuration & Input Card */}
      <Card
        title="Automated URL & Contact Page Crawler"
        subtitle="Discover contact pages, inspect form structures, and detect CAPTCHA markers"
      >
        <form onSubmit={handleStartScan} className="space-y-5">
          {/* URL Input */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Target Website URL
            </label>
            <div className="relative">
              <Globe className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="https://example.com or http://localhost:8000/fixture"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
                className="w-full bg-slate-50 border border-slate-300 focus:bg-white text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500 transition"
              />
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Live scan checks domain allowlist. Enable loopback mode for local fixture testing.
            </p>
          </div>

          {/* Crawler Options Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-xl border border-slate-200/80">
            {/* Max Pages */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Max Pages to Crawl: <span className="font-bold text-blue-600 font-mono">{maxPages}</span>
              </label>
              <input
                type="range"
                min="1"
                max="20"
                value={maxPages}
                onChange={(e) => setMaxPages(Number(e.target.value))}
                className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span>1 page</span>
                <span>20 max</span>
              </div>
            </div>

            {/* Max Depth */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Crawl Depth: <span className="font-bold text-blue-600 font-mono">{maxDepth}</span>
              </label>
              <input
                type="range"
                min="0"
                max="3"
                value={maxDepth}
                onChange={(e) => setMaxDepth(Number(e.target.value))}
                className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span>0 (Home only)</span>
                <span>3 levels</span>
              </div>
            </div>

            {/* Loopback Toggle */}
            <div className="flex flex-col justify-center">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={allowLoopback}
                  onChange={(e) => setAllowLoopback(e.target.checked)}
                  className="rounded text-blue-600 focus:ring-blue-500 h-4 w-4 border-slate-300"
                />
                <span className="text-xs font-medium text-slate-700">Allow Localhost / Loopback</span>
              </label>
              <span className="text-[10px] text-slate-400 mt-0.5 pl-6">
                Useful for QA and mock test servers
              </span>
            </div>

            {/* Background Toggle */}
            <div className="flex flex-col justify-center">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={runInBackground}
                  onChange={(e) => setRunInBackground(e.target.checked)}
                  className="rounded text-blue-600 focus:ring-blue-500 h-4 w-4 border-slate-300"
                />
                <span className="text-xs font-medium text-slate-700">Asynchronous / Background</span>
              </label>
              <span className="text-[10px] text-slate-400 mt-0.5 pl-6">
                Polls results without blocking browser
              </span>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span>Playwright Headless Chromium Engine</span>
            </div>

            <button
              type="submit"
              disabled={scanning || !url.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium px-6 py-2.5 rounded-xl text-sm transition flex items-center gap-2 shadow-md shadow-blue-600/20"
            >
              {scanning ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Crawling Target...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>Start Live Inspection</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Error Alert */}
        {error && (
          <div className="mt-4 p-4 bg-rose-50 border border-rose-200 rounded-xl flex items-start gap-3 text-rose-800 text-xs">
            <AlertCircle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />
            <div>
              <p className="font-bold">Inspection Error</p>
              <p className="mt-0.5">{error}</p>
            </div>
          </div>
        )}
      </Card>

      {/* Crawl Pipeline Progress Tracker */}
      {scanning && (
        <Card title="Live Crawler Status" subtitle={`Job ID: ${scanId || 'Initializing'}`}>
          <div className="py-4 space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
              <span className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-blue-600 animate-spin" />
                Browser active: Navigating DOM, analyzing anchors, discovering contact routes...
              </span>
              <span className="font-mono text-slate-400">Step: {currentStep}</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
              <div className="bg-blue-600 h-2.5 rounded-full animate-pulse w-3/4" />
            </div>
          </div>
        </Card>
      )}

      {/* Scan Results Section */}
      {scanResult && (
        <div className="space-y-6">
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <span className="text-[11px] font-semibold uppercase text-slate-400 tracking-wider">
                Crawled Pages
              </span>
              <p className="text-xl font-bold text-slate-900 mt-1">{scanResult.pages_crawled}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <span className="text-[11px] font-semibold uppercase text-slate-400 tracking-wider">
                Contact Touchpoints
              </span>
              <p className="text-xl font-bold text-blue-600 mt-1">{scanResult.contact_pages_found}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <span className="text-[11px] font-semibold uppercase text-slate-400 tracking-wider">
                CAPTCHA Detected
              </span>
              <p className="text-xl font-bold text-slate-900 mt-1">
                {scanResult.captcha_detected ? (
                  <span className="text-rose-600">Yes</span>
                ) : (
                  <span className="text-emerald-600">No</span>
                )}
              </p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <span className="text-[11px] font-semibold uppercase text-slate-400 tracking-wider">
                Crawl Duration
              </span>
              <p className="text-xl font-bold text-slate-900 mt-1 font-mono">
                {scanResult.crawl_duration_ms} ms
              </p>
            </div>
          </div>

          {/* Discovered Pages Table */}
          <Card
            title={`Discovered Pages & Evidence (${scanResult.results?.length || 0})`}
            subtitle={`Target: ${scanResult.submitted_url}`}
          >
            {scanResult.results && scanResult.results.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-semibold uppercase tracking-wider">
                      <th className="py-3 px-3">Discovered Page / Path</th>
                      <th className="py-3 px-2">Depth</th>
                      <th className="py-3 px-2">Type</th>
                      <th className="py-3 px-2">Forms</th>
                      <th className="py-3 px-2">CAPTCHA Provider</th>
                      <th className="py-3 px-2">Review Status</th>
                      <th className="py-3 px-3 text-right">Evidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {scanResult.results.map((page) => (
                      <tr key={page.id} className="hover:bg-slate-50 transition-colors">
                        <td className="py-3 px-3 max-w-[260px]">
                          <div className="font-semibold text-slate-900 truncate">
                            {page.title || page.path || '/'}
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono truncate flex items-center gap-1">
                            <span>{page.url}</span>
                            <a
                              href={page.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-500 hover:text-blue-700"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                        </td>
                        <td className="py-3 px-2 font-mono text-slate-500">L{page.depth}</td>
                        <td className="py-3 px-2">
                          {page.is_contact_page ? (
                            <span className="bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full text-[11px] font-semibold">
                              Contact
                            </span>
                          ) : (
                            <span className="text-slate-400 text-[11px]">General</span>
                          )}
                        </td>
                        <td className="py-3 px-2 font-mono">
                          {page.forms_found_count > 0 ? (
                            <span className="font-bold text-slate-900">{page.forms_found_count}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="py-3 px-2">
                          <Badge
                            variant="provider"
                            value={page.captcha_provider || (page.captcha_detected ? 'detected' : 'no_captcha')}
                            size="sm"
                          />
                        </td>
                        <td className="py-3 px-2">
                          <Badge variant="review" value={page.review_status} size="sm" />
                        </td>
                        <td className="py-3 px-3 text-right">
                          <button
                            onClick={() => setSelectedPage(page)}
                            className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-2.5 py-1 rounded-md transition"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Inspect</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400 text-xs">
                No subpages discovered for this target.
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Evidence Viewer Modal */}
      {selectedPage && (
        <Modal
          isOpen={!!selectedPage}
          onClose={() => setSelectedPage(null)}
          title={`Page Evidence: ${selectedPage.path || '/'}`}
          subtitle={selectedPage.url}
          maxWidth="4xl"
          footer={
            <button
              onClick={() => setSelectedPage(null)}
              className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-medium"
            >
              Close
            </button>
          }
        >
          <EvidenceViewer
            pageUrl={selectedPage.url}
            screenshotPath={selectedPage.screenshot_path}
            provider={selectedPage.captcha_provider}
            confidence={selectedPage.captcha_confidence}
            evidence={selectedPage.evidence}
            handlingStrategy={selectedPage.handling_strategy}
          />
        </Modal>
      )}
    </div>
  );
}

export default function InspectorPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-400">Loading URL Inspector...</div>}>
      <InspectorContent />
    </Suspense>
  );
}
