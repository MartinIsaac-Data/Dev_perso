-- =============================================================================
-- fact_review_challenge
-- Grain: one row per objection raised by the review board.
-- =============================================================================
--
-- Almost factless: the useful measures are counts and the days an objection
-- stayed open. It exists so that "my cost assumptions are consistently the
-- weakest part of my cases, and have been for a year" is a query rather than a
-- reading exercise across five review documents.

DROP TABLE IF EXISTS fact_review_challenge;

CREATE TABLE fact_review_challenge AS
SELECT
    ch.id                                       AS challenge_id,
    r.id                                        AS review_id,
    bc.profile_id                               AS profile_key,
    reviewed.date_key                           AS date_key,
    ch.persona                                  AS persona,
    ch.severity                                 AS severity,
    CASE ch.severity
        WHEN 'blocking' THEN 3
        WHEN 'major'    THEN 2
        ELSE 1
    END                                         AS severity_rank,
    COALESCE(ch.target_assumption_id, -1)       AS assumption_id,
    CASE WHEN ch.target_assumption_id IS NULL THEN 0 ELSE 1 END AS is_pinned_to_assumption,
    CASE WHEN ch.resolved_on IS NULL THEN 1 ELSE 0 END          AS is_open,
    CASE WHEN resolved.day_number IS NULL THEN NULL
         ELSE resolved.day_number - reviewed.day_number
    END                                         AS days_to_answer
FROM case_review_challenge ch
JOIN case_review r ON r.id = ch.review_id
JOIN business_case bc ON bc.id = r.case_id
JOIN dim_date reviewed ON reviewed.full_date = r.reviewed_on
LEFT JOIN dim_date resolved ON resolved.full_date = ch.resolved_on;
