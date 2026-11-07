-- Phase 5 schema (commit 98f1457), exported from a real Phase 5 database. Schema only, no data.
CREATE TABLE audit_logs (
	id VARCHAR(36) NOT NULL, 
	timestamp DATETIME, 
	actor_id VARCHAR(36), 
	actor_username VARCHAR(64), 
	actor_role VARCHAR(32), 
	action VARCHAR(64) NOT NULL, 
	resource_type VARCHAR(64), 
	resource_id VARCHAR(64), 
	ip_address VARCHAR(64), 
	request_id VARCHAR(64), 
	details TEXT, 
	PRIMARY KEY (id)
);
CREATE TABLE batch_jobs (
	id VARCHAR(36) NOT NULL, 
	status VARCHAR(32), 
	total_records INTEGER, 
	processed_records INTEGER, 
	successful_records INTEGER, 
	failed_records INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE captcha_intelligence (
	id VARCHAR(36) NOT NULL, 
	scan_id VARCHAR(36), 
	page_url VARCHAR(1024), 
	classification VARCHAR(64) NOT NULL, 
	provider VARCHAR(64) NOT NULL, 
	challenge_type VARCHAR(64), 
	is_active_challenge BOOLEAN, 
	detection_confidence FLOAT, 
	detection_evidence TEXT, 
	handling_strategy VARCHAR(64) NOT NULL, 
	human_review_required BOOLEAN, 
	processing_status VARCHAR(64), 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE discovered_pages (
	id VARCHAR(36) NOT NULL, 
	scan_id VARCHAR(36) NOT NULL, 
	url VARCHAR(1024) NOT NULL, 
	depth INTEGER, 
	page_title VARCHAR(512), 
	canonical_url VARCHAR(1024), 
	classification VARCHAR(32), 
	confidence_score FLOAT, 
	evidence TEXT, 
	contact_form_found BOOLEAN, 
	forms_count INTEGER, 
	has_inputs BOOLEAN, 
	has_textarea BOOLEAN, 
	captcha_detected BOOLEAN, 
	captcha_provider VARCHAR(128), 
	is_active_challenge BOOLEAN, 
	human_review_required BOOLEAN, 
	detection_method VARCHAR(128), 
	screenshot_path VARCHAR(512), 
	http_status INTEGER, 
	crawl_duration_ms FLOAT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(scan_id) REFERENCES url_scans (id)
);
CREATE TABLE human_reviews (
	id VARCHAR(36) NOT NULL, 
	scan_id VARCHAR(36), 
	page_url VARCHAR(1024) NOT NULL, 
	captcha_provider VARCHAR(128) NOT NULL, 
	challenge_type VARCHAR(64), 
	reason_for_review TEXT NOT NULL, 
	review_status VARCHAR(32), 
	operator_notes TEXT, 
	created_at DATETIME, 
	resolved_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE ocr_evaluations (
	id VARCHAR(36) NOT NULL, 
	ground_truth VARCHAR(128) NOT NULL, 
	predicted_text VARCHAR(128) NOT NULL, 
	exact_match BOOLEAN, 
	character_accuracy FLOAT, 
	confidence FLOAT, 
	duration_ms FLOAT, 
	ocr_engine VARCHAR(128), 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE url_scans (
	id VARCHAR(36) NOT NULL, 
	submitted_url VARCHAR(1024) NOT NULL, 
	domain VARCHAR(255) NOT NULL, 
	status VARCHAR(32), 
	pages_crawled INTEGER, 
	contact_pages_found INTEGER, 
	captcha_detected BOOLEAN, 
	captcha_providers VARCHAR(255), 
	error_message TEXT, 
	crawl_duration_ms FLOAT, 
	created_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE website_inspections (
	id VARCHAR(36) NOT NULL, 
	batch_id VARCHAR(36) NOT NULL, 
	company_name VARCHAR(255) NOT NULL, 
	website_url VARCHAR(1024) NOT NULL, 
	scan_status VARCHAR(64), 
	page_title VARCHAR(512), 
	contact_page_url VARCHAR(1024), 
	contact_form_found BOOLEAN, 
	captcha_detected BOOLEAN, 
	captcha_provider VARCHAR(128), 
	detection_method VARCHAR(128), 
	is_active_challenge BOOLEAN, 
	human_review_required BOOLEAN, 
	error_details TEXT, 
	inspection_duration_ms FLOAT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(batch_id) REFERENCES batch_jobs (id)
);
CREATE INDEX ix_audit_logs_action ON audit_logs (action);
CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);
CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id);
CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp);
CREATE INDEX ix_batch_jobs_status ON batch_jobs (status);
CREATE INDEX ix_captcha_intelligence_classification ON captcha_intelligence (classification);
CREATE INDEX ix_captcha_intelligence_scan_id ON captcha_intelligence (scan_id);
CREATE INDEX ix_discovered_pages_classification ON discovered_pages (classification);
CREATE INDEX ix_discovered_pages_scan_id ON discovered_pages (scan_id);
CREATE INDEX ix_human_reviews_review_status ON human_reviews (review_status);
CREATE INDEX ix_human_reviews_scan_id ON human_reviews (scan_id);
CREATE INDEX ix_url_scans_domain ON url_scans (domain);
CREATE INDEX ix_url_scans_status ON url_scans (status);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_website_inspections_batch_id ON website_inspections (batch_id);
CREATE INDEX ix_website_inspections_scan_status ON website_inspections (scan_status);
