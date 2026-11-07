'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { DiscoveredPage } from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { EvidenceViewer } from '@/components/EvidenceViewer';
import {
  ShieldAlert,
  Search,
  RefreshCw,
  ExternalLink,
  Eye,
  Filter,
  CheckCircle,
  FileSearch,
} from 'lucide-react';

export default function ResultsPage() {
  const [pages, setPages] = useState<DiscoveredPage[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters
  const [providerFilter, setProviderFilter] = useState<string>('all');
  const [captchaOnly, setCaptchaOnly] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Modal
  const [selectedPage, setSelectedPage] = useState<DiscoveredPage | null>(null);

  const fetchResults = async () => {
    setLoading(true);
    try {
      const res = await api.listDiscoveredPages({
        captcha_only: captchaOnly,
        provider: providerFilter === 'all' ? undefined : providerFilter,
      });
      if (res.success) {
        setPages(res.pages);
        setTotal(res.total);
      }
    } catch {
      // Backend error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, [providerFilter, captchaOnly]);

  const filteredPages = pages.filter((p) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      p.url.toLowerCase().includes(term) ||
      (p.title && p.title.toLowerCase().includes(term)) ||
      (p.captcha_provider && p.captcha_provider.toLowerCase().includes(term))
    );
  });

  return (
    <div className="space-y-6">
      {/* Controls & Filter Card */}
      <Card>
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
          {/* Search bar */}
          <div className="relative w-full lg:w-96">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search by URL, page title, or provider..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-xl pl-10 pr-4 py-2 text-xs placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500 transition"
            />
          </div>

          {/* Provider Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              className="bg-slate-50 border border-slate-200 text-slate-800 rounded-xl px-3 py-2 text-xs font-medium focus:ring-2 focus:ring-blue-500 transition"
            >
              <option value="all">All Challenge Providers</option>
              <option value="google_recaptcha">Google reCAPTCHA</option>
              <option value="cloudflare_turnstile">Cloudflare Turnstile</option>
              <option value="hcaptcha">hCaptcha</option>
              <option value="synthetic_text_captcha">Synthetic Text OCR</option>
              <option value="no_captcha">No CAPTCHA</option>
            </select>

            <label className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-2 rounded-xl text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={captchaOnly}
                onChange={(e) => setCaptchaOnly(e.target.checked)}
                className="rounded text-blue-600 focus:ring-blue-500 h-3.5 w-3.5 border-slate-300"
              />
              <span className="font-medium text-slate-700">CAPTCHA Detections Only</span>
            </label>

            <button
              onClick={fetchResults}
              className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition"
              title="Refresh results"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </Card>

      {/* Results Table */}
      <Card
        title={`Classified Discoveries (${filteredPages.length})`}
        subtitle="Itemized CAPTCHA challenges detected across all monitored websites"
      >
        {loading ? (
          <div className="py-16 text-center text-slate-400 flex flex-col items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin mb-2 text-blue-500" />
            <p className="text-xs">Loading classified findings...</p>
          </div>
        ) : filteredPages.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p className="text-sm font-medium">No results found matching your filters.</p>
            <p className="text-xs text-slate-400 mt-1">
              Try unchecking &ldquo;CAPTCHA Detections Only&rdquo; or running a new URL scan.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-3">Page / Target URL</th>
                  <th className="py-3 px-2">Provider</th>
                  <th className="py-3 px-2">Confidence</th>
                  <th className="py-3 px-2">Handling Strategy</th>
                  <th className="py-3 px-2">Forms</th>
                  <th className="py-3 px-2">Review Status</th>
                  <th className="py-3 px-2">Discovered</th>
                  <th className="py-3 px-3 text-right">Evidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filteredPages.map((page) => (
                  <tr key={page.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3 px-3 max-w-[280px]">
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
                    <td className="py-3 px-2">
                      <Badge
                        variant="provider"
                        value={page.captcha_provider || (page.captcha_detected ? 'detected' : 'no_captcha')}
                        size="sm"
                      />
                    </td>
                    <td className="py-3 px-2 font-mono">
                      {page.captcha_confidence ? (
                        <span className="font-semibold text-slate-800">
                          {Math.round(page.captcha_confidence * 100)}%
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="py-3 px-2">
                      {page.handling_strategy ? (
                        <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px] font-mono">
                          {page.handling_strategy}
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="py-3 px-2 font-mono text-slate-800 font-medium">
                      {page.forms_found_count}
                    </td>
                    <td className="py-3 px-2">
                      <Badge variant="review" value={page.review_status} size="sm" />
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-[11px] whitespace-nowrap">
                      {new Date(page.created_at).toLocaleDateString()}
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
        )}
      </Card>

      {/* Modal */}
      {selectedPage && (
        <Modal
          isOpen={!!selectedPage}
          onClose={() => setSelectedPage(null)}
          title={`Evidence: ${selectedPage.path || '/'}`}
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
