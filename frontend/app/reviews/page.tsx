'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { HumanReviewRecord } from '@/lib/types';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { EvidenceViewer } from '@/components/EvidenceViewer';
import {
  UserCheck,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Search,
  ExternalLink,
  ShieldAlert,
  Clock,
  MessageSquare,
  User,
  ShieldCheck,
} from 'lucide-react';

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<HumanReviewRecord[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Active Review in Modal
  const [selectedReview, setSelectedReview] = useState<HumanReviewRecord | null>(null);
  const [reviewerNotes, setReviewerNotes] = useState<string>('');
  const [reviewerId, setReviewerId] = useState<string>('operator-admin');
  const [updating, setUpdating] = useState<boolean>(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchReviews = async () => {
    setLoading(true);
    try {
      const res = await api.listReviews({
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      if (res.success) {
        setReviews(res.reviews);
        setTotal(res.total);
      }
    } catch {
      // Backend error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
  }, [statusFilter]);

  const handleOpenReview = (rev: HumanReviewRecord) => {
    setSelectedReview(rev);
    setReviewerNotes(rev.reviewer_notes || '');
    setReviewerId(rev.reviewer_id || 'operator-admin');
    setActionSuccess(null);
    setActionError(null);
  };

  const handleUpdateStatus = async (
    newStatus: 'approved' | 'rejected' | 'manually_verified'
  ) => {
    if (!selectedReview) return;
    setUpdating(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      const res = await api.updateReview(selectedReview.id, {
        review_status: newStatus,
        reviewer_notes: reviewerNotes.trim() || undefined,
        reviewer_id: reviewerId.trim() || undefined,
      });

      if (res.success) {
        setActionSuccess(`Review #${selectedReview.id} updated to "${newStatus}".`);
        setSelectedReview(res.review);
        // Refresh review list in background
        fetchReviews();
      }
    } catch (err: any) {
      setActionError(err?.message || 'Failed to update review status.');
    } finally {
      setUpdating(false);
    }
  };

  const filteredReviews = reviews.filter((r) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      r.target_url.toLowerCase().includes(term) ||
      r.provider.toLowerCase().includes(term) ||
      (r.challenge_type && r.challenge_type.toLowerCase().includes(term))
    );
  });

  return (
    <div className="space-y-6">
      {/* Overview Alert Banner */}
      <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-md border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 text-xs font-medium mb-2 border border-blue-400/20">
            <UserCheck className="w-3.5 h-3.5 text-blue-400" />
            <span>Human-in-the-Loop Verification</span>
          </div>
          <h2 className="text-xl font-bold tracking-tight">Operator Human Review Center</h2>
          <p className="mt-1 text-xs text-slate-300 max-w-2xl leading-relaxed">
            Audit high-risk CAPTCHAs, third-party challenges, and ambiguous form markers.
            In compliance with our Zero-Bypass policy, external challenges require human verification.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">
              Pending Queue
            </span>
            <span className="text-2xl font-bold text-amber-400 font-mono">
              {reviews.filter((r) => r.review_status === 'pending').length}
            </span>
          </div>
        </div>
      </div>

      {/* Filter and Tab Controls */}
      <Card>
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="relative w-full md:w-96">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search by URL or Challenge..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-xl pl-10 pr-4 py-2 text-xs placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500 transition"
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto justify-end">
            <div className="flex bg-slate-100 p-1 rounded-xl text-xs font-medium overflow-x-auto">
              {[
                { id: 'pending', label: 'Needs Review' },
                { id: 'approved', label: 'Approved' },
                { id: 'rejected', label: 'Rejected' },
                { id: 'manually_verified', label: 'Verified' },
                { id: 'all', label: 'All' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setStatusFilter(tab.id)}
                  className={`px-3 py-1.5 rounded-lg whitespace-nowrap transition ${
                    statusFilter === tab.id
                      ? 'bg-white text-slate-900 shadow-xs font-semibold'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <button
              onClick={fetchReviews}
              className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition"
              title="Refresh reviews"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </Card>

      {/* Review Queue Table */}
      <Card
        title={`Review Queue Items (${filteredReviews.length})`}
        subtitle="Flagged challenges requiring human operator validation"
      >
        {loading ? (
          <div className="py-16 text-center text-slate-400 flex flex-col items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin mb-2 text-blue-500" />
            <p className="text-xs">Loading review records...</p>
          </div>
        ) : filteredReviews.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <ShieldCheck className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p className="text-sm font-medium">No reviews in this queue.</p>
            <p className="text-xs text-slate-400 mt-1">
              Select another status filter or crawl a website with active CAPTCHAs.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-3">Target URL</th>
                  <th className="py-3 px-2">Provider</th>
                  <th className="py-3 px-2">Challenge Type</th>
                  <th className="py-3 px-2">Confidence</th>
                  <th className="py-3 px-2">Handling Policy</th>
                  <th className="py-3 px-2">Review Status</th>
                  <th className="py-3 px-2">Discovered</th>
                  <th className="py-3 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filteredReviews.map((rev) => (
                  <tr key={rev.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3 px-3 max-w-[280px]">
                      <div className="font-semibold text-slate-900 truncate font-mono text-[11px]">
                        {rev.target_url}
                      </div>
                      <span className="text-[10px] text-slate-400">Review ID: #{rev.id}</span>
                    </td>
                    <td className="py-3 px-2">
                      <Badge variant="provider" value={rev.provider} size="sm" />
                    </td>
                    <td className="py-3 px-2 font-mono text-slate-800 text-[11px]">
                      {rev.challenge_type}
                    </td>
                    <td className="py-3 px-2 font-mono font-medium">
                      {typeof rev.confidence_score === 'number' ? `${Math.round(rev.confidence_score * 100)}%` : '-'}
                    </td>
                    <td className="py-3 px-2">
                      <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px] font-mono">
                        {rev.handling_strategy}
                      </span>
                    </td>
                    <td className="py-3 px-2">
                      <Badge variant="review" value={rev.review_status} size="sm" />
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-[11px] whitespace-nowrap">
                      {new Date(rev.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => handleOpenReview(rev)}
                        className={`inline-flex items-center gap-1 text-xs font-semibold px-3 py-1 rounded-md transition ${
                          rev.review_status === 'pending'
                            ? 'bg-amber-500 hover:bg-amber-600 text-white shadow-xs'
                            : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                        }`}
                      >
                        <UserCheck className="w-3.5 h-3.5" />
                        <span>{rev.review_status === 'pending' ? 'Review Now' : 'Inspect'}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Review Modal */}
      {selectedReview && (
        <Modal
          isOpen={!!selectedReview}
          onClose={() => setSelectedReview(null)}
          title={`Human Review: #${selectedReview.id} (${selectedReview.provider})`}
          subtitle={selectedReview.target_url}
          maxWidth="4xl"
          footer={
            <div className="flex items-center justify-between w-full">
              <span className="text-xs text-slate-400">
                Status: <Badge variant="review" value={selectedReview.review_status} size="sm" />
              </span>
              <button
                onClick={() => setSelectedReview(null)}
                className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-medium"
              >
                Close
              </button>
            </div>
          }
        >
          <div className="space-y-6">
            {/* Feedback notifications */}
            {actionSuccess && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{actionSuccess}</span>
              </div>
            )}
            {actionError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{actionError}</span>
              </div>
            )}

            {/* Operator Actions Card */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-4">
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-blue-600" />
                Operator Decision & Audit Trail
              </h4>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase mb-1">
                    Reviewer ID
                  </label>
                  <div className="relative">
                    <User className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      value={reviewerId}
                      onChange={(e) => setReviewerId(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-800 focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase mb-1">
                    Last Updated
                  </label>
                  <div className="text-xs font-mono text-slate-700 bg-white border border-slate-200 rounded-lg px-3 py-1.5">
                    {selectedReview.updated_at
                      ? new Date(selectedReview.updated_at).toLocaleString()
                      : 'Never'}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase mb-1">
                  Operator Audit Notes
                </label>
                <textarea
                  rows={2}
                  placeholder="Record reasoning, inspection notes, or verification details..."
                  value={reviewerNotes}
                  onChange={(e) => setReviewerNotes(e.target.value)}
                  className="w-full bg-white border border-slate-300 rounded-lg p-3 text-xs text-slate-800 placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  disabled={updating}
                  onClick={() => handleUpdateStatus('manually_verified')}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium px-4 py-2 rounded-lg flex items-center gap-1.5 transition shadow-xs"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>Mark Manually Verified</span>
                </button>

                <button
                  type="button"
                  disabled={updating}
                  onClick={() => handleUpdateStatus('approved')}
                  className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-medium px-4 py-2 rounded-lg flex items-center gap-1.5 transition shadow-xs"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Approve Exception</span>
                </button>

                <button
                  type="button"
                  disabled={updating}
                  onClick={() => handleUpdateStatus('rejected')}
                  className="bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-medium px-4 py-2 rounded-lg flex items-center gap-1.5 transition shadow-xs"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  <span>Reject / False Positive</span>
                </button>
              </div>
            </div>

            {/* Evidence Viewer */}
            <EvidenceViewer
              pageUrl={selectedReview.target_url}
              screenshotPath={selectedReview.evidence?.screenshot_path || null}
              provider={selectedReview.provider}
              confidence={typeof selectedReview.confidence_score === 'number' ? selectedReview.confidence_score : undefined}
              evidence={selectedReview.evidence}
              handlingStrategy={selectedReview.handling_strategy}
            />
          </div>
        </Modal>
      )}
    </div>
  );
}
