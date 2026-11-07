'use client';

import React from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  subtitle?: string;
  trend?: string;
  badge?: React.ReactNode;
  accentColor?: 'blue' | 'purple' | 'emerald' | 'amber' | 'slate' | 'rose';
}

export function StatCard({
  title,
  value,
  icon,
  subtitle,
  trend,
  badge,
  accentColor = 'blue',
}: StatCardProps) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-600 border-blue-100',
    purple: 'bg-purple-50 text-purple-600 border-purple-100',
    emerald: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    amber: 'bg-amber-50 text-amber-600 border-amber-100',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
    rose: 'bg-rose-50 text-rose-600 border-rose-100',
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs hover:border-slate-300 transition-all">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">{title}</span>
        <div className={`p-2.5 rounded-lg border ${colorMap[accentColor]}`}>{icon}</div>
      </div>
      <div className="mt-3 flex items-baseline justify-between">
        <span className="text-2xl font-bold tracking-tight text-slate-900">{value}</span>
        {badge && <div>{badge}</div>}
      </div>
      {(subtitle || trend) && (
        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
          <span>{subtitle}</span>
          {trend && <span className="font-medium text-emerald-600">{trend}</span>}
        </div>
      )}
    </div>
  );
}
