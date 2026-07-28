-- =============================================================================
-- fact_market_requirement
-- Grain: one row per requirement extracted from one job posting.
-- =============================================================================
--
-- The point of this table is the time axis. Postings are never overwritten, so
-- six years of captures make it answerable which requirements were structural
-- and which were a fashion — a question a single snapshot can never address.
--
-- Unmapped requirements point at the unknown member (skill_key = -1) rather
-- than carrying a null. They are the most interesting rows in the table, and an
-- inner join must not be able to lose them silently.

DROP TABLE IF EXISTS fact_market_requirement;

CREATE TABLE fact_market_requirement AS
SELECT
    req.id                                      AS requirement_id,
    p.id                                        AS posting_id,
    COALESCE(req.skill_id, -1)                  AS skill_key,
    COALESCE(p.target_role_id, -1)              AS target_role_key,
    dd.date_key                                 AS date_key,
    p.title                                     AS posting_title,
    p.seniority_label                           AS seniority_label,
    req.raw_label                               AS raw_label,
    req.required_level                          AS required_level,
    CASE WHEN req.importance = 'must_have' THEN 1 ELSE 0 END AS is_must_have,
    CASE WHEN req.skill_id IS NULL THEN 1 ELSE 0 END         AS is_unmapped
FROM job_requirement req
JOIN job_posting p ON p.id = req.posting_id
JOIN dim_date dd ON dd.full_date = p.captured_on;
