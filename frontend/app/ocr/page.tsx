'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { OcrBenchmarkResponse } from '@/lib/types';
import { Card } from '@/components/Card';
import { StatCard } from '@/components/StatCard';
import { Badge } from '@/components/Badge';
import {
  Cpu,
  Play,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Layers,
  Sparkles,
  BarChart3,
  Sliders,
  Shield,
  Zap,
} from 'lucide-react';

export default function OcrPage() {
  // Single Demo State
  const [customText, setCustomText] = useState('8K2MN');
  const [runningDemo, setRunningDemo] = useState(false);
  const [demoResult, setDemoResult] = useState<{
    ground_truth: string;
    ocr_prediction: string;
    exact_match: boolean;
    character_accuracy: number;
    confidence: number;
    execution_time_ms: number;
    ocr_engine: string;
    image_base64?: string;
    preprocessed_base64?: string;
    methodology?: Record<string, string>;
  } | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);

  // Benchmark Suite State
  const [benchmarkSamples, setBenchmarkSamples] = useState(5);
  const [runningBenchmark, setRunningBenchmark] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<OcrBenchmarkResponse | null>(null);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);

  const handleGenerateRandom = () => {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let text = '';
    for (let i = 0; i < 5; i++) {
      text += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setCustomText(text);
  };

  const handleRunDemo = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunningDemo(true);
    setDemoError(null);
    try {
      const res = await api.runOcrDemo({
        text: customText.trim() || undefined,
      });
      if (res.success) {
        setDemoResult((res as any) || res.evaluation);
      }
    } catch (err: any) {
      setDemoError(err?.message || 'Failed to execute synthetic OCR pipeline');
    } finally {
      setRunningDemo(false);
    }
  };

  const handleRunBenchmark = async () => {
    setRunningBenchmark(true);
    setBenchmarkError(null);
    try {
      const res = await api.runOcrBenchmark({
        samples: benchmarkSamples,
      });
      if (res.success) {
        setBenchmarkResult(res);
      }
    } catch (err: any) {
      setBenchmarkError(err?.message || 'Failed to execute OCR benchmark');
    } finally {
      setRunningBenchmark(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-md border border-slate-800">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 text-xs font-medium mb-3 border border-blue-400/20">
          <Cpu className="w-3.5 h-3.5 text-blue-400" />
          <span>Synthetic Text CAPTCHA Engine</span>
        </div>
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">
          OCR Laboratory & Computer Vision Preprocessing
        </h1>
        <p className="mt-1 text-xs text-slate-300 max-w-3xl leading-relaxed">
          Test synthetic text distortion recognition using OpenCV filters (Bilateral Smoothing, Otsu
          Adaptive Binarization, Morphological Opening) coupled with Tesseract LSTM OCR.
          Audited for owned/synthetic challenges only.
        </p>
      </div>

      {/* Grid: Interactive Demo & Pipeline */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Input & Control Panel */}
        <Card
          title="Synthetic Generator"
          subtitle="Generate controlled distorted challenges"
          className="lg:col-span-5"
        >
          <form onSubmit={handleRunDemo} className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Ground Truth Text
                </label>
                <button
                  type="button"
                  onClick={handleGenerateRandom}
                  className="text-xs font-medium text-blue-600 hover:text-blue-800 inline-flex items-center gap-1"
                >
                  <Sparkles className="w-3 h-3" />
                  Randomize
                </button>
              </div>
              <input
                type="text"
                maxLength={8}
                value={customText}
                onChange={(e) => setCustomText(e.target.value.toUpperCase())}
                placeholder="e.g. 8K2MN"
                className="w-full bg-slate-50 border border-slate-300 focus:bg-white text-slate-900 font-mono tracking-widest text-lg font-bold rounded-xl px-4 py-2.5 text-center focus:ring-2 focus:ring-blue-500 transition"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Pillow adds character rotation, noise arcs, and salt-and-pepper artifacts.
              </p>
            </div>

            <button
              type="submit"
              disabled={runningDemo}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-xs transition flex items-center justify-center gap-2 shadow-md shadow-blue-600/20"
            >
              {runningDemo ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Processing CV Pipeline...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>Run OCR Evaluation</span>
                </>
              )}
            </button>
          </form>

          {demoError && (
            <div className="mt-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{demoError}</span>
            </div>
          )}

          {/* Quick Metrics when result available */}
          {demoResult && (
            <div className="mt-5 pt-5 border-t border-slate-100 space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 font-medium">Exact Match:</span>
                {demoResult.exact_match ? (
                  <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded font-semibold text-[11px]">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Exact Match
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded font-semibold text-[11px]">
                    <XCircle className="w-3.5 h-3.5" />
                    Mismatch
                  </span>
                )}
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 font-medium">Character Accuracy:</span>
                <span className="font-bold text-slate-800 font-mono">
                  {demoResult.character_accuracy}%
                </span>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 font-medium">Execution Time:</span>
                <span className="font-mono text-slate-800">{demoResult.execution_time_ms} ms</span>
              </div>
            </div>
          )}
        </Card>

        {/* Right: Preprocessing & OCR Pipeline Visualizer */}
        <Card
          title="Computer Vision Pipeline & Verification"
          subtitle="Step-by-step image transformation before text extraction"
          className="lg:col-span-7"
        >
          {demoResult ? (
            <div className="space-y-5">
              {/* Image comparison grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Step 1: Raw image */}
                <div className="border border-slate-200 rounded-xl p-3 bg-slate-50 text-center space-y-2">
                  <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider block">
                    1. Distorted Input Image
                  </span>
                  <div className="bg-white p-2 rounded-lg border border-slate-200 flex items-center justify-center min-h-[90px]">
                    {demoResult.image_base64 ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={`data:image/png;base64,${demoResult.image_base64}`}
                        alt="Raw synthetic CAPTCHA"
                        className="max-h-16 object-contain rounded"
                      />
                    ) : (
                      <span className="text-xs text-slate-400">Image data unavailable</span>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-400 block">Pillow distortion & noise lines</span>
                </div>

                {/* Step 2: Cleaned image */}
                <div className="border border-slate-200 rounded-xl p-3 bg-slate-50 text-center space-y-2">
                  <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider block">
                    2. OpenCV Filtered Image
                  </span>
                  <div className="bg-white p-2 rounded-lg border border-slate-200 flex items-center justify-center min-h-[90px]">
                    {demoResult.preprocessed_base64 ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={`data:image/png;base64,${demoResult.preprocessed_base64}`}
                        alt="Preprocessed CAPTCHA"
                        className="max-h-16 object-contain rounded"
                      />
                    ) : (
                      <span className="text-xs text-slate-400">Preprocessed image</span>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-400 block">
                    Bilateral filter + Otsu binarization
                  </span>
                </div>
              </div>

              {/* Extraction Comparison Box */}
              <div className="p-4 bg-slate-900 text-white rounded-xl space-y-3">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block">
                      Ground Truth
                    </span>
                    <span className="text-xl font-mono font-bold text-emerald-400 tracking-wider">
                      {demoResult.ground_truth}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block">
                      Tesseract OCR Prediction
                    </span>
                    <span
                      className={`text-xl font-mono font-bold tracking-wider ${
                        demoResult.exact_match ? 'text-emerald-400' : 'text-amber-400'
                      }`}
                    >
                      {demoResult.ocr_prediction || '(Empty)'}
                    </span>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span>Engine: {demoResult.ocr_engine}</span>
                  <span>Confidence: {Math.round(demoResult.confidence * 100)}%</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-16 text-center text-slate-400 space-y-2">
              <Layers className="w-10 h-10 mx-auto text-slate-300" />
              <p className="text-sm font-medium">Ready to evaluate synthetic CAPTCHA</p>
              <p className="text-xs text-slate-400">
                Click &ldquo;Run OCR Evaluation&rdquo; to generate an image and visualize OpenCV transformations.
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* Benchmark Suite Section */}
      <Card
        title="Automated Synthetic Benchmark Suite"
        subtitle="Batch-evaluate OCR accuracy across randomized test sets"
        action={
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <span>Samples:</span>
              <select
                value={benchmarkSamples}
                onChange={(e) => setBenchmarkSamples(Number(e.target.value))}
                className="bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 text-xs font-semibold"
              >
                <option value={5}>5 Samples</option>
                <option value={10}>10 Samples</option>
                <option value={20}>20 Samples</option>
              </select>
            </div>

            <button
              onClick={handleRunBenchmark}
              disabled={runningBenchmark}
              className="bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-medium px-4 py-2 rounded-lg transition flex items-center gap-1.5"
            >
              {runningBenchmark ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Benchmarking...</span>
                </>
              ) : (
                <>
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>Run Benchmark</span>
                </>
              )}
            </button>
          </div>
        }
      >
        {benchmarkError && (
          <div className="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{benchmarkError}</span>
          </div>
        )}

        {benchmarkResult ? (
          <div className="space-y-6">
            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                <span className="text-[11px] font-semibold uppercase text-slate-400">Total Samples</span>
                <p className="text-xl font-bold text-slate-900 mt-1">{benchmarkResult.total_samples}</p>
              </div>
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                <span className="text-[11px] font-semibold uppercase text-slate-400">Exact Matches</span>
                <p className="text-xl font-bold text-emerald-600 mt-1">
                  {benchmarkResult.exact_matches} ({benchmarkResult.exact_match_rate_percent}%)
                </p>
              </div>
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                <span className="text-[11px] font-semibold uppercase text-slate-400">
                  Mean Char Accuracy
                </span>
                <p className="text-xl font-bold text-blue-600 mt-1">
                  {benchmarkResult.mean_character_accuracy}%
                </p>
              </div>
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                <span className="text-[11px] font-semibold uppercase text-slate-400">
                  Mean Time per Image
                </span>
                <p className="text-xl font-bold text-slate-900 mt-1 font-mono">
                  {benchmarkResult.mean_execution_time_ms} ms
                </p>
              </div>
            </div>

            {/* Itemized Benchmark Results Table */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-2">
                Sample Execution Breakdown
              </h4>
              <div className="overflow-x-auto border border-slate-200 rounded-xl">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                      <th className="py-2.5 px-3">#</th>
                      <th className="py-2.5 px-3">Ground Truth</th>
                      <th className="py-2.5 px-3">Predicted</th>
                      <th className="py-2.5 px-3">Accuracy</th>
                      <th className="py-2.5 px-3">Result</th>
                      <th className="py-2.5 px-3 text-right">Duration</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {benchmarkResult.results.map((row) => (
                      <tr key={row.sample_index} className="hover:bg-slate-50">
                        <td className="py-2 px-3 font-mono text-slate-400">{row.sample_index}</td>
                        <td className="py-2 px-3 font-mono font-bold text-slate-900">
                          {row.ground_truth}
                        </td>
                        <td className="py-2 px-3 font-mono text-slate-800">
                          {row.predicted_text || '<empty>'}
                        </td>
                        <td className="py-2 px-3 font-mono">{row.character_accuracy}%</td>
                        <td className="py-2 px-3">
                          {row.exact_match ? (
                            <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-semibold">
                              Pass
                            </span>
                          ) : (
                            <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded text-[11px]">
                              Partial
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-3 font-mono text-right text-slate-500">
                          {row.execution_time_ms}ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Technical Analysis Card */}
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-blue-600" />
                Architectural Limitations Analysis
              </h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                {benchmarkResult.technical_limitations_summary}
              </p>
            </div>
          </div>
        ) : (
          <div className="py-12 text-center text-slate-400">
            <BarChart3 className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p className="text-sm font-medium">No benchmark has been executed yet.</p>
            <p className="text-xs text-slate-400 mt-1">
              Select sample size and click &ldquo;Run Benchmark&rdquo; to test Tesseract LSTM accuracy.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
