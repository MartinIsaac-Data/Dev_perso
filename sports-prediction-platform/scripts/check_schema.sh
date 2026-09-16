#!/usr/bin/env bash
# Applique sql/schema.sql sur une base jetable et vérifie qu'il passe.
# Utilisé en CI : une migration cassée doit échouer avant d'atteindre staging.
set -euo pipefail
cd "$(dirname "$0")/.."

PSQL_URL="${SPP_TEST_DATABASE_URL:-postgresql://spp:spp@localhost:5433/postgres}"
DB="spp_schema_check_$$"

cleanup() { psql "$PSQL_URL" -q -c "DROP DATABASE IF EXISTS ${DB};" >/dev/null 2>&1 || true; }
trap cleanup EXIT

psql "$PSQL_URL" -q -c "CREATE DATABASE ${DB};"
psql "${PSQL_URL%/*}/${DB}" -q -v ON_ERROR_STOP=1 -f sql/schema.sql

echo "Schéma appliqué sans erreur."
psql "${PSQL_URL%/*}/${DB}" -t -c "
  SELECT n.nspname || ' : ' || count(*) || ' relations'
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname IN ('raw','core','stats','market','features','ml','bet','ops')
    AND c.relkind IN ('r','p','v','m')
  GROUP BY n.nspname ORDER BY n.nspname;"
