-- VPMS Phase 2 Migration
-- Version: 002
-- Description: Register Chronos, Avatar Webinar, VMF workers and their capabilities

BEGIN;

-- ── Update worker registry entries with real base URLs ────────────────────────

UPDATE vpms.worker_registry
SET
    base_url = CASE worker_id
        WHEN 'chronos'          THEN NULL  -- file-based, no HTTP URL
        WHEN 'avatar-webinar'  THEN 'http://localhost:3200'
        WHEN 'vmf'             THEN 'http://localhost:4100'
        ELSE base_url
    END,
    status = 'AVAILABLE',
    health_status = 'UNKNOWN',  -- will be updated by health checks
    max_concurrency = CASE worker_id
        WHEN 'chronos'          THEN 1   -- one cron slot at a time
        WHEN 'avatar-webinar'    THEN 3   -- concurrent renders
        WHEN 'vmf'              THEN 5   -- parallel pipeline jobs
        ELSE max_concurrency
    END,
    extra_data = CASE worker_id
        WHEN 'chronos' THEN '{"app_dir": "/opt/empire/apps/high-cpm-story-franchise", "interface": "file_queue"}'
        WHEN 'avatar-webinar' THEN '{"port": 3200, "auth": "supabase_jwt", "interface": "http_rest"}'
        WHEN 'vmf' THEN '{"port": 4100, "auth": "jwt_bearer", "interface": "http_rest"}'
        ELSE extra_data
    END
WHERE worker_id IN ('chronos', 'avatar-webinar', 'vmf');

-- ── Chronos Capabilities ────────────────────────────────────────────────────────
INSERT INTO vpms.worker_capabilities
    (worker_id, capability, code_present, credential_verified, integration_verified, production_verified, healthy, estimated_cost, average_latency_seconds, max_concurrency, visibility, extra_data)
VALUES
    ('chronos', 'content_research',        TRUE, TRUE, TRUE, FALSE, FALSE, 0.00, 30.0, 1, 'internal', '{"description": "Discover and research high-CPM niche topics"}'),
    ('chronos', 'script_generation',       TRUE, TRUE, TRUE, FALSE, FALSE, 0.10, 60.0, 1, 'internal', '{"description": "Write episodic scripts with narrative continuity"}'),
    ('chronos', 'fish_audio_tts',         TRUE, TRUE, TRUE, FALSE, FALSE, 0.02, 15.0, 1, 'internal', '{"description": "Fish Audio narration generation"}'),
    ('chronos', 'shotstack_render',        TRUE, TRUE, TRUE, FALSE, FALSE, 0.25, 120.0, 1, 'internal', '{"description": "Shotstack 1080p MP4 rendering"}'),
    ('chronos', 'postiz_publish',          TRUE, TRUE, TRUE, FALSE, FALSE, 0.00, 10.0, 1, 'internal', '{"description": "Postiz social publishing"}'),
    ('chronos', 'full_episode_pipeline',   TRUE, TRUE, FALSE, FALSE, FALSE, 0.37, 300.0, 1, 'internal', '{"description": "End-to-end episode: research→script→TTS→render→publish"}')
ON CONFLICT DO NOTHING;

-- ── Avatar Webinar Capabilities ──────────────────────────────────────────────────
INSERT INTO vpms.worker_capabilities
    (worker_id, capability, code_present, credential_verified, integration_verified, production_verified, healthy, estimated_cost, average_latency_seconds, max_concurrency, visibility, extra_data)
VALUES
    ('avatar-webinar', 'podcast_production',   TRUE, FALSE, FALSE, FALSE, FALSE, 0.50, 180.0, 3, 'internal', '{"description": "Full podcast production: plan→approve→render"}'),
    ('avatar-webinar', 'render_from_script',   TRUE, FALSE, FALSE, FALSE, FALSE, 0.50, 180.0, 3, 'internal', '{"description": "One-call render from script text"}'),
    ('avatar-webinar', 'avatar_talking_head', TRUE, FALSE, FALSE, FALSE, FALSE, 0.20, 30.0, 3, 'internal', '{"description": "AI avatar talking-head video"}'),
    ('avatar-webinar', 'podcast_hybrid',      TRUE, FALSE, FALSE, FALSE, FALSE, 0.35, 180.0, 3, 'internal', '{"description": "Smart hybrid podcast rendering"}')
ON CONFLICT DO NOTHING;

-- ── VMF Capabilities ─────────────────────────────────────────────────────────────
INSERT INTO vpms.worker_capabilities
    (worker_id, capability, code_present, credential_verified, integration_verified, production_verified, healthy, estimated_cost, average_latency_seconds, max_concurrency, visibility, extra_data)
VALUES
    ('vmf', 'pipeline_video',   TRUE, FALSE, FALSE, FALSE, FALSE, 0.50, 120.0, 5, 'internal', '{"description": "LLM-script→TTS→assets→Shotstack render pipeline", "providers": ["shotstack", "creatomate"]}'),
    ('vmf', 'ugc_batch',        TRUE, FALSE, FALSE, FALSE, FALSE, 0.10, 60.0, 5, 'internal', '{"description": "Bulk UGC video generation via Creatomate"}'),
    ('vmf', 'image_generation', TRUE, TRUE,  TRUE,  FALSE, TRUE,  0.01, 10.0, 5, 'internal', '{"description": "Image generation via Runware/MuAPI/Wavespeed"}'),
    ('vmf', 'video_generation', TRUE, TRUE,  TRUE,  FALSE, TRUE,  0.10, 30.0, 5, 'internal', '{"description": "Video generation via Kling/Veo/Seedance/Wan"}')
ON CONFLICT DO NOTHING;

-- ── Remove mock_video_render capability (replaced by real capabilities) ─────────
UPDATE vpms.worker_capabilities
SET is_active = FALSE
WHERE worker_id = 'vmf' AND capability = 'mock_video_render';

-- ── Remove moneyprint stub (Phase 3) ───────────────────────────────────────────
UPDATE vpms.worker_registry
SET is_active = FALSE
WHERE worker_id = 'moneyprint';

COMMIT;
