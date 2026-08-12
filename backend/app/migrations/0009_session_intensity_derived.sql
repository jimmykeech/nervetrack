-- strength_sessions.intensity becomes the single source of truth for session
-- intensity; daily_entries.session_intensity becomes a derived cache (MAX(intensity)
-- over the day's sessions), kept in sync by services/sessions.py from here on.

-- Backfill: the xlsx importer historically wrote day-level session_intensity but
-- created its one-session-per-day rows with no intensity of their own. Where a day
-- has exactly one session and that session's intensity is still NULL, copy the day's
-- stored value onto it so imported history becomes real per-session data.
UPDATE strength_sessions
SET intensity = (
    SELECT d.session_intensity
    FROM daily_entries d
    WHERE d.id = strength_sessions.daily_entry_id
)
WHERE intensity IS NULL
  AND daily_entry_id IN (
      SELECT daily_entry_id
      FROM strength_sessions
      GROUP BY daily_entry_id
      HAVING COUNT(*) = 1
  )
  AND EXISTS (
      SELECT 1 FROM daily_entries d
      WHERE d.id = strength_sessions.daily_entry_id
        AND d.session_intensity IS NOT NULL
  );

-- Recompute: re-derive the mirror from sessions, but only for days that have at
-- least one session with a non-null intensity to attribute it to. Days holding a
-- session_intensity with no such session (multi-session days with all-null
-- intensities, or orphaned values with no session at all) are left untouched —
-- blanking them would destroy data with no way to recover it.
UPDATE daily_entries
SET session_intensity = (
    SELECT MAX(s.intensity)
    FROM strength_sessions s
    WHERE s.daily_entry_id = daily_entries.id
)
WHERE id IN (
    SELECT daily_entry_id
    FROM strength_sessions
    WHERE intensity IS NOT NULL
);
