import {
  HealthResponse,
  SystemSettings,
  OverviewStats,
  UrlScan,
  UrlScanResultsResponse,
  DiscoveredPage,
  HumanReviewListResponse,
  HumanReviewRecord,
  BatchJob,
  BatchResultsResponse,
  CsvImportResult,
  OcrEvaluation,
  OcrBenchmarkResponse,
  CaptchaClassification,
} from './types';

// Default to backend on 127.0.0.1:8000
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    let errorData = null;
    try {
      errorData = await response.json();
      if (errorData?.detail) {
        errorDetail = typeof errorData.detail === 'string' 
          ? errorData.detail 
          : JSON.stringify(errorData.detail);
      } else if (errorData?.message) {
        errorDetail = errorData.message;
      }
    } catch {
      // Body is not JSON
    }
    throw new ApiError(response.status, errorDetail, errorData);
  }

  return response.json();
}

export const api = {
  baseUrl: API_BASE,

  // Health and System Diagnostics
  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  async getSettings(): Promise<SystemSettings> {
    return request<SystemSettings>('/api/websites/settings');
  },

  async getOverviewStats(): Promise<OverviewStats> {
    return request<OverviewStats>('/api/websites/overview-stats');
  },

  // Crawler and URL Inspection
  async inspectUrl(payload: {
    url: string;
    max_pages?: number;
    max_depth?: number;
    allow_loopback?: boolean;
    background?: boolean;
  }): Promise<{
    success: boolean;
    scan_id: string;
    status: string;
    submitted_url?: string;
    domain?: string;
    pages_crawled?: number;
    contact_pages_found?: number;
    captcha_detected?: boolean;
    captcha_providers?: string[];
    crawl_duration_ms?: number;
    results?: DiscoveredPage[];
    message?: string;
  }> {
    return request('/api/websites/inspect-url', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getScan(scanId: string): Promise<{ success: boolean; scan: UrlScan }> {
    return request<{ success: boolean; scan: UrlScan }>(`/api/websites/scans/${scanId}`);
  },

  async getScanResults(scanId: string): Promise<UrlScanResultsResponse> {
    return request<UrlScanResultsResponse>(`/api/websites/scans/${scanId}/results`);
  },

  async listScans(params: {
    limit?: number;
    offset?: number;
    status?: string;
  } = {}): Promise<{ success: boolean; total: number; scans: UrlScan[] }> {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', params.limit.toString());
    if (params.offset) q.set('offset', params.offset.toString());
    if (params.status) q.set('status', params.status);
    return request<{ success: boolean; total: number; scans: UrlScan[] }>(
      `/api/websites/scans?${q.toString()}`
    );
  },

  async listDiscoveredPages(params: {
    limit?: number;
    offset?: number;
    captcha_only?: boolean;
    provider?: string;
  } = {}): Promise<{ success: boolean; total: number; pages: DiscoveredPage[] }> {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', params.limit.toString());
    if (params.offset) q.set('offset', params.offset.toString());
    if (params.captcha_only !== undefined) q.set('captcha_only', params.captcha_only.toString());
    if (params.provider) q.set('provider', params.provider);
    return request<{ success: boolean; total: number; pages: DiscoveredPage[] }>(
      `/api/websites/pages?${q.toString()}`
    );
  },

  // Human Review Queue
  async listReviews(params: {
    status?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<HumanReviewListResponse> {
    const q = new URLSearchParams();
    if (params.status && params.status !== 'all') q.set('status', params.status);
    if (params.limit) q.set('limit', params.limit.toString());
    if (params.offset) q.set('offset', params.offset.toString());
    return request<HumanReviewListResponse>(`/api/captcha/reviews?${q.toString()}`);
  },

  async getReview(reviewId: number): Promise<{ success: boolean; review: HumanReviewRecord }> {
    return request<{ success: boolean; review: HumanReviewRecord }>(`/api/captcha/reviews/${reviewId}`);
  },

  async updateReview(
    reviewId: number,
    payload: {
      review_status: 'approved' | 'rejected' | 'manually_verified';
      reviewer_notes?: string;
      reviewer_id?: string;
    }
  ): Promise<{ success: boolean; message: string; review: HumanReviewRecord }> {
    return request(`/api/captcha/reviews/${reviewId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  // CSV Batch Management
  async uploadCsv(file: File, autoScan: boolean = false): Promise<CsvImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    return request<CsvImportResult>(`/api/websites/import?auto_scan=${autoScan}`, {
      method: 'POST',
      body: formData,
    });
  },

  async scanBatch(websites: Array<{ company_name: string; website_url: string }>): Promise<{
    success: boolean;
    batch_id: string;
    status: string;
    total_websites: number;
    message: string;
  }> {
    return request('/api/websites/scan-batch', {
      method: 'POST',
      body: JSON.stringify({ websites }),
    });
  },

  async getBatch(batchId: string): Promise<{ success: boolean; batch: BatchJob }> {
    return request<{ success: boolean; batch: BatchJob }>(`/api/websites/batches/${batchId}`);
  },

  async getBatchResults(batchId: string): Promise<BatchResultsResponse> {
    return request<BatchResultsResponse>(`/api/websites/batches/${batchId}/results`);
  },

  async listBatches(params: {
    limit?: number;
    offset?: number;
    status?: string;
  } = {}): Promise<{ success: boolean; total: number; batches: BatchJob[] }> {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', params.limit.toString());
    if (params.offset) q.set('offset', params.offset.toString());
    if (params.status) q.set('status', params.status);
    return request<{ success: boolean; total: number; batches: BatchJob[] }>(
      `/api/websites/batches?${q.toString()}`
    );
  },

  getBatchReportUrl(batchId: string): string {
    return `${API_BASE}/api/websites/batches/${batchId}/report`;
  },

  // OCR Laboratory
  async runOcrDemo(payload: {
    text?: string;
    add_noise?: boolean;
    noise_level?: string;
  } = {}): Promise<{ success: boolean; evaluation: OcrEvaluation }> {
    return request('/api/captcha/ocr-demo', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async runOcrBenchmark(payload: {
    samples?: number;
    noise_level?: string;
  } = {}): Promise<OcrBenchmarkResponse> {
    return request<OcrBenchmarkResponse>('/api/captcha/ocr-benchmark', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // CAPTCHA Classifier
  async classifyCaptcha(payload: {
    html: string;
    page_title?: string;
    base_domain?: string;
    screenshot_base64?: string;
  }): Promise<{ success: boolean; classification: CaptchaClassification }> {
    return request('/api/captcha/classify', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Token Verification
  async verifyToken(payload: {
    provider: string;
    token: string;
    remote_ip?: string;
  }): Promise<{
    success: boolean;
    verification: {
      provider: string;
      is_valid: boolean;
      score?: number;
      action?: string;
      hostname?: string;
      error_codes?: string[];
    };
  }> {
    return request('/api/captcha/verify-token', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Helper to format evidence/screenshot URL
  getScreenshotUrl(relPath: string | null): string | null {
    if (!relPath) return null;
    if (relPath.startsWith('http://') || relPath.startsWith('https://')) return relPath;
    const cleanPath = relPath.startsWith('/') ? relPath.slice(1) : relPath;
    return `${API_BASE}/${cleanPath}`;
  },
};
