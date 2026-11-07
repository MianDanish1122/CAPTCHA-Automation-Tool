'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { UrlScan, UrlScanResultsResponse, DiscoveredPage } from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Drawer } from '@/components/Drawer';
import { Modal } from '@/components/Modal';
import { EvidenceViewer } from '@/components/EvidenceViewer';
import {
  History,
  Search,
  RefreshCw,
  Globe,
  ExternalLink,
  ChevronRight,
  Eye,
  ShieldAlert,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react';

function ScansContent() {
  const searchParams = useSearchParams();
  const directScanId = searchParams.get('scan_id');

  const [scans, setScans] = useState<UrlScan[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);

  // Selected scan for Drawer
  const [activeScanResults, setActiveScanResults] = useState<UrlScanResultsResponse | null>(null);
  const [loadingDetails, setLoadingDetails] = useState<boolean>(false);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  // Selected page for Evidence Modal
  const [evidencePage, setEvidencePage] = useState<DiscoveredPage | null>(null);

  const fetchScans = async () => {
    setLoading(true);
    try {
      const res = await api.listScans({
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      if (res.success) {
        setScans(res.scans);
        setTotal(res.total);
      }
    } catch {
      // Backend error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScans();
  }, [statusFilter]);

  // Open direct scan id if provided in query string
  useEffect(() => {
    if (directScanId) {
      handleOpenDetails(directScanId);
    }
  }, [directScanId]);

  const handleOpenDetails = async (scanId: string) => {
    setDrawerOpen(true);
    setLoadingDetails(true);
    try {
      const details = await api.getScanResults(scanId);
      setActiveScanResults(details);
    } catch {
      setActiveScanResults(null);
    } finally {
      setLoadingDetails(false);
    }
  };

  const filteredScans = scans.filter((s) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      s.submitted_url.toLowerCase().includes(term) ||
      s.domain.toLowerCase().includes(term) ||
      s.id.toLowerCase().includes(term)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <Card>
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Search bar */}
          <div className="relative w-full md:w-96">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search by URL, domain, or Scan ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-xl pl-10 pr-4 py-2 text-xs placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500 transition"
            />
          </div>

          {/* Status Tabs and Refresh */}
          <div className="flex items-center gap-2 w-full md:w-auto justify-end">
            <div className="flex bg-slate-100 p-1 rounded-xl text-xs font-medium">
              {['all', 'completed', 'crawling', 'failed'].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-3 py-1.5 rounded-lg capitalize transition ${
                    statusFilter === st
                      ? 'bg-white text-slate-900 shadow-xs font-semibold'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            <button
              onClick={fetchScans}
              className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition"
              title="Refresh scan history"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </Card>

      {/* Scans Table Card */}
      <Card
        title={`Scan Records (${filteredScans.length})`}
        subtitle="Complete audit history of automated crawler executions"
      >
        {loading ? (
          <div className="py-16 text-center text-slate-400 flex flex-col items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin mb-2 text-blue-500" />
            <p className="text-xs">Fetching crawl records...</p>
          </div>
        ) : filteredScans.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <History className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p className="text-sm font-medium">No scans match your criteria.</p>
            <p className="text-xs text-slate-400 mt-1">
              Adjust filters or run a new inspection via URL Inspector.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-3">Target Domain & URL</th>
                  <th className="py-3 px-2">Scan ID</th>
                  <th className="py-3 px-2">Status</th>
                  <th className="py-3 px-2">Pages</th>
                  <th className="py-3 px-2">Contact</th>
                  <th className="py-3 px-2">CAPTCHA Providers</th>
                  <th className="py-3 px-2">Duration</th>
                  <th className="py-3 px-2">Discovered</th>
                  <th className="py-3 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filteredScans.map((scan) => {
                  const sId = scan.id || (scan as any).scan_id || '';
                  return (
                  <tr key={sId} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3 px-3 max-w-[260px]">
                      <div className="font-semibold text-slate-900 truncate">
                        {scan.domain}
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono truncate">
                        {scan.submitted_url}
                      </div>
                    </td>
                    <td className="py-3 px-2 font-mono text-slate-500 text-[11px]">
                      {sId.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-2">
                      <Badge variant="status" value={scan.status} size="sm" />
                    </td>
                    <td className="py-3 px-2 font-mono font-medium">{scan.pages_crawled}</td>
                    <td className="py-3 px-2 font-mono text-blue-600 font-medium">
                      {scan.contact_pages_found}
                    </td>
                    <td className="py-3 px-2">
                      {scan.captcha_detected ? (
                        <div className="flex flex-wrap gap-1">
                          {scan.captcha_providers && scan.captcha_providers.length > 0 ? (
                            scan.captcha_providers.map((p) => (
                              <Badge key={p} variant="provider" value={p} size="sm" />
                            ))
                          ) : (
                            <Badge variant="provider" value="detected" size="sm" />
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-400 text-[11px]">None Detected</span>
                      )}
                    </td>
                    <td className="py-3 px-2 font-mono text-slate-500 text-[11px]">
                      {scan.crawl_duration_ms ? `${Math.round(scan.crawl_duration_ms)}ms` : '-'}
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-[11px] whitespace-nowrap">
                      {new Date(scan.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => handleOpenDetails(sId)}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-3 py-1 rounded-md transition"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                );})}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Slide-out Drawer for Scan Details */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Scan Inspection Details"
        subtitle={activeScanResults ? `Domain: ${activeScanResults.domain}` : 'Loading...'}
        width="2xl"
      >
        {loadingDetails ? (
          <div className="py-16 text-center text-slate-400 flex flex-col items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin mb-2 text-blue-500" />
            <p className="text-xs">Loading itemized pages...</p>
          </div>
        ) : activeScanResults ? (
          <div className="space-y-6">
            {/* Scan Meta Box */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-slate-400 block font-medium">Target URL:</span>
                  <span className="font-mono text-slate-900 break-all">{activeScanResults.submitted_url}</span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Status:</span>
                  <Badge variant="status" value={activeScanResults.status} size="sm" />
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Pages Crawled:</span>
                  <span className="font-bold text-slate-800">{activeScanResults.pages_crawled}</span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Execution Duration:</span>
                  <span className="font-mono text-slate-800">{activeScanResults.crawl_duration_ms} ms</span>
                </div>
              </div>
            </div>

            {/* Discovered Pages List */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
                Itemized Discovered Pages ({activeScanResults.results?.length || 0})
              </h4>
              <div className="space-y-3">
                {activeScanResults.results?.map((page) => (
                  <div
                    key={page.id}
                    className="border border-slate-200 rounded-xl p-3.5 hover:border-slate-300 bg-white transition space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-0.5">
                        <span className="font-semibold text-slate-900 text-xs block">
                          {page.title || page.path || '/'}
                        </span>
                        <span className="font-mono text-[11px] text-slate-400 block break-all">
                          {page.url}
                        </span>
                      </div>
                      <Badge
                        variant="provider"
                        value={page.captcha_provider || (page.captcha_detected ? 'detected' : 'no_captcha')}
                        size="sm"
                      />
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                      <div className="flex items-center gap-3">
                        <span>Depth: L{page.depth}</span>
                        <span>Forms: {page.forms_found_count}</span>
                        {page.is_contact_page && (
                          <span className="text-blue-600 font-semibold">Contact Touchpoint</span>
                        )}
                      </div>
                      <button
                        onClick={() => setEvidencePage(page)}
                        className="text-blue-600 hover:text-blue-800 font-semibold inline-flex items-center gap-1"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>View Evidence</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="py-12 text-center text-slate-400 text-xs">
            Failed to load details for this scan.
          </div>
        )}
      </Drawer>

      {/* Evidence Modal */}
      {evidencePage && (
        <Modal
          isOpen={!!evidencePage}
          onClose={() => setEvidencePage(null)}
          title={`Evidence: ${evidencePage.path || '/'}`}
          subtitle={evidencePage.url}
          maxWidth="4xl"
          footer={
            <button
              onClick={() => setEvidencePage(null)}
              className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-medium"
            >
              Close
            </button>
          }
        >
          <EvidenceViewer
            pageUrl={evidencePage.url}
            screenshotPath={evidencePage.screenshot_path}
            provider={evidencePage.captcha_provider}
            confidence={evidencePage.captcha_confidence}
            evidence={evidencePage.evidence}
            handlingStrategy={evidencePage.handling_strategy}
          />
        </Modal>
      )}
    </div>
  );
}

export default function ScansPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-400">Loading Scan History...</div>}>
      <ScansContent />
    </Suspense>
  );
}
