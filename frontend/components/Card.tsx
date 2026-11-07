'use client';

import React from 'react';

interface CardProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  headerClassName?: string;
}

export function Card({
  title,
  subtitle,
  action,
  children,
  className = '',
  bodyClassName = '',
  headerClassName = '',
}: CardProps) {
  const hasHeader = title || subtitle || action;

  return (
    <div className={`bg-white rounded-xl border border-slate-200/80 shadow-xs overflow-hidden ${className}`}>
      {hasHeader && (
        <div className={`px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-4 ${headerClassName}`}>
          <div>
            {title && <h3 className="font-semibold text-slate-900 text-base">{title}</h3>}
            {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={`p-6 ${bodyClassName}`}>{children}</div>
    </div>
  );
}
