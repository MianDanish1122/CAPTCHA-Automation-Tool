// TypeScript type definitions for Technology Brainz - CAPTCHA Inspector

export type CaptchaProvider =
  | 'no_captcha'
  | 'synthetic_text_captcha'
  | 'google_recaptcha'
  | 'hcaptcha'
  | 'cloudflare_turnstile'
  | 'unknown_challenge'
  | string;

export type ScanStatus = 'pending' | 'running' | 'crawling' | 'completed' | 'failed';

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'manually_verified';

export type BatchStatus = 'queued' | 'running' | 'completed' | 'failed' | 'partial_failure';

export interface HealthResponse {
  status: string;
  service?: string;
  version?: string;
  database?: string;
  database_connected?: boolean;
  ocr_engine?: string;
  tesseract_installed?: boolean;
  live_scan_enabled?: boolean;
  allowed_domains?: string[];
}

export interface SystemSettings {
  success: boolean;
  app_name: string;
  app_env: string;
  debug: boolean;
  host: string;
  port: number;
  enable_live_scan: boolean;
  allowed_domains: string[];
  request_timeout_ms: number;
  max_concurrent_pages: number;
  crawler_max_pages: number;
  crawler_max_depth: number;
  crawler_page_timeout_ms: number;
  crawler_total_timeout_sec: number;
  tesseract_cmd: string;
  tesseract_installed: boolean;
  reports_dir: string;
  evidence_dir: string;
}

export interface OverviewStats {
  success: boolean;
  total_scans: number;
  total_pages: number;
  total_captchas: number;
  pending_reviews: number;
  total_batches: number;
  provider_breakdown: Record<string, number>;
  recent_scans: UrlScan[];
}

export interface DiscoveredPage {
  id: number;
  scan_id: string;
  url: string;
  path: string;
  title: string | null;
  depth: number;
  status_code: number;
  content_type: string | null;
  is_contact_page: boolean;
  contact_confidence: number;
  forms_found_count: number;
  captcha_detected: boolean;
  captcha_provider: CaptchaProvider | null;
  captcha_confidence: number;
  handling_strategy: string | null;
  human_review_required: boolean;
  review_status: ReviewStatus;
  screenshot_path: string | null;
  evidence: Record<string, any>;
  created_at: string;
}

