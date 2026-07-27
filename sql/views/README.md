# Reporting views

Clean, stable SQL views over the star schema, intended as the contract for
Power BI (Phase 4). Report definitions bind to these, not to the physical
tables, so the tables can be reshaped without breaking every report.

Each view is named `v_<subject>` and carries a comment stating what one row
represents and which measures are safe to aggregate over it.
