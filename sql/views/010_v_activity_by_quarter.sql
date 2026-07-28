-- =============================================================================
-- v_activity_by_quarter
-- One row per profile, quarter and deliverable type.
-- =============================================================================
--
-- Safe to sum: deliverables_published, skill_applications.
-- Not safe to sum: nothing here — every measure is additive at this grain,
-- which is the point of aggregating to it rather than binding a report
-- straight to fact_activity where COUNT(*) means skill-applications.

DROP VIEW IF EXISTS v_activity_by_quarter;

CREATE VIEW v_activity_by_quarter AS
SELECT
    p.profile_code,
    p.is_demo,
    d.year,
    d.quarter,
    d.year_quarter,
    d.phase_code,
    t.type_code,
    t.type_name,
    t.is_publication,
    COUNT(DISTINCT f.deliverable_id) AS deliverables_published,
    COUNT(*)                         AS skill_applications,
    SUM(f.is_central_skill)          AS central_skill_applications,
    SUM(f.cited_as_evidence)         AS evidence_citations
FROM fact_activity f
JOIN dim_date d              ON d.date_key = f.date_key
JOIN dim_profile p           ON p.profile_key = f.profile_key
JOIN dim_deliverable_type t  ON t.deliverable_type_key = f.deliverable_type_key
GROUP BY
    p.profile_code, p.is_demo, d.year, d.quarter, d.year_quarter,
    d.phase_code, t.type_code, t.type_name, t.is_publication;
