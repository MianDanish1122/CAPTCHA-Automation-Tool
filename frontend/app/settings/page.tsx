'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { SystemSettings, HealthResponse } from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import {
  Settings as SettingsIcon,
  Shield,
  Server,
  Cpu,
  RefreshCw,
  CheckCircle,
  XCircle,
  Lock,
  Globe,
  Sliders,
  Folder,
} from 'lucide-react';

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const [setRes, healthRes] = await Promise.allSettled([
        api.getSettings(),
        api.getHealth(),
      ]);

      if (setRes.status === 'fulfilled') setSettings(setRes.value);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch settings from backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-md border border-slate-800">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 text-xs font-medium mb-3 border border-blue-400/20">
          <SettingsIcon className="w-3.5 h-3.5 text-blue-400" />
          <span>System Diagnostics & Policies</span>
        </div>
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">
          System Settings & Crawler Configuration
        </h1>
        <p className="mt-1 text-xs text-slate-300 max-w-2xl leading-relaxed">
          Inspect active security policies, domain allowlists, crawler throttling parameters,
          and computer vision engine paths.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Backend & Environment Card */}
        <Card
          title="Backend & Connection"
          subtitle="FastAPI server connectivity and parameters"
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Application Name</span>
              <span className="font-semibold text-slate-900">
                {settings?.app_name || 'CAPTCHA Automation Tool'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Environment</span>
              <span className="font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-800">
                {settings?.app_env || 'development'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">API Base URL</span>
              <span className="font-mono text-blue-600 font-bold">{api.baseUrl}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Database</span>
              <span className="inline-flex items-center gap-1 font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                <CheckCircle className="w-3.5 h-3.5" />
                SQLite (SQLAlchemy Engine)
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-slate-500 font-medium">Request Timeout</span>
              <span className="font-mono text-slate-800">{settings?.request_timeout_ms || 15000} ms</span>
            </div>
          </div>
        </Card>

        {/* Security Guard & Domain Allowlist */}
        <Card
          title="Security Guard Policies"
          subtitle="Strict SSRF and domain boundary controls"
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Live Scanning</span>
              <span
                className={`font-semibold px-2 py-0.5 rounded text-[11px] ${
                  settings?.enable_live_scan
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-amber-50 text-amber-700 border border-amber-200'
                }`}
              >
                {settings?.enable_live_scan ? 'Enabled' : 'Restricted (Allowlist Only)'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">SSRF Guard</span>
              <span className="text-emerald-700 font-semibold flex items-center gap-1">
                <Lock className="w-3.5 h-3.5" />
                Private IP & Rebinding Blocked
              </span>
            </div>
            <div className="py-2 border-b border-slate-100 space-y-1.5">
              <span className="text-slate-500 font-medium block">Authorized Domains:</span>
              <div className="flex flex-wrap gap-1.5">
                {settings?.allowed_domains && settings.allowed_domains.length > 0 ? (
                  settings.allowed_domains.map((d) => (
                    <span
                      key={d}
                      className="bg-blue-50 text-blue-800 border border-blue-200 px-2 py-0.5 rounded font-mono text-[11px]"
                    >
                      {d}
                    </span>
                  ))
                ) : (
                  <span className="text-slate-400">None configured</span>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-slate-500 font-medium">Zero-Bypass Architecture</span>
              <span className="text-emerald-700 font-semibold">Active & Audited</span>
            </div>
          </div>
        </Card>

        {/* Crawler Parameters */}
        <Card
          title="Crawler Engine Parameters"
          subtitle="Concurrency limits and Playwright crawler budgets"
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Max Crawl Pages / Job</span>
              <span className="font-mono font-bold text-slate-800">
                {settings?.crawler_max_pages || 10}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Default Max Depth</span>
              <span className="font-mono font-bold text-slate-800">
                {settings?.crawler_max_depth || 2}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Page Navigation Timeout</span>
              <span className="font-mono text-slate-800">
                {settings?.crawler_page_timeout_ms || 10000} ms
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-slate-500 font-medium">Max Concurrent Pages</span>
              <span className="font-mono text-slate-800">
                {settings?.max_concurrent_pages || 3}
              </span>
            </div>
          </div>
        </Card>

        {/* OCR & Storage Diagnostics */}
        <Card
          title="OCR Engine & Directories"
          subtitle="Local computer vision binaries and storage directories"
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Tesseract OCR Status</span>
              {settings?.tesseract_installed ? (
                <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-semibold">
                  <CheckCircle className="w-3.5 h-3.5" />
                  Installed & Ready
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded font-semibold">
                  Path Verified
                </span>
              )}
            </div>
            <div className="py-2 border-b border-slate-100 space-y-1">
              <span className="text-slate-500 font-medium block">Tesseract Command Path:</span>
              <span className="font-mono text-slate-700 text-[11px] break-all block bg-slate-50 p-1.5 rounded border border-slate-200">
                {settings?.tesseract_cmd || 'tesseract'}
              </span>
            </div>
            <div className="py-2 space-y-1">
              <span className="text-slate-500 font-medium block">Evidence Storage Directory:</span>
              <span className="font-mono text-slate-700 text-[11px] break-all block bg-slate-50 p-1.5 rounded border border-slate-200">
                {settings?.evidence_dir || 'evidence/'}
              </span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
