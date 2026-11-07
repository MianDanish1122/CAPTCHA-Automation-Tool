'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { OverviewStats, HealthResponse, SystemSettings } from '@/lib/types';
import { StatCard } from '@/components/StatCard';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import {
  Search,
  Globe,
  ShieldAlert,
  UserCheck,
  CheckCircle2,
  Clock,
  ArrowRight,
  Shield,
  Layers,
  Sparkles,
  ExternalLink,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';

export default function OverviewPage() {
  const router = useRouter();
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [quickUrl, setQuickUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [statsRes, healthRes, settingsRes] = await Promise.allSettled([
        api.getOverviewStats(),
        api.getHealth(),
        api.getSettings(),
      ]);

      if (statsRes.status === 'fulfilled') setStats(statsRes.value);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
      if (settingsRes.status === 'fulfilled') setSettings(settingsRes.value);
    } catch (err: any) {
      setError(err?.message || 'Failed to communicate with backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleQuickScan = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickUrl.trim()) return;
    router.push(`/inspector?url=${encodeURIComponent(quickUrl.trim())}`);
  };

  const providerBreakdown = stats?.provider_breakdown || {};
  const totalCaptchas = stats?.total_captchas || 0;

  return (
    <div className="space-y-6">
      {/* Top Banner: Quick Scan Bar */}
      <div className="bg-gradient-to-r from-slate-900 via-blue-950 to-slate-900 rounded-2xl p-6 text-white shadow-lg border border-slate-800">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-medium mb-3 border border-blue-400/20">
            <Sparkles className="w-3.5 h-3.5 text-blue-400" />
            <span>Next-Generation Automated Website Inspection</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight">
            Security & CAPTCHA Intelligence Dashboard
          </h1>
          <p className="mt-2 text-sm text-slate-300 leading-relaxed">
            Scan authorized domains, discover contact touchpoints, classify CAPTCHA challenges,
            and maintain an auditable human review pipeline.
          </p>

          <form onSubmit={handleQuickScan} className="mt-5 flex flex-col sm:flex-row gap-2 max-w-2xl">
            <div className="relative flex-1">
              <Globe className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Enter authorized target URL (e.g. https://example.com)"
                value={quickUrl}
                onChange={(e) => setQuickUrl(e.target.value)}
                className="w-full bg-slate-800/80 border border-slate-700 text-white rounded-xl pl-10 pr-4 py-2.5 text-sm placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500 transition"
              />
            </div>
            <button
              type="submit"
              disabled={submitting || !quickUrl.trim()}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium px-5 py-2.5 rounded-xl text-sm transition flex items-center justify-center gap-2 shadow-md shadow-blue-600/30"
            >
              <Search className="w-4 h-4" />
              <span>Inspect Now</span>
            </button>
          </form>
        </div>
      </div>

      {/* System Status Alert / Diagnostic Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200/80 rounded-xl p-4 flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-100">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
                Security Policy
              </span>
              <span className="text-sm font-bold text-slate-800">
                {settings?.enable_live_scan ? 'Live Mode Active' : 'Strict Allowlist Only'}
              </span>
            </div>
          </div>
          <span className="text-xs bg-slate-100 text-slate-700 px-2 py-1 rounded font-mono">
            SSRF Guard ON
          </span>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-4 flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
                OCR Engine
              </span>
              <span className="text-sm font-bold text-slate-800">
                {health?.ocr_engine === 'tesseract_ready' ? 'Tesseract OCR Ready' : 'OCR Standby'}
              </span>
            </div>
          </div>
          <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded font-medium">
            OpenCV + PyTesseract
          </span>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-4 flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600 border border-amber-100">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
                Review Queue
              </span>
              <span className="text-sm font-bold text-slate-800">
                {stats?.pending_reviews ?? 0} Pending Verification
              </span>
            </div>
          </div>
          <Link
            href="/reviews"
            className="text-xs text-blue-600 hover:text-blue-800 font-medium inline-flex items-center gap-1"
          >
            Manage <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Scans"
          value={stats?.total_scans ?? 0}
          icon={<Search className="w-5 h-5" />}
          subtitle="All completed & active jobs"
          accentColor="blue"
        />
        <StatCard
          title="Discovered Pages"
          value={stats?.total_pages ?? 0}
          icon={<Globe className="w-5 h-5" />}
          subtitle="Crawled same-domain pages"
          accentColor="slate"
        />
        <StatCard
          title="CAPTCHAs Found"
          value={stats?.total_captchas ?? 0}
          icon={<ShieldAlert className="w-5 h-5" />}
          subtitle="Classified challenges"
          accentColor="purple"
        />
        <StatCard
          title="Batch Jobs"
          value={stats?.total_batches ?? 0}
          icon={<Layers className="w-5 h-5" />}
          subtitle="CSV batch pipelines"
          accentColor="emerald"
        />
      </div>

      {/* Provider Distribution & Recent Activity Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Provider Breakdown Card */}
        <Card
          title="Detected CAPTCHA Distribution"
          subtitle="Classification breakdown across scanned assets"
          className="lg:col-span-1"
        >
          <div className="space-y-4">
            {Object.keys(providerBreakdown).length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                <p className="text-xs font-medium">No CAPTCHA markers classified yet.</p>
                <p className="text-[11px] text-slate-400 mt-1">Run an inspection to collect statistics.</p>
              </div>
            ) : (
              Object.entries(providerBreakdown).map(([prov, count]) => {
                const pct = totalCaptchas > 0 ? Math.round((count / totalCaptchas) * 100) : 0;
                return (
                  <div key={prov} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <Badge variant="provider" value={prov} size="sm" />
                      <span className="font-semibold text-slate-700">
                        {count} ({pct}%)
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}

            <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs">
              <span className="text-slate-500">View detailed telemetry</span>
              <Link href="/results" className="text-blue-600 font-medium hover:underline inline-flex items-center gap-1">
                All Findings <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
          </div>
        </Card>

        {/* Recent Scans Table */}
        <Card
          title="Recent Scan Jobs"
          subtitle="Latest website crawls and form investigations"
          className="lg:col-span-2"
          action={
            <Link
              href="/scans"
              className="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              View Full History <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          }
        >
          {loading ? (
            <div className="py-12 flex justify-center items-center text-slate-400">
              <RefreshCw className="w-5 h-5 animate-spin mr-2" />
              <span className="text-xs">Loading scan records...</span>
            </div>
          ) : !stats?.recent_scans || stats.recent_scans.length === 0 ? (
            <div className="text-center py-10 text-slate-400">
              <Search className="w-8 h-8 mx-auto mb-2 text-slate-300" />
              <p className="text-sm font-medium">No recent scans recorded.</p>
              <p className="text-xs text-slate-400 mt-1">
                Enter a target URL above or click New Inspection to crawl.
              </p>
              <Link
                href="/inspector"
                className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:underline"
              >
                Launch First Scan <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-400 font-medium uppercase tracking-wider">
                    <th className="pb-3 pl-1">Target Website</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3">Pages</th>
                    <th className="pb-3">CAPTCHA</th>
                    <th className="pb-3">Date</th>
                    <th className="pb-3 text-right pr-1">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-600">
                  {stats.recent_scans.map((scan) => (
                    <tr key={scan.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 pl-1 font-medium text-slate-900 max-w-[220px] truncate">
                        <span title={scan.submitted_url}>{scan.submitted_url}</span>
                      </td>
                      <td className="py-3">
                        <Badge variant="status" value={scan.status} size="sm" />
                      </td>
                      <td className="py-3 font-mono">{scan.pages_crawled}</td>
                      <td className="py-3">
                        {scan.captcha_detected ? (
                          <span className="text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded text-[11px] font-semibold">
                            Found ({scan.captcha_providers?.length || 1})
                          </span>
                        ) : (
                          <span className="text-slate-500 bg-slate-100 px-2 py-0.5 rounded text-[11px]">
                            Clean
                          </span>
                        )}
                      </td>
                      <td className="py-3 text-slate-400 font-mono text-[11px]">
                        {new Date(scan.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 text-right pr-1">
                        <Link
                          href={`/scans?scan_id=${scan.id}`}
                          className="text-blue-600 hover:text-blue-800 font-semibold"
                        >
                          Details
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
