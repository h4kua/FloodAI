-- Migration: 110_report_photos.sql
-- Description: Optional photo on a community flood report. Photos are uploaded
--              by the backend (anon key) into a public Storage bucket after it
--              has re-encoded them as JPEG (metadata stripped, max 1280 px);
--              the report row keeps the public URL.
-- Created: 2026-10-27
-- Run once in the Supabase SQL Editor.

BEGIN;

ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS photo_url TEXT;

-- Public read; 2 MB cap and image types enforced by Storage as a second line.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('report-photos', 'report-photos', true, 2097152, ARRAY['image/jpeg'])
ON CONFLICT (id) DO NOTHING;

-- The backend uploads with the anon key: allow INSERT into this bucket only.
DROP POLICY IF EXISTS "backend uploads report photos" ON storage.objects;
CREATE POLICY "backend uploads report photos"
    ON storage.objects FOR INSERT TO anon
    WITH CHECK (bucket_id = 'report-photos');

COMMIT;
