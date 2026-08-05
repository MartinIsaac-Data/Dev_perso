#!/usr/bin/env bash
#
# Démarrer MindFlow sur une machine de développement, en une commande.
#
#   ./tool/dev_up.sh          # démarre tout, et attend d'avoir vu /health répondre
#   ./tool/dev_up.sh --stop   # arrête l'API et le worker
#   ./tool/dev_up.sh --token  # imprime un jeton de développement
#
# Ce script existe parce que la marche à suivre de `docs/Deployment.md` §0 tient
# en douze commandes dont trois créent des choses qui ne doivent être créées
# qu'une fois. Il est donc idempotent : le relancer sur une installation déjà
# faite ne recrée rien et ne casse rien.
#
# Deux principes qu'il ne transige pas :
#
#   * **le worker démarre avant l'API.** Une capture déclarée sans worker reste
#     en attente ; l'inverse ne se produit pas (`Deployment.md` §4) ;
#   * **il échoue bruyamment.** Chaque étape est vérifiée. Un script de
#     démarrage qui rend la main sans avoir rien démarré est pire que pas de
#     script du tout : on croit le produit cassé alors qu'il n'a pas été lancé.
#
# Rien ici ne vise la production. `MINDFLOW_ENV` reste `local`, les moteurs IA
# restent `fake`, et les jetons sont non signés — trois choses que le contrôle
# de configuration refuse ailleurs, délibérément.
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BACKEND="$ROOT/backend"
readonly RUNTIME="$ROOT/.dev"

readonly DB_NAME="${MINDFLOW_DEV_DB:-mindflow}"
readonly DB_USER="${MINDFLOW_DEV_DB_USER:-mindflow}"
readonly DB_PASSWORD="${MINDFLOW_DEV_DB_PASSWORD:-mindflow}"
readonly PGPORT_="${PGPORT:-5432}"
readonly API_PORT="${MINDFLOW_DEV_PORT:-8000}"

readonly RED=$'\033[31m' GREEN=$'\033[32m' DIM=$'\033[2m' BOLD=$'\033[1m' OFF=$'\033[0m'

