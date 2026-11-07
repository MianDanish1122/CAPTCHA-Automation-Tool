'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { VerificationMode, VerificationResult, VerificationRow } from '@/lib/types';
import { ShieldCheck, FlaskConical, Ban, Server, RefreshCw } from 'lucide-react';

const PROVIDERS = [
  { value: 'google_recaptcha', label: 'Google reCAPTCHA' },
  { value: 'hcaptcha', label: 'hCaptcha' },
  { value: 'cloudflare_turnstile', label: 'Cloudflare Turnstile' },
];

// Official provider TEST secrets (public, published by the providers) -> real provider call
const TEST_SECRETS: Record<string, { label: string; secret?: string; token: string }[]> = {
  google_recaptcha: [{ label: 'Official test key (always passes)', token: 'any-test-token' }],
  hcaptcha: [{ label: 'Official test key (always passes)', token: '10000000-aaaa-bbbb-cccc-000000000001' }],
  cloudflare_turnstile: [
    { label: 'Official test key: always passes', secret: '1x0000000000000000000000000000000AA', token: 'XXXX.DUMMY.TOKEN.XXXX' },
    { label: 'Official test key: always fails', secret: '2x0000000000000000000000000000000AA', token: 'XXXX.DUMMY.TOKEN.XXXX' },
    { label: 'Official test key: token already spent', secret: '3x0000000000000000000000000000000AA', token: 'XXXX.DUMMY.TOKEN.XXXX' },
  ],
};

const SIMULATIONS = ['invalid', 'expired', 'reused', 'provider_down', 'provider_malformed'];

const MODE_STYLE: Record<VerificationMode, { label: string; cls: string; icon: React.ReactNode; blurb: string }> = {
  provider_live: {
    label: 'PROVIDER – REAL KEY',
    cls: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    icon: <Server className="w-4 h-4" />,
    blurb: 'The provider verified a token with an operator-supplied secret key.',
  },
  provider_test_keys: {
    label: 'PROVIDER – OFFICIAL TEST KEYS',
    cls: 'bg-blue-50 text-blue-800 border-blue-200',
    icon: <ShieldCheck className="w-4 h-4" />,
    blurb: 'The real provider endpoint answered, but test keys accept/reject any token by design. This shows the integration works; it is not proof that a human solved a production challenge.',
  },
  simulated: {
    label: 'SIMULATED – NO PROVIDER CALL',
    cls: 'bg-amber-50 text-amber-900 border-amber-200',
    icon: <FlaskConical className="w-4 h-4" />,
    blurb: 'Generated locally to demonstrate error handling. A simulation can never succeed.',
  },
  local_validation: {
    label: 'LOCAL VALIDATION – REJECTED BEFORE PROVIDER',
    cls: 'bg-slate-100 text-slate-800 border-slate-300',
    icon: <Ban className="w-4 h-4" />,
    blurb: 'The request was rejected by the server without contacting the provider.',
  },
};

