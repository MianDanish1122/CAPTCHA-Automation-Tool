'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { BatchJob, OverviewStats } from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { StatCard } from '@/components/StatCard';
import {
  FileText,
  Download,
  RefreshCw,
  CheckCircle,
  FileSpreadsheet,
  Clock,
  ShieldCheck,
  ExternalLink,
  Layers,
} from 'lucide-react';

export default function ReportsPage() {
  const [batches, setBatches] = useState<BatchJob[]>([]);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const [batchRes, statsRes] = await Promise.allSettled([
        api.listBatches({ limit: 50 }),
        api.getOverviewStats(),
      ]);

      if (batchRes.status === 'fulfilled' && batchRes.value.success) {
        setBatches(batchRes.value.batches);
      }
      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value);
      }
    } catch {
      // Backend error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-md border border-slate-800">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 text-xs font-medium mb-3 border border-blue-400/20">
          <FileText className="w-3.5 h-3.5 text-blue-400" />
          <span>Audit & Compliance Center</span>
        </div>
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">
          Inspection Reports & Compliance Exports
        </h1>
        <p className="mt-1 text-xs text-slate-300 max-w-2xl leading-relaxed">
          Download standardized CSV compliance logs for audits, evidence records, and
          security assessment reporting. All data is verified and timestamped.
        </p>
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Total Audit Batches"
          value={batches.length}
          icon={<Layers className="w-5 h-5" />}
          subtitle="Processed batch jobs"
          accentColor="blue"
        />
        <StatCard
          title="Verified Clean Sites"
          value={stats ? stats.total_pages - stats.total_captchas : 0}
          icon={<ShieldCheck className="w-5 h-5" />}
          subtitle="Zero challenge markers"
          accentColor="emerald"
        />
        <StatCard
          title="CAPTCHAs Documented"
          value={stats?.total_captchas ?? 0}
          icon={<FileSpreadsheet className="w-5 h-5" />}
          subtitle="All active challenges"
          accentColor="purple"
        />
      </div>

      {/* Batches Table with Direct CSV Download */}
      <Card
        title={`Audit Report Archive (${batches.length})`}
        subtitle="Click download to export official CSV compliance reports"
        action={
          <button
            onClick={fetchReports}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition"
            title="Refresh reports"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        }
      >
        {loading ? (
          <div className="py-16 text-center text-slate-400 flex flex-col items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin mb-2 text-blue-500" />
            <p className="text-xs">Fetching report archives...</p>
          </div>
        ) : batches.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <FileSpreadsheet className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p className="text-sm font-medium">No batch reports available yet.</p>
            <p className="text-xs text-slate-400 mt-1">
              Import a CSV file in CSV Batch Manager to generate your first audit report.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-3">Batch ID</th>
                  <th className="py-3 px-2">Status</th>
                  <th className="py-3 px-2">Processed / Total</th>
                  <th className="py-3 px-2">Created</th>
                  <th className="py-3 px-2">Completed</th>
                  <th className="py-3 px-3 text-right">Download Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {batches.map((b) => (
                  <tr key={b.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3 px-3 font-mono font-semibold text-slate-900">
                      {b.id.slice(0, 12)}...
                    </td>
                    <td className="py-3 px-2">
                      <Badge variant="status" value={b.status} size="sm" />
                    </td>
                    <td className="py-3 px-2 font-mono font-medium">
                      {b.processed_records} / {b.total_records}
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-[11px] whitespace-nowrap">
                      {new Date(b.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-[11px] whitespace-nowrap">
                      {b.completed_at ? new Date(b.completed_at).toLocaleString() : '-'}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <a
                        href={api.getBatchReportUrl(b.id)}
                        download
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-900 hover:text-white bg-slate-100 hover:bg-slate-900 px-3 py-1.5 rounded-lg transition shadow-xs"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Export CSV</span>
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
