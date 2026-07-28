-- =============================================================================
-- fact_skill_state
-- Grain: one row per profile, per skill, as at the build date.
-- =============================================================================
--
-- A snapshot fact, not a transaction fact: it holds the position at build time,
-- and rebuilding overwrites it. The history of *changes* lives in
-- fact_level_change, which is a transaction fact with a different grain.
-- Keeping them apart is what stops a report averaging levels across time and
-- calling the result progress.
--
-- Rows exist only for profile-skill pairs the profile actually tracks. Skills
-- with no state row are absent rather than materialised at zero: "not
-- assessed" and "assessed at zero" are different facts, and a dimensional
-- model that conflates them will report a beginner and a non-participant
-- identically.
--
-- Decay is computed by subtracting sequential day numbers held on dim_date.
-- Date arithmetic is where portable SQL usually breaks — `julianday` is
-- SQLite, `AGE` is Postgres — and an integer difference is neither.

DROP TABLE IF EXISTS fact_skill_state;

CREATE TABLE fact_skill_state AS
SELECT
    ss.profile_id                                   AS profile_key,
    ss.skill_id                                     AS skill_key,
    ss.current_level                                AS current_level,
    ss.target_level                                 AS target_level,
    CASE WHEN ss.target_level > ss.current_level
         THEN ss.target_level - ss.current_level
         ELSE 0 END                                 AS level_gap,
    ss.last_practised_on                            AS last_practised_on,
    COALESCE(s.decay_months, 9)                     AS decay_months,
    practised.day_number                            AS last_practised_day_number,
    CASE WHEN practised.day_number IS NULL THEN NULL
         ELSE built.day_number - practised.day_number
    END                                             AS days_since_practice,
    CASE WHEN ss.current_level >= 2
          AND practised.day_number IS NOT NULL
          AND (built.day_number - practised.day_number)
              >= COALESCE(s.decay_months, 9) * 30
         THEN 1 ELSE 0 END                          AS is_decayed,
    CASE WHEN ss.current_level >= 3 THEN 1 ELSE 0 END AS is_claimable,
    -- How many published deliverables back this level.
    (SELECT COUNT(*)
       FROM deliverable_skill dsk
       JOIN deliverable dd ON dd.id = dsk.deliverable_id
      WHERE dsk.skill_id = ss.skill_id
        AND dd.profile_id = ss.profile_id
        AND dd.status = 'published')                AS evidence_count
FROM skill_state ss
JOIN skill s ON s.id = ss.skill_id
LEFT JOIN dim_date practised ON practised.full_date = ss.last_practised_on
CROSS JOIN (SELECT day_number FROM dim_date WHERE is_build_date = 1) built;
