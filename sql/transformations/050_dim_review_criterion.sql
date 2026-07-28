-- =============================================================================
-- dim_review_criterion
-- Grain: one row per scoring criterion in the review rubric.
-- =============================================================================
--
-- `weight` is carried here as a dimension attribute rather than being applied
-- in the fact, so a report can show both the raw score and the weighted
-- contribution, and so rebalancing the rubric does not require rebuilding
-- history. fact_case_review stores the weight that was in force at the time.

DROP TABLE IF EXISTS dim_review_criterion;

CREATE TABLE dim_review_criterion AS
SELECT
    c.id       AS criterion_key,
    c.code     AS criterion_code,
    c.name     AS criterion_name,
    c.weight   AS current_weight,
    c.ordinal  AS criterion_ordinal
FROM review_criterion c;
