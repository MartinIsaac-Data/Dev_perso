-- =============================================================================
-- v_review_scores
-- One row per review and criterion.
-- =============================================================================
--
-- `review_overall_score` repeats across the rows of one review, so it must be
-- aggregated with MIN or MAX, never SUM or AVG over rows. Left visible rather
-- than removed because a report legitimately wants it — with that warning
-- attached.

DROP VIEW IF EXISTS v_review_scores;

CREATE VIEW v_review_scores AS
SELECT
    p.profile_code,
    p.is_demo,
    d.year,
    d.year_quarter,
    f.case_id,
    f.case_title,
    f.review_id,
    c.criterion_code,
    c.criterion_name,
    c.criterion_ordinal,
    f.score,
    f.weight_at_review,
    f.weighted_score,
    f.review_overall_score,
    f.roi_model_version
FROM fact_case_review f
JOIN dim_date d              ON d.date_key = f.date_key
JOIN dim_profile p           ON p.profile_key = f.profile_key
JOIN dim_review_criterion c  ON c.criterion_key = f.criterion_key;
