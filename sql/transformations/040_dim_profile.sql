-- =============================================================================
-- dim_profile
-- Grain: one row per profile.
-- =============================================================================
--
-- `is_demo` is carried into the star layer so a report can exclude the
-- demonstration data with a filter rather than by remembering which profile
-- code is fictional.

DROP TABLE IF EXISTS dim_profile;

CREATE TABLE dim_profile AS
SELECT
    p.id                                  AS profile_key,
    p.code                                AS profile_code,
    p.display_name                        AS display_name,
    CASE WHEN p.is_demo THEN 1 ELSE 0 END AS is_demo,
    p.currency                            AS currency
FROM profile p;
