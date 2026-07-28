-- =============================================================================
-- v_skill_position
-- One row per profile and skill currently tracked.
-- =============================================================================
--
-- The reporting contract for the skill graph. Reports bind here rather than to
-- fact_skill_state so the physical table can be reshaped without breaking
-- every visual.

DROP VIEW IF EXISTS v_skill_position;

CREATE VIEW v_skill_position AS
SELECT
    p.profile_code,
    p.is_demo,
    s.skill_code,
    s.skill_name,
    s.domain_code,
    s.domain_name,
    s.domain_ordinal,
    s.direct_dependents,
    s.is_root,
    f.current_level,
    f.target_level,
    f.level_gap,
    f.decay_months,
    f.days_since_practice,
    f.is_decayed,
    f.is_claimable,
    f.evidence_count,
    -- A level of 3 or above with nothing published behind it. The gap an
    -- interviewer finds before you do.
    CASE WHEN f.is_claimable = 1 AND f.evidence_count = 0 THEN 1 ELSE 0 END
        AS is_undefensible
FROM fact_skill_state f
JOIN dim_profile p ON p.profile_key = f.profile_key
JOIN dim_skill s   ON s.skill_key = f.skill_key;