step()  { printf '%s==>%s %s\n' "$BOLD" "$OFF" "$1"; }
ok()    { printf '    %s✓%s %s\n' "$GREEN" "$OFF" "$1"; }
note()  { printf '    %s%s%s\n' "$DIM" "$1" "$OFF"; }
die()   { printf '%s✗ %s%s\n' "$RED" "$1" "$OFF" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 est introuvable. $2"; }

# --------------------------------------------------------------------------
# PostgreSQL
#
# Le rôle et la base doivent être créés par un superutilisateur, et « qui est
# superutilisateur » dépend entièrement de l'installation : `postgres` sur une
# Debian, l'utilisateur courant sur un Homebrew, `postgres` sans sudo dans un
# conteneur. On essaie les trois plutôt que d'en imposer une.
# --------------------------------------------------------------------------
PSQL_SUPER=""

detect_superuser() {
  local candidates=(
    "psql -U postgres -h 127.0.0.1 -p $PGPORT_"
    "psql -h 127.0.0.1 -p $PGPORT_"
    "sudo -n -u postgres psql -p $PGPORT_"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if $candidate -tAc 'SELECT 1' postgres >/dev/null 2>&1; then
      PSQL_SUPER="$candidate"
      return 0
    fi
  done
  return 1
}

super() { $PSQL_SUPER -v ON_ERROR_STOP=1 -tAc "$1" postgres; }

ensure_postgres() {
  step "PostgreSQL"
  if ! pg_isready -q -h 127.0.0.1 -p "$PGPORT_" 2>/dev/null; then
    die "aucun PostgreSQL sur 127.0.0.1:$PGPORT_.
    Démarrez-le, par exemple :
      Debian/Ubuntu   sudo pg_ctlcluster 16 main start
      macOS/Homebrew  brew services start postgresql@16
      Docker          docker run -d --name mindflow-pg -p 5432:5432 \\
                        -e POSTGRES_HOST_AUTH_METHOD=trust pgvector/pgvector:pg16"
  fi
  ok "en écoute sur 127.0.0.1:$PGPORT_"

  detect_superuser || die "connexion superutilisateur impossible sur le port $PGPORT_.
    Le script doit créer un rôle et une base une seule fois. Essayez :
      sudo -u postgres psql -c \"CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD'\"
      sudo -u postgres psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER\"
    puis relancez ce script."

  if [ "$(super "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != "1" ]; then
    super "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD'" >/dev/null
    ok "rôle $DB_USER créé"
  else
    ok "rôle $DB_USER déjà présent"
  fi

  if [ "$(super "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" != "1" ]; then
    super "CREATE DATABASE $DB_NAME OWNER $DB_USER" >/dev/null
    ok "base $DB_NAME créée"
  else
    ok "base $DB_NAME déjà présente"
  fi

  # pgvector doit exister avant la migration 0006, qui la trouve et continue.
  # Sur un PostgreSQL managé où `CREATE EXTENSION` est refusé, c'est ici que ça
  # se voit — et c'est le prérequis P1 du plan de déploiement.
  if ! $PSQL_SUPER -v ON_ERROR_STOP=1 -q -c 'CREATE EXTENSION IF NOT EXISTS vector' "$DB_NAME" 2>/dev/null; then
    die "l'extension pgvector n'a pas pu être créée dans $DB_NAME.
    Elle n'est pas incluse avec PostgreSQL : installez le paquet
    (Debian : postgresql-16-pgvector ; Homebrew : pgvector ; ou l'image
    pgvector/pgvector:pg16), puis relancez."
  fi
  ok "extension pgvector disponible"
}

# --------------------------------------------------------------------------
# Redis
#
# Sans lui, aucune capture n'est traitée : l'API accepte, met en file, et
# personne ne dépile. On le démarre plutôt que de le réclamer, parce que
# `redis-server --daemonize yes` n'a aucune conséquence sur une machine de
# développement.
# --------------------------------------------------------------------------
ensure_redis() {
  step "Redis"
  if redis-cli ping >/dev/null 2>&1; then
    ok "déjà en écoute"
    return
  fi
  command -v redis-server >/dev/null 2>&1 || die "Redis est introuvable.
    Installez-le (Debian : sudo apt install redis-server ; macOS : brew install redis)
    ou lancez : docker run -d --name mindflow-redis -p 6379:6379 redis:7"
  # `dir` explicite : sinon le dump atterrit dans le dossier courant, donc dans
  # le dépôt.
  mkdir -p "$RUNTIME"
  redis-server --daemonize yes --dir "$RUNTIME" >/dev/null
  for _ in $(seq 1 20); do
    redis-cli ping >/dev/null 2>&1 && break
    sleep 0.25
  done
  redis-cli ping >/dev/null 2>&1 || die "Redis n'a pas démarré."
  ok "démarré"
}

# --------------------------------------------------------------------------
# Configuration et schéma
# --------------------------------------------------------------------------
ensure_env() {
  step "Configuration"
  mkdir -p "$RUNTIME/objects"
  if [ ! -f "$BACKEND/.env" ]; then
    cp "$BACKEND/.env.example" "$BACKEND/.env"
    ok ".env créé depuis .env.example"
  else
    ok ".env déjà présent, laissé tel quel"
  fi

  # Les deux seules valeurs que le modèle ne peut pas deviner : où écrire les
  # objets, et comment joindre la base qu'on vient de créer. Réécrites
  # uniquement si elles sont encore à leur valeur d'exemple, pour ne jamais
  # écraser une clé d'API que l'utilisateur aurait ajoutée.
  local dsn="postgresql+asyncpg://$DB_USER:$DB_PASSWORD@localhost:$PGPORT_/$DB_NAME"
  python3 - "$BACKEND/.env" "$RUNTIME/objects" "$dsn" <<'PY'
import pathlib, sys

path, objects, dsn = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
defaults = {
    "MINDFLOW_STORAGE_LOCAL_ROOT": ("/var/lib/mindflow/objects", objects),
    "MINDFLOW_DATABASE_URL": (
        "postgresql+asyncpg://mindflow:mindflow@localhost:5432/mindflow", dsn),
}
lines = path.read_text().splitlines()
for i, line in enumerate(lines):
    key, _, value = line.partition("=")
    example, wanted = defaults.get(key.strip(), (None, None))
    if wanted is not None and value.strip() == example:
        lines[i] = f"{key}={wanted}"
path.write_text("\n".join(lines) + "\n")
PY
  ok "objets écrits dans $RUNTIME/objects"
}

ensure_schema() {
  step "Schéma"
  ( cd "$BACKEND" && uv run alembic upgrade head ) 2>&1 | sed 's/^/    /' | grep -E 'Running upgrade|ERROR' || true
  local head
  head="$( cd "$BACKEND" && uv run alembic current 2>/dev/null | tail -1 )"
  [ -n "$head" ] || die "les migrations n'ont pas abouti."
  ok "à jour ($head)"
}

# --------------------------------------------------------------------------
# Processus
# --------------------------------------------------------------------------
pid_file() { printf '%s/%s.pid\n' "$RUNTIME" "$1"; }

is_running() {
  local file; file="$(pid_file "$1")"
  [ -f "$file" ] && kill -0 "$(cat "$file")" 2>/dev/null
}

spawn() {
  local name="$1"; shift
  if is_running "$name"; then
    ok "$name déjà en cours (pid $(cat "$(pid_file "$name")"))"
    return
  fi
  ( cd "$BACKEND" && exec "$@" ) >"$RUNTIME/$name.log" 2>&1 &
  echo $! > "$(pid_file "$name")"
  ok "$name démarré (pid $!) — journal : .dev/$name.log"
}

stop_all() {
  step "Arrêt"
  local name file
  for name in api worker; do
    file="$(pid_file "$name")"
    if is_running "$name"; then
      kill "$(cat "$file")" 2>/dev/null || true
      ok "$name arrêté"
    else
      note "$name n'était pas en cours"
    fi
    rm -f "$file"
  done
  note "PostgreSQL et Redis sont laissés en place : ils servent probablement à autre chose."
}

mint_token() {
  ( cd "$BACKEND" && uv run python -c "
from app.infra.auth.supabase import make_local_token
print(make_local_token('11111111-1111-4111-8111-111111111111', 'dev@example.com'))
" 2>/dev/null )
}

# --------------------------------------------------------------------------
main() {
  case "${1:-}" in
    --stop) stop_all; exit 0 ;;
    --token) mint_token; exit 0 ;;
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "") ;;
    *) die "option inconnue : $1" ;;
  esac

  need uv "Installez-le : curl -LsSf https://astral.sh/uv/install.sh | sh"
  need pg_isready "Il est fourni avec le client PostgreSQL."
  need python3 "Il sert uniquement à ajuster deux lignes du .env."

  ensure_postgres
  ensure_redis
  ensure_env
  ensure_schema

  step "Services"
  # Le worker d'abord : voir l'en-tête.
  spawn worker uv run arq app.workers.settings.WorkerSettings
  spawn api uv run uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"

  step "Vérification"
  local health=""
  for _ in $(seq 1 40); do
    health="$(curl -fsS "http://127.0.0.1:$API_PORT/health" 2>/dev/null || true)"
    [ -n "$health" ] && break
    sleep 0.5
  done
  [ -n "$health" ] || die "l'API n'a pas répondu sur le port $API_PORT.
    Le journal dit pourquoi : tail -50 $RUNTIME/api.log"
  ok "$health"

  # Le worker peut mourir au démarrage sans que l'API s'en aperçoive — c'est
  # exactement ce qui s'est passé pendant quatre phases. On vérifie qu'il a
  # annoncé ses tâches, pas seulement qu'il a un pid.
  if ! grep -q "Starting worker" "$RUNTIME/worker.log" 2>/dev/null; then
    die "le worker n'a pas démarré. Sans lui aucune capture n'est traitée.
    tail -50 $RUNTIME/worker.log"
  fi
  ok "worker à l'écoute de la file capture.realtime"

  cat <<EOF

${BOLD}MindFlow tourne.${OFF}

  API          http://127.0.0.1:$API_PORT        ${DIM}(documentation : /docs)${OFF}
  Journaux     .dev/api.log, .dev/worker.log
  Arrêt        ./tool/dev_up.sh --stop

Le client :

  cd frontend && MINDFLOW_API_BASE_URL=http://127.0.0.1:$API_PORT ./tool/build.sh linux

Ou directement en ligne de commande :

  TOKEN=\$(./tool/dev_up.sh --token)
  curl -s localhost:$API_PORT/v1/dashboard -H "Authorization: Bearer \$TOKEN"

${DIM}Les moteurs de parole et de langage sont sur \`fake\` : ils renvoient du texte
français plausible, hors ligne, sans clé. Pour de vrais résultats, renseignez
MINDFLOW_OPENAI_API_KEY et MINDFLOW_STT_BACKEND dans backend/.env, puis
relancez. Le faux encodeur, lui, produit des vecteurs qui s'indexent avec
succès et n'encodent rien — la recherche sémantique aura l'air de marcher en
renvoyant les mauvaises notes.${OFF}
EOF
}

main "$@"
