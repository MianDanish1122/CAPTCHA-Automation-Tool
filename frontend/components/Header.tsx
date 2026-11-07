'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { api } from '@/lib/api';
import { HealthResponse } from '@/lib/types';
import {
  Activity,
  Plus,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Search,
  CheckCircle2,
} from 'lucide-react';

export function Header() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [checking, setChecking] = useState<boolean>(false);

  const checkHealth = async () => {
    setChecking(true);
    try {
      const data = await api.getHealth();
      setHealth(data);
      setIsOnline(true);
    } catch {
      setIsOnline(false);
      setHealth(null);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const getPageTitle = (path: string) => {
    if (path === '/') return 'System Overview Dashboard';
    if (path.startsWith('/inspector')) return 'Smart Website URL Inspector';
    if (path.startsWith('/scans')) return 'Inspection Scan History';
    if (path.startsWith('/results')) return 'CAPTCHA Intelligence Results';
    if (path.startsWith('/reviews')) return 'Human Review & Verification Center';
    if (path.startsWith('/ocr')) return 'Synthetic OCR Laboratory & Benchmarks';
    if (path.startsWith('/batch')) return 'CSV Batch Manager & Pipeline';
    if (path.startsWith('/reports')) return 'Audit Reports & Compliance Exports';
    if (path.startsWith('/settings')) return 'System Settings & Engine Diagnostics';
    return 'CAPTCHA Inspector';
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200/80 px-6 flex items-center justify-between sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900 leading-tight">
            {getPageTitle(pathname)}
          </h2>
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <span>Technology Brainz</span>
            <span>/</span>
            <span className="capitalize">{pathname === '/' ? 'Dashboard' : pathname.replace('/', '')}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Backend Status Indicator */}
        <div className="flex items-center gap-2">
          {isOnline === true ? (
            <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200/80 px-2.5 py-1 rounded-full text-xs font-medium text-emerald-800">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>FastAPI Connected</span>
              <span className="text-[10px] text-emerald-600 font-mono hidden sm:inline">127.0.0.1:8000</span>
            </div>
          ) : isOnline === false ? (
            <div className="flex items-center gap-2 bg-rose-50 border border-rose-200/80 px-2.5 py-1 rounded-full text-xs font-medium text-rose-800">
              <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
              <span>Backend Offline</span>
              <button
                onClick={checkHealth}
                className="hover:underline text-[10px] text-rose-600 font-semibold"
                title="Retry connection"
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-full text-xs font-medium text-slate-600">
              <RefreshCw className="w-3 h-3 animate-spin text-slate-400" />
              <span>Checking Backend...</span>
            </div>
          )}
        </div>

        {/* Quick Scan Action */}
        <Link
          href="/inspector"
          className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3.5 py-2 rounded-lg shadow-xs transition shadow-blue-500/10"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Inspection</span>
        </Link>
      </div>
    </header>
  );
}
