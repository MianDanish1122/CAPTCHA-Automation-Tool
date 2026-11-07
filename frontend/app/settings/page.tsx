'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { SystemSettings, HealthResponse, AuditLogItem } from '@/lib/types';
import { useAuth } from '@/lib/auth-context';
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
  UserCheck,
  FileText,
  Activity,
  KeyRound,
} from 'lucide-react';

export default function SettingsPage() {
  const { user, isAdmin } = useAuth();
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [loadingAudit, setLoadingAudit] = useState<boolean>(false);
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

  const fetchAuditLogs = async () => {
    if (!isAdmin) return;
    setLoadingAudit(true);
    try {
      const res = await api.listAuditLogs({ limit: 20 });
      if (res.logs) setAuditLogs(res.logs);
    } catch {
      // Audit logs fetch optional
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    if (isAdmin) {
      fetchAuditLogs();
    }
  }, [isAdmin]);

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
        {/* Authentication & Security Controls */}
        <Card
          title="Security & Session State"
          subtitle="JWT Authentication and Role-Based Access Controls"
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Active User</span>
              <span className="font-semibold text-slate-900 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                {user?.username} ({user?.email})
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Role Privilege Level</span>
              <span className="font-mono bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-bold uppercase text-[11px] border border-blue-200">
                {user?.role}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Token Scheme</span>
              <span className="font-mono text-slate-800">JWT (HS256) + Bcrypt Password Hash</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500 font-medium">Rate Limiting</span>
              <span className="inline-flex items-center gap-1 font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                <CheckCircle className="w-3.5 h-3.5" />
                Active (Token Bucket per IP)
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-slate-500 font-medium">Loopback Dev Setting</span>
              <span className="font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                Server-Controlled (Disabled in Prod)
              </span>
            </div>
          </div>
        </Card>

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
                SQLite (SQLAlchemy + Alembic Migrations)
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
              <span className="text-slate-500 font-medium">Browser Interception</span>
              <span className="text-emerald-700 font-semibold">Active (`page.route` SSRF Filter)</span>
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

      {/* Administrative Audit Trail Section (Admin Only) */}
      {isAdmin && (
        <Card
          title="Administrative Audit Trail (Immutable Security Logs)"
          subtitle="Cryptographically tracked security and operational events recorded in SQLite"
          action={
            <button
              onClick={fetchAuditLogs}
              disabled={loadingAudit}
              className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 font-medium cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingAudit ? 'animate-spin' : ''}`} />
              <span>Refresh Logs</span>
            </button>
          }
        >
          <div className="overflow-x-auto">
            {auditLogs.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">
                {loadingAudit ? 'Fetching audit records...' : 'No audit records found.'}
              </p>
            ) : (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                    <th className="py-2 px-3">Timestamp</th>
                    <th className="py-2 px-3">Actor</th>
                    <th className="py-2 px-3">Role</th>
                    <th className="py-2 px-3">Action</th>
                    <th className="py-2 px-3">Resource</th>
                    <th className="py-2 px-3">IP Address</th>
                    <th className="py-2 px-3">Request ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/80 font-mono text-[11px]">
                      <td className="py-2.5 px-3 text-slate-600 whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString()}
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-slate-900">
                        {log.actor_username || 'system'}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                          log.actor_role === 'admin'
                            ? 'bg-purple-50 text-purple-700 border border-purple-200'
                            : 'bg-blue-50 text-blue-700 border border-blue-200'
                        }`}>
                          {log.actor_role || 'anon'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-slate-800">
                        {log.action}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {log.resource_type} {log.resource_id ? `#${log.resource_id}` : ''}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">
                        {log.ip_address || '127.0.0.1'}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 text-[10px] max-w-[120px] truncate" title={log.request_id || ''}>
                        {log.request_id || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
