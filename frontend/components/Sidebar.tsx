'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Search,
  History,
  ShieldAlert,
  UserCheck,
  Cpu,
  Layers,
  FileText,
  Settings,
  Shield,
  ExternalLink,
  ChevronRight,
  Menu,
  X,
} from 'lucide-react';
import { api } from '@/lib/api';

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number | string;
}

export function Sidebar() {
  const pathname = usePathname();
  const [pendingReviews, setPendingReviews] = useState<number>(0);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    // Fetch pending review count for badge
    const fetchPendingCount = async () => {
      try {
        const stats = await api.getOverviewStats();
        if (stats && stats.pending_reviews !== undefined) {
          setPendingReviews(stats.pending_reviews);
        }
      } catch {
        // Backend not ready yet
      }
    };
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 15000);
    return () => clearInterval(interval);
  }, []);

  const navItems: NavItem[] = [
    { name: 'Overview', href: '/', icon: LayoutDashboard },
    { name: 'URL Inspector', href: '/inspector', icon: Search },
    { name: 'Scan History', href: '/scans', icon: History },
    { name: 'CAPTCHA Results', href: '/results', icon: ShieldAlert },
    {
      name: 'Human Review',
      href: '/reviews',
      icon: UserCheck,
      badge: pendingReviews > 0 ? pendingReviews : undefined,
    },
    { name: 'OCR Laboratory', href: '/ocr', icon: Cpu },
    { name: 'CSV Batch Manager', href: '/batch', icon: Layers },
    { name: 'Reports', href: '/reports', icon: FileText },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  return (
    <>
      {/* Mobile Toggle Button */}
      <div className="lg:hidden fixed top-3 left-3 z-50">
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="p-2 rounded-lg bg-slate-900 text-white shadow-md focus:outline-hidden"
          aria-label="Toggle navigation"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Backdrop for mobile */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar Content */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-40 w-64 bg-[#0f172a] text-slate-300 flex flex-col border-r border-slate-800 transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="h-16 px-6 flex items-center gap-3 border-b border-slate-800/80">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-wide text-white flex items-center gap-1.5">
              CAPTCHA <span className="text-blue-400 font-extrabold">INSPECTOR</span>
            </h1>
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">
              Technology Brainz v2.0
            </span>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Platform Menu
          </div>
          {navItems.map((item) => {
            const isActive =
              item.href === '/'
                ? pathname === '/'
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white font-semibold shadow-sm'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/70'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon
                    className={`w-4 h-4 ${
                      isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-300'
                    }`}
                  />
                  <span>{item.name}</span>
                </div>
                {item.badge !== undefined && (
                  <span
                    className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                      isActive ? 'bg-white text-blue-700' : 'bg-amber-500 text-slate-900'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Security & System Info Footer */}
        <div className="p-4 border-t border-slate-800/80 bg-slate-950/40 text-xs">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-slate-400 font-medium">Security Guard</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-800/50">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              SSRF Safe
            </span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Zero-Bypass Architecture. Live scanner enforces allowlist restrictions.
          </p>
          <div className="mt-3 pt-2.5 border-t border-slate-800/50 flex items-center justify-between text-[11px] text-slate-400 font-mono">
            <span>FastAPI: 8000</span>
            <a
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-blue-400 hover:text-blue-300 inline-flex items-center gap-0.5"
            >
              Docs <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </aside>
    </>
  );
}