export interface UrlScan {
  id: string;
  submitted_url: string;
  domain: string;
  canonical_url: string | null;
  status: ScanStatus;
  pages_crawled: number;
  contact_pages_found: number;
  captcha_detected: boolean;
  captcha_providers: string[];
  crawl_duration_ms: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface UrlScanResultsResponse {
  success: boolean;
  scan_id: string;
  status: ScanStatus;
  submitted_url: string;
  domain: string;
  pages_crawled: number;
  contact_pages_found: number;
  captcha_detected: boolean;
  captcha_providers: string[];
  crawl_duration_ms: number;
  results: DiscoveredPage[];
}

export interface HumanReviewRecord {
  id: number;
  scan_id: string | null;
  discovered_page_id: number | null;
  target_url: string;
  provider: CaptchaProvider;
  challenge_type: string;
  confidence_score: number;
  handling_strategy: string;
  review_status: ReviewStatus;
  reviewer_notes: string | null;
  reviewer_id: string | null;
  evidence: Record<string, any>;
  created_at: string;
  updated_at: string | null;
}

export interface HumanReviewListResponse {
  success: boolean;
  total: number;
  status_filter: string | null;
  reviews: HumanReviewRecord[];
}

export interface BatchJob {
  id: string;
  status: BatchStatus;
  total_records: number;
  processed_records: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

// Mirrors WebsiteInspection.to_dict() on the backend (field names are the API's, not guesses).
export interface WebsiteInspectionItem {
  id: string;
  batch_id: string;
  company_name: string;
  website_url: string;
  scan_status: string;
  page_title: string | null;
  contact_page_url: string | null;
  contact_form_found: boolean;
  captcha_detected: boolean;
  captcha_provider: string | null;
  detection_method: string | null;
  is_active_challenge: boolean;
  human_review_required: boolean;
  error_details: string | null;
  inspection_duration_ms: number;
  expected_captcha: string | null;
  expected_captcha_raw: string | null;
  expected_contact_page: string | null;
  platform: string | null;
  city: string | null;
  state: string | null;
  category: string | null;
  captcha_subtype: string | null;
  widget_state: string | null;
  widget_loaded: boolean;
  result_category: ResultCategory | null;
  robots_status: string | null;
  screenshot_path: string | null;
  evidence: Record<string, any> | null;
  form_probe: Record<string, any> | null;
  source_row: Record<string, any> | null;
  created_at: string;
}

export type ResultCategory = 'match' | 'mismatch' | 'not_detected' | 'not_accessible' | 'not_verified';

export interface EvaluationRow {
  company: string;
  website: string;
  expected: string | null;
  expected_normalised: string | null;
  detected: string;
  contact_page: string | null;
  widget_loaded: boolean;
  result_category: ResultCategory;
  result: string;
  reason: string | null;
  subtype_agreement: string;
  scan_status: string | null;
  error: string | null;
}

export interface EvaluationSummary {
  total_records: number;
  counts: Record<ResultCategory, number>;
  eligible_records: number;
  excluded: { not_accessible: number; not_verified: number };
  agreement_pct: number | null;
  subtype_agreement: { agree: number; differs: number };
  sample_size_note: string;
}

export interface BatchEvaluation {
  success: boolean;
  batch_id: string;
  status: string;
  processed_records: number;
  total_records: number;
  rows: EvaluationRow[];
  summary: EvaluationSummary;
}

export interface BatchResultsResponse {
  success: boolean;
  batch_id: string;
  status: BatchStatus;
  total_records: number;
  processed_records: number;
  results: WebsiteInspectionItem[];
}

export interface ScanWebsite {
  company_name: string;
  website_url: string;
  expected_captcha_raw?: string | null;
  expected_captcha?: string | null;
  expected_contact_page?: string | null;
  platform?: string | null;
  city?: string | null;
  state?: string | null;
  category?: string | null;
  source_row?: string | null;
}

export interface CsvImportResult {
  success: boolean;
  message: string;
  total_rows: number;
  valid_count: number;
  invalid_count: number;
  websites: Array<ScanWebsite>;
  errors: Array<{
    row: number;
    reason: string;
  }>;
  warnings?: Array<{ row: number; reason: string }>;
  columns?: string[];
  unmapped_columns?: string[];
  batch_id?: string;
  batch_status?: string;
}

export interface OcrEvaluation {
  ground_truth: string;
  extracted_text: string;
  exact_match: boolean;
  character_accuracy: number;
  execution_time_ms: number;
  image_base64?: string;
  visual_steps?: Array<{
    step: string;
    label: string;
    description: string;
    image_base64: string;
  }>;
}

export interface OcrBenchmarkItem {
  sample_index: number;
  ground_truth: string;
  predicted_text: string;
  exact_match: boolean;
  character_accuracy: number;
  execution_time_ms: number;
  noise_level: string;
}

export interface OcrBenchmarkResponse {
  success: boolean;
  total_samples: number;
  exact_matches: number;
  exact_match_rate_percent: number;
  mean_character_accuracy: number;
  mean_execution_time_ms: number;
  engine: string;
  results: OcrBenchmarkItem[];
  confusion_matrix_insights: string[];
  technical_limitations_summary: string;
}

export interface CaptchaClassification {
  provider: CaptchaProvider;
  challenge_type: string;
  detection_confidence: number;
  detection_evidence: Record<string, any>;
  handling_strategy: string;
  human_review_required: boolean;
  processing_status: string;
}

export type UserRole = 'admin' | 'operator';

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
  user: UserProfile;
}

export interface AuditLogItem {
  id: number;
  timestamp: string;
  actor_id?: string | null;
  actor_username?: string | null;
  actor_role?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  ip_address?: string | null;
  request_id?: string | null;
  details?: Record<string, any> | null;
}


// ---- Phase 7: verification + evaluation metrics ---------------------------------
export type VerificationMode = 'provider_live' | 'provider_test_keys' | 'simulated' | 'local_validation';

export interface VerificationResult {
  success: boolean;
  provider: string;
  verification_mode: VerificationMode;
  outcome: string;
  provider_called: boolean;
  provider_verified: boolean;
  scenario: string | null;
  token_source: string;
  http_status: number | null;
  error_codes: string[];
  hostname: string | null;
  message: string;
  duration_ms: number;
  evidence_note: string;
  checked_at: string;
}

export interface VerificationRow {
  id: string;
  created_at: string | null;
  provider: string;
  verification_mode: VerificationMode;
  scenario: string | null;
  outcome: string;
  success: boolean;
  provider_called: boolean;
  provider_verified: boolean;
  error_codes: string[];
  duration_ms: number;
}

export interface BenchmarkRunRow {
  id: string;
  created_at: string | null;
  source: string;
  dataset: string;
  split: string;
  engine: string;
  samples: number;
  exact_matches: number;
  exact_match_pct: number;
  char_accuracy_pct: number;
  latency_ms_mean: number;
  latency_ms_p95: number;
  failures: number;
  details: any;
}

export interface StatsSummary {
  success: boolean;
  has_data: boolean;
  time_range: { since: string | null; until: string; all_time: boolean; days: number | null };
  inspections: {
    denominator: string;
    url_scans_total: number;
    url_scans_by_status: Record<string, number>;
    batch_inspections_total: number;
    batch_inspections_by_status: Record<string, number>;
    batches_total: number;
  };
  pages: { denominator: string; pages_inspected: number; pages_with_captcha: number; pages_with_captcha_pct: number | null };
  captcha_types: { denominator: string; by_provider: Record<string, number>; share_pct: Record<string, number | null> };
  ocr: {
    denominator: string;
    evaluations: number;
    exact_matches: number;
    exact_match_pct: number | null;
    mean_char_accuracy_pct: number | null;
    mean_latency_ms: number | null;
    heldout_benchmarks: { denominator: string; by_engine: Record<string, BenchmarkRunRow> };
    api_benchmark_runs: number;
  };
  verification: {
    denominator: string;
    attempts: number;
    by_mode_and_outcome: Record<string, Record<string, number>>;
    provider_confirmed: number;
    simulated_attempts: number;
    note: string;
  };
  failures: {
    denominator: string;
    failed_scans: number;
    failed_scans_pct: number | null;
    top_errors: { message: string; count: number }[];
  };
  human_review: { denominator: string; cases: number; by_status: Record<string, number>; decisions_recorded: number };
}
