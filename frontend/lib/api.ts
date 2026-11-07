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
  UserProfile,
  LoginResponse,
  AuditLogItem,
} from './types';

// Default to backend on 127.0.0.1:8000
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('captcha_token');
}

export function setStoredToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  if (token) {
    localStorage.setItem('captcha_token', token);
  } else {
    localStorage.removeItem('captcha_token');
    localStorage.removeItem('captcha_user');
  }
}

export function getStoredUser(): UserProfile | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem('captcha_user');
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setStoredUser(user: UserProfile | null): void {
  if (typeof window === 'undefined') return;
  if (user) {
    localStorage.setItem('captcha_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('captcha_user');
  }
}

function generateRequestId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export class ApiError extends Error {
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

  // Auto-inject JWT token if available
  if (!headers.has('Authorization')) {
    const token = getStoredToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  // Auto-inject correlation request ID for distributed tracing
  if (!headers.has('X-Request-ID')) {
    headers.set('X-Request-ID', generateRequestId());
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && !endpoint.includes('/api/auth/login')) {
      // Clear token upon session invalidation
      setStoredToken(null);
      setStoredUser(null);
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login?expired=1';
      }
    }

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
    // Detailed diagnostics require a session; the public /health probe reveals only liveness.
    try {
      return await request<HealthResponse>('/api/health/details');
    } catch {
      return request<HealthResponse>('/health');
    }
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

  // Authentication & Session Management
  async login(payload: { username: string; password: string }): Promise<LoginResponse> {
    const res = await request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.access_token) {
      setStoredToken(res.access_token);
      setStoredUser(res.user);
    }
    return res;
  },

  async logout(): Promise<{ success: boolean }> {
    try {
      await request('/api/auth/logout', { method: 'POST' });
    } catch {
      // Ignore network errors on logout
    } finally {
      setStoredToken(null);
      setStoredUser(null);
    }
    return { success: true };
  },

  async getMe(): Promise<{ success: boolean; user: UserProfile }> {
    return request<{ success: boolean; user: UserProfile }>('/api/auth/me');
  },

  async listAuditLogs(params: {
    limit?: number;
    offset?: number;
    action?: string;
    actor_username?: string;
  } = {}): Promise<{ success: boolean; total: number; logs: AuditLogItem[] }> {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', params.limit.toString());
    if (params.offset) q.set('offset', params.offset.toString());
    if (params.action) q.set('action', params.action);
    if (params.actor_username) q.set('actor_username', params.actor_username);
    return request<{ success: boolean; total: number; logs: AuditLogItem[] }>(
      `/api/auth/audit-logs?${q.toString()}`
    );
  },

  async createUser(payload: {
    username: string;
    email: string;
    password: string;
    role: 'admin' | 'operator';
  }): Promise<{ success: boolean; user: UserProfile }> {
    return request<{ success: boolean; user: UserProfile }>('/api/auth/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Evidence is served only to authenticated sessions, so an <img src> cannot load it directly.
  // Returns the API path for a stored relative path ("evidence/scans/<id>/<file>.png").
  getScreenshotUrl(relPath: string | null): string | null {
    if (!relPath) return null;
    if (relPath.startsWith('http://') || relPath.startsWith('https://')) return null;
    let clean = relPath.startsWith('/') ? relPath.slice(1) : relPath;
    if (clean.startsWith('evidence/')) clean = clean.slice('evidence/'.length);
    return `/api/evidence/${clean}`;
  },

  // Fetch a screenshot with the session token and return a temporary object URL.
  async fetchEvidenceObjectUrl(apiPath: string): Promise<string> {
    const headers = new Headers();
    const token = getStoredToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(`${API_BASE}${apiPath}`, { headers });
    if (!response.ok) {
      throw new ApiError(response.status, 'Evidence not available');
    }
    return URL.createObjectURL(await response.blob());
  },
};
