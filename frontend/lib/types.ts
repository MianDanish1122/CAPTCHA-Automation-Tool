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

export interface WebsiteInspectionItem {
  id: number;
  batch_id: string;
  company_name: string;
  website_url: string;
  status: string;
  captcha_detected: boolean;
  captcha_provider: string | null;
  challenge_type: string | null;
  confidence_score: number;
  forms_found_count: number;
  human_review_required: boolean;
  evidence: Record<string, any>;
  error_message: string | null;
  created_at: string;
}

export interface BatchResultsResponse {
  success: boolean;
  batch_id: string;
  status: BatchStatus;
  total_records: number;
  processed_records: number;
  results: WebsiteInspectionItem[];
}

export interface CsvImportResult {
  success: boolean;
  message: string;
  total_rows: number;
  valid_count: number;
  invalid_count: number;
  websites: Array<{
    company_name: string;
    website_url: string;
  }>;
  errors: Array<{
    row: number;
    reason: string;
  }>;
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
