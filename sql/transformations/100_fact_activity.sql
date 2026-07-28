-- =============================================================================
-- fact_activity
-- Grain: one row per published deliverable, per skill it exercised.
-- =============================================================================
--
-- State the grain before writing the measures, because it decides what may be
-- summed. A deliverable exercising four skills appears as four rows here, so
-- COUNT(*) counts skill-applications, NOT deliverables. Counting deliverables
-- means COUNT(DISTINCT deliverable_id), and that is why the column is kept on
-- the fact rather than replaced by a surrogate key: it has to stay countable.
--
-- Only published deliverables are here. Work in progress is real, but it is
-- not evidence, and mixing the two would let a report show effort as though it
-- were output — which the whole application exists to avoid.
--
-- Note the join to dim_date rather than a date function. Extracting the year
-- from a date is `strftime` in SQLite and `EXTRACT` in Postgres; conforming on
-- the date dimension avoids the dialect entirely, and is what a date dimension
-- is for in the first place.

DROP TABLE IF EXISTS fact_activity;

CREATE TABLE fact_activity AS
SELECT
    d.id                                    AS deliverable_id,
    ds.skill_id                             AS skill_key,
    d.profile_id                            AS profile_key,
    d.type_id                               AS deliverable_type_key,
    dd.date_key                             AS date_key,
    d.title                                 AS deliverable_title,
    ds.contribution                         AS contribution,
    CASE WHEN ds.contribution = 3 THEN 1 ELSE 0 END AS is_central_skill,
    -- Was this deliverable cited to justify a level change on this skill?
    CASE WHEN EXISTS (
        SELECT 1 FROM skill_level_change c
        WHERE c.deliverable_id = d.id AND c.skill_id = ds.skill_id
    ) THEN 1 ELSE 0 END                     AS cited_as_evidence,
    d.business_value                        AS business_value
FROM deliverable d
JOIN deliverable_skill ds ON ds.deliverable_id = d.id
JOIN dim_date dd ON dd.full_date = d.published_on
WHERE d.status = 'published'
  AND d.published_on IS NOT NULL;
