'use client';

import React from 'react';
import { CaptchaProvider, ReviewStatus, ScanStatus, BatchStatus } from '@/lib/types';

interface BadgeProps {
  children?: React.ReactNode;
  variant?: 'default' | 'provider' | 'status' | 'review';
  value?: string | null;
  size?: 'sm' | 'md';
  className?: string;
}

export function Badge({
  children,
  variant = 'default',
  value,
  size = 'md',
  className = '',
}: BadgeProps) {
  const displayVal = value ?? (typeof children === 'string' ? children : '');

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-medium';

  // Format provider names
  const getProviderConfig = (provider?: string | null) => {
    switch (provider) {
      case 'google_recaptcha':
        return { label: 'Google reCAPTCHA', classes: 'bg-blue-50 text-blue-700 border-blue-200' };
      case 'hcaptcha':
        return { label: 'hCaptcha', classes: 'bg-purple-50 text-purple-700 border-purple-200' };
      case 'cloudflare_turnstile':
        return { label: 'Cloudflare Turnstile', classes: 'bg-amber-50 text-amber-700 border-amber-200' };
      case 'synthetic_text_captcha':
        return { label: 'Synthetic Text OCR', classes: 'bg-teal-50 text-teal-700 border-teal-200' };
      case 'no_captcha':
        return { label: 'No CAPTCHA', classes: 'bg-slate-100 text-slate-600 border-slate-200' };
      case 'unknown_challenge':
        return { label: 'Unknown Challenge', classes: 'bg-rose-50 text-rose-700 border-rose-200' };
      default:
        return { label: provider || 'Unknown', classes: 'bg-gray-100 text-gray-700 border-gray-200' };
    }
  };

  // Format status tags
  const getStatusConfig = (status?: string | null) => {
    switch (status) {
      case 'completed':
        return { label: 'Completed', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
      case 'crawling':
      case 'running':
        return { label: 'Running...', classes: 'bg-sky-50 text-sky-700 border-sky-200 animate-pulse' };
      case 'queued':
      case 'pending':
        return { label: 'Pending', classes: 'bg-amber-50 text-amber-700 border-amber-200' };
      case 'failed':
      case 'partial_failure':
        return { label: 'Failed', classes: 'bg-rose-50 text-rose-700 border-rose-200' };
      default:
        return { label: status || 'Unknown', classes: 'bg-slate-100 text-slate-700 border-slate-200' };
    }
  };

  // Format review status
  const getReviewConfig = (rev?: string | null) => {
    switch (rev) {
      case 'pending':
        return { label: 'Needs Review', classes: 'bg-amber-50 text-amber-800 border-amber-300 font-semibold' };
      case 'approved':
        return { label: 'Approved Bypass', classes: 'bg-emerald-50 text-emerald-800 border-emerald-200' };
      case 'rejected':
        return { label: 'Rejected', classes: 'bg-rose-50 text-rose-800 border-rose-200' };
      case 'manually_verified':
        return { label: 'Manually Verified', classes: 'bg-blue-50 text-blue-800 border-blue-200' };
      default:
        return { label: rev || 'Unreviewed', classes: 'bg-slate-100 text-slate-600 border-slate-200' };
    }
  };

  let style = 'bg-slate-100 text-slate-800 border-slate-200';
  let labelText: React.ReactNode = children || displayVal;

  if (variant === 'provider') {
    const cfg = getProviderConfig(displayVal);
    style = cfg.classes;
    if (!children) labelText = cfg.label;
  } else if (variant === 'status') {
    const cfg = getStatusConfig(displayVal);
    style = cfg.classes;
    if (!children) labelText = cfg.label;
  } else if (variant === 'review') {
    const cfg = getReviewConfig(displayVal);
    style = cfg.classes;
    if (!children) labelText = cfg.label;
  }

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-medium ${sizeClasses} ${style} ${className}`}
    >
      {labelText}
    </span>
  );
}
