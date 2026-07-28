-- =============================================================================
-- v_market_demand
-- One row per skill and capture quarter, across all captured postings.
-- =============================================================================
--
-- Two measures that must not be blended: `postings_demanding` is how common
-- the requirement is, `max_required_level` is how deep the deepest ask goes.
-- One posting wanting level 4 and nine wanting level 3 are different problems.
--
-- The unmapped skill member (skill_key = -1) appears here as a real row rather
-- than being filtered out. It is the signal that the market has moved
-- somewhere the taxonomy has not.

DROP VIEW IF EXISTS v_market_demand;

CREATE VIEW v_market_demand AS
SELECT
    d.year,
    d.quarter,
    d.year_quarter,
    s.skill_code,
    s.skill_name,
    s.domain_name,
    s.is_unknown_member,
    COUNT(DISTINCT f.posting_id) AS postings_demanding,
    COUNT(*)                     AS requirement_mentions,
    SUM(f.is_must_have)          AS must_have_mentions,
    MAX(f.required_level)        AS max_required_level
FROM fact_market_requirement f
JOIN dim_date d  ON d.date_key = f.date_key
JOIN dim_skill s ON s.skill_key = f.skill_key
GROUP BY
    d.year, d.quarter, d.year_quarter,
    s.skill_code, s.skill_name, s.domain_name, s.is_unknown_member;
