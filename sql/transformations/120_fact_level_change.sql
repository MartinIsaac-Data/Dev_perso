-- =============================================================================
-- fact_level_change
-- Grain: one row per recorded level movement.
-- =============================================================================
--
-- A transaction fact. This is where "how did the profile get here" is
-- answerable, and it is deliberately separate from the fact_skill_state
-- snapshot: averaging a snapshot across dates produces a number that means
-- nothing, and having the two grains in one table is how that mistake gets
-- made.
--
-- `level_delta` is negative for a downgrade, and downgrades are kept. A
-- trajectory that only records progress is one nobody can learn from.

DROP TABLE IF EXISTS fact_level_change;

CREATE TABLE fact_level_change AS
SELECT
    c.id                                    AS level_change_id,
    c.profile_id                            AS profile_key,
    c.skill_id                              AS skill_key,
    dd.date_key                             AS date_key,
    c.from_level                            AS from_level,
    c.to_level                              AS to_level,
    c.to_level - c.from_level               AS level_delta,
    CASE WHEN c.to_level > c.from_level THEN 1 ELSE 0 END AS is_promotion,
    COALESCE(c.deliverable_id, -1)          AS deliverable_id,
    CASE WHEN c.deliverable_id IS NULL THEN 0 ELSE 1 END AS has_evidence
FROM skill_level_change c
JOIN dim_date dd ON dd.full_date = c.changed_on;
