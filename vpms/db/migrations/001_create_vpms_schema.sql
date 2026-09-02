-- VPMS Schema Migration
-- Version: 001
-- Description: Create vpms schema and all core tables

BEGIN;

CREATE SCHEMA IF NOT EXISTS vpms;

-- Source Applications
CREATE TABLE vpms.source_apps (
    app_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    description TEXT,
    api_key_hash VARCHAR(256),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Jobs
CREATE TABLE vpms.jobs (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('vpms_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    source_app VARCHAR(64) NOT NULL REFERENCES vpms.source_apps(app_id),
    external_reference_id VARCHAR(256),
    idempotency_key VARCHAR(256),
    job_type VARCHAR(32) NOT NULL,
    request_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    priority INTEGER NOT NULL DEFAULT 5,
    request_payload JSONB NOT NULL DEFAULT '{}',
    production_plan JSONB,
    output JSONB,
    estimated_cost NUMERIC(10, 4),
    actual_cost NUMERIC(10, 4),
    budget_limit NUMERIC(10, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_code VARCHAR(64),
    error_message TEXT,
    created_by VARCHAR(256),
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX ix_jobs_source_app ON vpms.jobs(source_app);
CREATE INDEX ix_jobs_external_ref ON vpms.jobs(external_reference_id);
CREATE INDEX ix_jobs_idempotency ON vpms.jobs(idempotency_key);
CREATE INDEX ix_jobs_status ON vpms.jobs(status);
CREATE INDEX ix_jobs_source_idempotency ON vpms.jobs(source_app, idempotency_key);

-- Job Events
CREATE TABLE vpms.job_events (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('ev_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 16)),
    job_id VARCHAR(32) NOT NULL REFERENCES vpms.jobs(id),
    event_type VARCHAR(64) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    previous_state VARCHAR(32),
    new_state VARCHAR(32),
    worker VARCHAR(64),
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_job_events_job_id ON vpms.job_events(job_id);
CREATE INDEX ix_job_events_timestamp ON vpms.job_events(timestamp);

-- Worker Registry
CREATE TABLE vpms.worker_registry (
    worker_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    base_url VARCHAR(512),
    status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE',
    visibility VARCHAR(32) NOT NULL DEFAULT 'internal',
    health_status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    last_health_check TIMESTAMPTZ,
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    current_load INTEGER NOT NULL DEFAULT 0,
    avg_latency_seconds NUMERIC(10, 2),
    cost_per_job NUMERIC(10, 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_worker_status ON vpms.worker_registry(status);
CREATE INDEX ix_worker_health ON vpms.worker_registry(health_status);

-- Worker Capabilities
CREATE TABLE vpms.worker_capabilities (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('cap_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    worker_id VARCHAR(64) NOT NULL REFERENCES vpms.worker_registry(worker_id),
    capability VARCHAR(64) NOT NULL,
    code_present BOOLEAN NOT NULL DEFAULT FALSE,
    credential_verified BOOLEAN NOT NULL DEFAULT FALSE,
    integration_verified BOOLEAN NOT NULL DEFAULT FALSE,
    production_verified BOOLEAN NOT NULL DEFAULT FALSE,
    healthy BOOLEAN NOT NULL DEFAULT FALSE,
    estimated_cost NUMERIC(10, 4),
    average_latency_seconds NUMERIC(10, 2),
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    visibility VARCHAR(32) NOT NULL DEFAULT 'internal',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_capability_capability ON vpms.worker_capabilities(capability);

-- Worker Jobs
CREATE TABLE vpms.worker_jobs (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('wrkj_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    vpms_job_id VARCHAR(32) NOT NULL REFERENCES vpms.jobs(id),
    worker_id VARCHAR(64) NOT NULL REFERENCES vpms.worker_registry(worker_id),
    worker_job_id VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    provider VARCHAR(64),
    model VARCHAR(128),
    estimated_cost NUMERIC(10, 4),
    actual_cost NUMERIC(10, 4),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    errors JSONB NOT NULL DEFAULT '[]',
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_worker_jobs_vpms_job ON vpms.worker_jobs(vpms_job_id);
CREATE INDEX ix_worker_jobs_worker ON vpms.worker_jobs(worker_id);
CREATE INDEX ix_worker_jobs_worker_job_id ON vpms.worker_jobs(worker_job_id);

-- Artifacts
CREATE TABLE vpms.artifacts (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('art_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    job_id VARCHAR(32) NOT NULL REFERENCES vpms.jobs(id),
    worker_job_id VARCHAR(32) REFERENCES vpms.worker_jobs(id),
    artifact_type VARCHAR(64) NOT NULL,
    name VARCHAR(256) NOT NULL,
    url VARCHAR(1024),
    file_path VARCHAR(512),
    file_size_bytes BIGINT,
    mime_type VARCHAR(128),
    checksum VARCHAR(128),
    duration_seconds NUMERIC(10, 2),
    width INTEGER,
    height INTEGER,
    extra_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_artifacts_job_id ON vpms.artifacts(job_id);
CREATE INDEX ix_artifacts_type ON vpms.artifacts(artifact_type);

-- QA Reports
CREATE TABLE vpms.qa_reports (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('qa_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    job_id VARCHAR(32) NOT NULL REFERENCES vpms.jobs(id),
    qa_type VARCHAR(32) NOT NULL,
    scores JSONB NOT NULL DEFAULT '{}',
    issues JSONB NOT NULL DEFAULT '[]',
    required_fixes JSONB NOT NULL DEFAULT '[]',
    decision VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_qa_reports_job_id ON vpms.qa_reports(job_id);
CREATE INDEX ix_qa_reports_type ON vpms.qa_reports(qa_type);

-- Approvals
CREATE TABLE vpms.approvals (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('apr_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    job_id VARCHAR(32) NOT NULL REFERENCES vpms.jobs(id),
    approval_type VARCHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    approved_by VARCHAR(256),
    notes TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_approvals_job_id ON vpms.approvals(job_id);

-- Publish Receipts
CREATE TABLE vpms.publish_receipts (
    id VARCHAR(32) PRIMARY KEY DEFAULT ('pub_' || SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 12)),
    job_id VARCHAR(32) NOT NULL REFERENCES vpms.jobs(id),
    platform VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    provider_job_id VARCHAR(256),
    scheduled_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    published_url VARCHAR(1024),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ix_publish_job_id ON vpms.publish_receipts(job_id);

-- Seed source apps for testing
INSERT INTO vpms.source_apps (app_id, name, description) VALUES
    ('podcast-factory', 'Podcast Factory', 'Podcast episode production system'),
    ('bookfactory', 'BookFactory', 'Book factory video production'),
    ('affiliate-production', 'Affiliate Production', 'Affiliate video production'),
    ('vpms-internal', 'VPMS Internal', 'Internal VPMS test client')
ON CONFLICT DO NOTHING;

-- Seed worker registry entries
INSERT INTO vpms.worker_registry (worker_id, name, base_url, visibility) VALUES
    ('chronos', 'Chronos Content Showrunner', NULL, 'internal'),
    ('avatar-webinar', 'Avatar Webinar', NULL, 'internal'),
    ('moneyprint', 'MoneyPrint Faceless', NULL, 'internal'),
    ('vmf', 'Video Media Factory', NULL, 'internal')
ON CONFLICT DO NOTHING;

-- Seed mock worker capability
INSERT INTO vpms.worker_capabilities (worker_id, capability, code_present, credential_verified, integration_verified, production_verified, healthy, visibility)
VALUES ('vmf', 'mock_video_render', TRUE, TRUE, TRUE, FALSE, TRUE, 'internal')
ON CONFLICT DO NOTHING;

COMMIT;
