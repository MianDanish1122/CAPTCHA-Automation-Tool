'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Badge } from './Badge';
import { ExternalLink, Copy, Check, Image as ImageIcon, Code, ShieldCheck } from 'lucide-react';

interface EvidenceViewerProps {
  pageUrl?: string;
  screenshotPath?: string | null;
  provider?: string | null;
  confidence?: number;
  evidence?: Record<string, any> | null;
  handlingStrategy?: string | null;
}

export function EvidenceViewer({
  pageUrl,
  screenshotPath,
  provider,
  confidence,
  evidence,
  handlingStrategy,
}: EvidenceViewerProps) {
  const [activeTab, setActiveTab] = useState<'screenshot' | 'tokens' | 'raw'>('screenshot');
  const [copied, setCopied] = useState(false);

  const screenshotApiPath = api.getScreenshotUrl(screenshotPath || null);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [screenshotFailed, setScreenshotFailed] = useState(false);

  // Screenshots require an authenticated request, so load them as a blob (never a public URL).
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setScreenshotUrl(null);
    setScreenshotFailed(false);
    if (screenshotApiPath) {
      api
        .fetchEvidenceObjectUrl(screenshotApiPath)
        .then((url) => {
          if (cancelled) {
            URL.revokeObjectURL(url);
          } else {
            objectUrl = url;
            setScreenshotUrl(url);
          }
        })
        .catch(() => {
          if (!cancelled) setScreenshotFailed(true);
        });
    }
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [screenshotApiPath]);

  const copyRawJson = () => {
    navigator.clipboard.writeText(JSON.stringify(evidence || {}, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const scripts = evidence?.scripts_found || evidence?.scripts || [];
  const selectors = evidence?.selectors_matched || [];
  const forms = evidence?.forms_found || [];

  return (
    <div className="space-y-4">
      {/* Header Info Banner */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Provider:</span>
            <Badge variant="provider" value={provider} />
            {confidence !== undefined && (
              <span className="text-xs bg-slate-200/80 text-slate-700 px-2 py-0.5 rounded-full font-mono">
                {Math.round(confidence * 100)}% Confidence
              </span>
            )}
          </div>
          {pageUrl && (
            <div className="flex items-center gap-1.5 text-xs text-slate-600 font-mono break-all">
              <span className="text-slate-400">URL:</span>
              <a
                href={pageUrl}
                target="_blank"
                rel="noreferrer"
                className="text-blue-600 hover:underline inline-flex items-center gap-1"
              >
                {pageUrl}
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
        </div>

        {handlingStrategy && (
          <div className="text-right">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
              Handling Strategy
            </span>
            <span className="text-xs font-medium text-slate-800 bg-white border border-slate-200 px-2.5 py-1 rounded-md inline-block mt-0.5">
              {handlingStrategy}
            </span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 text-sm font-medium">
        <button
          onClick={() => setActiveTab('screenshot')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 transition ${
            activeTab === 'screenshot'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <ImageIcon className="w-4 h-4" />
          Screenshot Evidence
        </button>
        <button
          onClick={() => setActiveTab('tokens')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 transition ${
            activeTab === 'tokens'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          Detected Tokens ({scripts.length + selectors.length})
        </button>
        <button
          onClick={() => setActiveTab('raw')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 transition ${
            activeTab === 'raw'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <Code className="w-4 h-4" />
          Raw JSON Evidence
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'screenshot' && (
        <div className="space-y-2">
          {screenshotApiPath && screenshotFailed ? (
            <div className="border border-slate-200 rounded-xl p-8 text-center text-slate-400 bg-slate-900">
              <p className="text-sm font-medium">Screenshot not available</p>
              <p className="text-xs text-slate-500 mt-1 font-mono">{screenshotPath}</p>
            </div>
          ) : screenshotUrl ? (
            <div className="border border-slate-200 rounded-xl overflow-hidden bg-slate-900 flex items-center justify-center p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={screenshotUrl}
                alt="Page inspection screenshot"
                className="max-h-[420px] w-auto object-contain rounded shadow-lg"
              />
            </div>
          ) : screenshotApiPath ? (
            <div className="border border-slate-200 rounded-xl p-8 text-center text-slate-400 bg-slate-900 text-sm">
              Loading screenshot…
            </div>
          ) : (
            <div className="border border-dashed border-slate-300 rounded-xl p-12 text-center text-slate-400">
              <ImageIcon className="w-8 h-8 mx-auto mb-2 text-slate-300" />
              <p className="text-sm font-medium">No screenshot captured for this inspection.</p>
              <p className="text-xs text-slate-400 mt-1">
                Screenshots are captured automatically for contact and form-containing pages.
              </p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'tokens' && (
        <div className="space-y-4">
          <div>
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Matched Script Identifiers ({scripts.length})
            </h4>
            {scripts.length > 0 ? (
              <div className="space-y-1.5">
                {scripts.map((script: string, idx: number) => (
                  <div
                    key={idx}
                    className="p-2 bg-slate-50 border border-slate-200 rounded font-mono text-xs text-slate-800 break-all"
                  >
                    {script}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">No third-party challenge scripts detected.</p>
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Matched DOM / Selector Tokens ({selectors.length})
            </h4>
            {selectors.length > 0 ? (
              <div className="space-y-1.5">
                {selectors.map((sel: string, idx: number) => (
                  <div
                    key={idx}
                    className="p-2 bg-blue-50/50 border border-blue-200/80 rounded font-mono text-xs text-blue-900 break-all"
                  >
                    {sel}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">No widget container selectors found in DOM.</p>
            )}
          </div>

          {Array.isArray(forms) && forms.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Discovered Forms ({forms.length})
              </h4>
              <div className="space-y-2">
                {forms.map((form: any, idx: number) => (
                  <div key={idx} className="p-3 bg-white border border-slate-200 rounded-lg text-xs space-y-1">
                    <div className="font-semibold text-slate-800">
                      Form #{idx + 1} — Method: {form.method || 'GET'}, Action: {form.action || 'self'}
                    </div>
                    {form.inputs && (
                      <div className="text-slate-600 font-mono">
                        Inputs: {Array.isArray(form.inputs) ? form.inputs.join(', ') : JSON.stringify(form.inputs)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'raw' && (
        <div className="relative">
          <button
            onClick={copyRawJson}
            className="absolute top-2 right-2 bg-slate-800 hover:bg-slate-700 text-white text-xs px-2.5 py-1.5 rounded flex items-center gap-1.5 transition z-10"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Copied' : 'Copy JSON'}
          </button>
          <pre className="bg-slate-900 text-slate-200 p-4 rounded-xl text-xs font-mono overflow-x-auto max-h-[400px]">
            {JSON.stringify(evidence || {}, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
