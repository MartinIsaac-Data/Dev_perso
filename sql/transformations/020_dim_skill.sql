-- =============================================================================
-- dim_skill
-- Grain: one row per skill in the taxonomy, plus one "unknown" member.
-- =============================================================================
--
-- The row with skill_key = -1 is deliberate and is standard dimensional
-- practice. A job requirement the taxonomy cannot express has no skill to
-- point at, and there are only three ways to handle that:
--
--   1. leave the foreign key null, which forces every query to remember an
--      outer join and silently drops those rows from any inner-joined report;
--   2. drop the requirement, which destroys the most interesting signal the
--      Gap Radar produces;
--   3. point it at an explicit unknown member, so it is counted, visible, and
--      impossible to lose by accident.
--
-- Only the third one is honest, so every fact table here uses -1 rather than
-- null for a missing dimension key.

DROP TABLE IF EXISTS dim_skill;

CREATE TABLE dim_skill AS
SELECT
    s.id                        AS skill_key,
    s.code                      AS skill_code,
    s.name                      AS skill_name,
    d.code                      AS domain_code,
    d.name                      AS domain_name,
    d.ordinal                   AS domain_ordinal,
    s.decay_months              AS decay_months,
    -- Degenerate graph attributes, denormalised onto the dimension so a
    -- report can filter on "foundational" without traversing the edge table.
    (SELECT COUNT(*) FROM skill_edge e WHERE e.prerequisite_skill_id = s.id)
                                AS direct_dependents,
    (SELECT COUNT(*) FROM skill_edge e WHERE e.dependent_skill_id = s.id)
                                AS direct_prerequisites,
    CASE
        WHEN (SELECT COUNT(*) FROM skill_edge e WHERE e.dependent_skill_id = s.id) = 0
        THEN 1 ELSE 0
    END                         AS is_root,
    0                           AS is_unknown_member
FROM skill s
JOIN skill_domain d ON d.id = s.domain_id

UNION ALL

SELECT
    -1, 'unknown', 'Not in the taxonomy', 'unknown', 'Unmapped', 99,
    NULL, 0, 0, 0, 1;
