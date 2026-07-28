-- =============================================================================
-- fact_case_review
-- Grain: one row per review, per rubric criterion scored.
-- =============================================================================
--
-- A review of five criteria is five rows, so COUNT(*) counts scores, not
-- reviews. Reviews are COUNT(DISTINCT review_id), and `review_overall_score`
-- must never be summed — it repeats on every row of the same review. That is
-- the classic double-counting trap in a star schema, and stating it here is
-- cheaper than debugging a Power BI measure later.
--
-- `weight_at_review` is on the fact rather than joined from the dimension at
-- query time. The rubric can be rebalanced, and when it is, a score recorded in
-- 2027 must keep the weighting that produced its overall mark. Joining to the
-- current weight would silently rewrite history.

DROP TABLE IF EXISTS fact_case_review;

CREATE TABLE fact_case_review AS
SELECT
    r.id                                    AS review_id,
    bc.id                                   AS case_id,
    bc.profile_id                           AS profile_key,
    sc.criterion_id                         AS criterion_key,
    dd.date_key                             AS date_key,
    bc.title                                AS case_title,
    sc.score                                AS score,
    rc.weight                               AS weight_at_review,
    sc.score * rc.weight                    AS weighted_score,
    r.overall_score                         AS review_overall_score,
    COALESCE(m.version, 0)                  AS roi_model_version
FROM case_review r
JOIN business_case bc ON bc.id = r.case_id
JOIN case_review_score sc ON sc.review_id = r.id
JOIN review_criterion rc ON rc.id = sc.criterion_id
JOIN dim_date dd ON dd.full_date = r.reviewed_on
LEFT JOIN roi_model m ON m.id = r.roi_model_id;
