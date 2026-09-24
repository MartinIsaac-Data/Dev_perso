#!/usr/bin/env bash
# Checks a release package against a real SQL Server, in Production mode, the way the installer runs it:
#   mode B: the DBA runs sql/migrations.sql (twice: it must be idempotent), the API starts with ApplyMigrations=false;
#   mode A: the API creates the schema itself.
# Each mode: /health answers, the bootstrap admin can sign in, the executive dashboard computes.
#
# usage: verify-package.sh <package-dir> <sqlcmd-container> <sa-password>
set -euo pipefail
pkg=$1; container=$2; sa=$3
port=5185
db_suffix=$RANDOM

sql() { docker exec "$container" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$sa" -C -b "$@"; }

run_api() { # $1 database, $2 ApplyMigrations
  local admin="Adm-$(openssl rand -hex 6)"
  env ASPNETCORE_ENVIRONMENT=Production Database__Provider=SqlServer Database__ApplyMigrations="$2" \
      "ConnectionStrings__Sop=Server=localhost,1433;Database=$1;User Id=sa;Password=$sa;TrustServerCertificate=True" \
      Jwt__Key="$(openssl rand -base64 48)" Bootstrap__AdminUsername=admin Bootstrap__AdminPassword="$admin" \
      Refresh__Enabled=false \
      dotnet "$pkg/api/Broli.SOP.API.dll" --urls "http://127.0.0.1:$port" > "/tmp/verify-$1.log" 2>&1 &
  local pid=$!
  local ok=""
  for _ in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:$port/health" > /dev/null; then ok=1; break; fi
    kill -0 $pid 2>/dev/null || break
    sleep 1
  done
  if [ -z "$ok" ]; then echo "API did not start on $1:"; tail -30 "/tmp/verify-$1.log"; kill $pid 2>/dev/null || true; return 1; fi
  local token
  token=$(curl -sf -H 'Content-Type: application/json' -d "{\"username\":\"admin\",\"password\":\"$admin\"}" \
          "http://127.0.0.1:$port/api/auth/login" | sed -E 's/.*"token":"([^"]+)".*/\1/')
  [ -n "$token" ] || { echo "admin sign-in failed on $1"; kill $pid; return 1; }
  curl -sf -H "Authorization: Bearer $token" "http://127.0.0.1:$port/api/executive" > /dev/null \
    || { echo "executive dashboard failed on $1"; tail -30 "/tmp/verify-$1.log"; kill $pid; return 1; }
  kill $pid; wait $pid 2>/dev/null || true
  echo "  $1: healthy, admin sign-in OK, dashboard OK"
}

echo "Mode B - schema applied by the DBA with sql/migrations.sql"
dbB="broli_pkg_b_$db_suffix"
sql -Q "CREATE DATABASE [$dbB]"
docker cp "$pkg/sql/migrations.sql" "$container:/tmp/migrations.sql"
sql -d "$dbB" -i /tmp/migrations.sql > /dev/null
sql -d "$dbB" -i /tmp/migrations.sql > /dev/null   # second run must be a no-op
applied=$(sql -d "$dbB" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM __EFMigrationsHistory")
expected=$(grep -c . "$pkg/sql/migrations.txt")
[ "$applied" -eq "$expected" ] || { echo "migrations applied: $applied, expected $expected"; exit 1; }
echo "  migrations.sql ran twice, $applied/$expected migrations recorded"
run_api "$dbB" false

echo "Mode B - the API refuses a database the DBA has not migrated"
dbE="broli_pkg_empty_$db_suffix"
sql -Q "CREATE DATABASE [$dbE]"
if run_api "$dbE" false > /dev/null 2>&1; then echo "  the API started on an empty schema"; exit 1; fi
grep -q "not up to date" "/tmp/verify-$dbE.log" || { echo "  no explicit message:"; tail -20 "/tmp/verify-$dbE.log"; exit 1; }
echo "  refused with an explicit message"

echo "Mode A - schema created by the application"
run_api "broli_pkg_a_$db_suffix" true

sql -Q "DROP DATABASE [$dbB]; DROP DATABASE [$dbE]; DROP DATABASE [broli_pkg_a_$db_suffix]" > /dev/null
echo "Package verified."