function ModeBadge({ mode }: { mode: VerificationMode }) {
  const m = MODE_STYLE[mode];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[11px] font-bold ${m.cls}`}>
      {m.icon}
      {m.label}
    </span>
  );
}

export default function VerificationPage() {
  const [provider, setProvider] = useState('google_recaptcha');
  const [scenario, setScenario] = useState<string>('test:0');
  const [customToken, setCustomToken] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [records, setRecords] = useState<VerificationRow[]>([]);
  const [total, setTotal] = useState(0);

  const loadRecords = useCallback(async () => {
    try {
      const res = await api.listVerificationRecords(15);
      setRecords(res.records);
      setTotal(res.total);
    } catch {
      /* table is informational */
    }
  }, []);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const testOptions = TEST_SECRETS[provider] || [];

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      let payload: Parameters<typeof api.verifyToken>[0] = { provider };
      if (scenario.startsWith('test:')) {
        const opt = testOptions[Number(scenario.split(':')[1])] || testOptions[0];
        payload = { provider, token: customToken.trim() || opt.token, secret_key: opt.secret };
      } else if (scenario.startsWith('sim:')) {
        payload = { provider, token: customToken.trim() || 'simulated-token', simulate_status: scenario.slice(4) };
      } else if (scenario === 'missing') {
        payload = { provider, token: '' };
      } else if (scenario === 'bad-secret') {
        payload = { provider, token: customToken.trim() || 'some-token', secret_key: 'not-a-real-secret' };
      }
      setResult(await api.verifyToken(payload));
      loadRecords();
    } catch (err: any) {
      setError(err?.message || 'Verification request failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 text-white rounded-2xl p-6 border border-slate-800">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">Verification Results</h1>
        <p className="text-sm text-slate-300 mt-1 max-w-3xl">
          Server-side token verification against each provider&apos;s official <code>siteverify</code> endpoint.
          Every result states <b>how</b> it was produced – a real provider response, an official test-key response,
          a local simulation, or a local rejection. Nothing the browser asserts is accepted as proof.
        </p>
      </div>

      <form onSubmit={run} className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
        <div className="grid md:grid-cols-3 gap-4">
          <label className="text-xs font-semibold text-slate-600 space-y-1">
            Provider
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setScenario('test:0');
              }}
              className="block w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-normal"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-600 space-y-1 md:col-span-2">
            Scenario
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="block w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-normal"
            >
              <optgroup label="Real provider call – official TEST keys">
                {testOptions.map((o, i) => (
                  <option key={i} value={`test:${i}`}>{o.label}</option>
                ))}
              </optgroup>
              <optgroup label="Real provider call – invalid secret">
                <option value="bad-secret">Provider rejects an invalid secret/token (live response)</option>
              </optgroup>
              <optgroup label="Local validation (no provider call)">
                <option value="missing">Missing token</option>
              </optgroup>
              <optgroup label="Simulated failure (no provider call)">
                {SIMULATIONS.map((s) => (
                  <option key={s} value={`sim:${s}`}>Simulated: {s.replace('_', ' ')}</option>
                ))}
              </optgroup>
            </select>
          </label>
        </div>
        <label className="text-xs font-semibold text-slate-600 space-y-1 block">
          Token override (optional – paste only a token from a page YOU own or an official test widget)
          <input
            value={customToken}
            onChange={(e) => setCustomToken(e.target.value)}
            placeholder="leave empty to use the scenario's documented dummy token"
            className="block w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono font-normal"
          />
        </label>
        <button
          type="submit"
          disabled={running}
          className="inline-flex items-center gap-2 bg-slate-900 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-slate-700 disabled:opacity-50"
        >
          {running ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
          Run verification
        </button>
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </form>

      {result && (
        <div data-testid="verification-result" className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <ModeBadge mode={result.verification_mode} />
            <span
              className={`px-2 py-0.5 rounded-md text-xs font-bold ${
                result.provider_verified ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'
              }`}
            >
              {result.provider_verified ? 'CONFIRMED BY PROVIDER' : 'NOT VERIFIED'}
            </span>
            <span className="text-sm font-mono text-slate-700">{result.outcome}</span>
          </div>
          <p className="text-sm text-slate-600">{MODE_STYLE[result.verification_mode].blurb}</p>
          <dl className="grid sm:grid-cols-3 gap-x-6 gap-y-1 text-xs text-slate-600">
            <div><dt className="inline font-semibold">Provider called: </dt><dd className="inline">{String(result.provider_called)}</dd></div>
            <div><dt className="inline font-semibold">HTTP status: </dt><dd className="inline">{result.http_status ?? '–'}</dd></div>
            <div><dt className="inline font-semibold">Duration: </dt><dd className="inline">{result.duration_ms} ms</dd></div>
            <div><dt className="inline font-semibold">Error codes: </dt><dd className="inline">{result.error_codes.join(', ') || '–'}</dd></div>
            <div><dt className="inline font-semibold">Token source: </dt><dd className="inline">{result.token_source}</dd></div>
            <div><dt className="inline font-semibold">Hostname: </dt><dd className="inline">{result.hostname ?? '–'}</dd></div>
          </dl>
          <p className="text-xs text-slate-500">{result.message}</p>
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-2xl p-5">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-semibold text-slate-900">Recorded attempts</h2>
          <span className="text-xs text-slate-500">showing {records.length} of {total} recorded (tokens are never stored)</span>
        </div>
        {records.length === 0 ? (
          <p className="text-sm text-slate-500">No verification attempts recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2 pr-3">Time</th><th className="pr-3">Provider</th><th className="pr-3">Mode</th>
                  <th className="pr-3">Outcome</th><th className="pr-3">Provider called</th><th>Errors</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100">
                    <td className="py-2 pr-3 whitespace-nowrap">{r.created_at ? new Date(r.created_at + 'Z').toLocaleTimeString() : '–'}</td>
                    <td className="pr-3">{r.provider}</td>
                    <td className="pr-3"><ModeBadge mode={r.verification_mode} /></td>
                    <td className="pr-3 font-mono">{r.outcome}</td>
                    <td className="pr-3">{r.provider_called ? 'yes' : 'no'}</td>
                    <td className="font-mono">{r.error_codes.join(', ') || '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
