-- =============================================================================
-- dim_deliverable_type
-- Grain: one row per deliverable type.
-- =============================================================================

DROP TABLE IF EXISTS dim_deliverable_type;

CREATE TABLE dim_deliverable_type AS
SELECT
    t.id                                    AS deliverable_type_key,
    t.code                                  AS type_code,
    t.name                                  AS type_name,
    CASE WHEN t.is_publication THEN 1 ELSE 0 END AS is_publication
FROM deliverable_type t

UNION ALL

SELECT -1, 'unknown', 'Unknown type', 0;
