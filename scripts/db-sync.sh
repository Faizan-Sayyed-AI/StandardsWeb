#!/usr/bin/env bash
#
# Pull the production database down and load it into the local Docker stack.
#
#   ./scripts/db-sync.sh dump                  # fetch a dump from the server
#   ./scripts/db-sync.sh restore <file>        # load a dump into the local DB
#   ./scripts/db-sync.sh sync                  # dump, then restore
#
# Configure the server via env vars (or a .env.dbsync file next to this script):
#
#   SSH_HOST=1.2.3.4            required for `dump`/`sync`
#   SSH_USER=ec2-user           default: ec2-user
#   SSH_KEY=~/.ssh/prod.pem     optional; passed to ssh -i
#   REMOTE_CONTAINER=ists_db    Postgres container name on the server
#   REMOTE_PG_MODE=docker       "docker" (default) or "host" if Postgres runs
#                               directly on the server rather than in a container
#
# Example:
#   SSH_HOST=13.234.5.6 SSH_KEY=~/.ssh/standards.pem ./scripts/db-sync.sh sync
#
# ── WARNING: the dump contains real production data ────────────────────────────
# Password hashes, user emails (PII), audit logs, and encrypted API keys. Dumps
# land in ./backups/ (gitignored). Delete them when you're done.
#
# ── WARNING: `restore` DESTROYS your local database ───────────────────────────
# It drops and recreates the local `ists` database. Local-only data is lost.
#
set -euo pipefail

cd "$(dirname "$0")/.."

# Optional local config file, not committed
[ -f scripts/.env.dbsync ] && . scripts/.env.dbsync

SSH_USER="${SSH_USER:-ec2-user}"
SSH_KEY="${SSH_KEY:-}"
REMOTE_CONTAINER="${REMOTE_CONTAINER:-ists_db}"
REMOTE_PG_MODE="${REMOTE_PG_MODE:-docker}"
REMOTE_DB="${REMOTE_DB:-ists}"
REMOTE_DB_USER="${REMOTE_DB_USER:-ists}"

LOCAL_CONTAINER="${LOCAL_CONTAINER:-ists_db}"
LOCAL_DB="${LOCAL_DB:-ists}"
LOCAL_DB_USER="${LOCAL_DB_USER:-ists}"

DUMP_DIR="${DUMP_DIR:-backups}"

ASSUME_YES="${ASSUME_YES:-0}"

die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }

ssh_cmd() {
  [ -n "$SSH_HOST" ] || die "SSH_HOST is not set. See the header of this script."
  # shellcheck disable=SC2086
  ssh ${SSH_KEY:+-i "$SSH_KEY"} -o BatchMode=yes "$SSH_USER@$SSH_HOST" "$@"
}

# ── dump ──────────────────────────────────────────────────────────────────────
do_dump() {
  : "${SSH_HOST:?SSH_HOST is required for dump — see the header of this script}"
  mkdir -p "$DUMP_DIR"
  local stamp out
  stamp="$(date +%Y%m%d-%H%M%S)"
  out="$DUMP_DIR/${REMOTE_DB}-${stamp}.dump"

  info "Checking SSH connectivity to $SSH_USER@$SSH_HOST"
  ssh_cmd true || die "Cannot SSH to $SSH_USER@$SSH_HOST (check SSH_HOST/SSH_USER/SSH_KEY and that your IP is allowed on port 22)"

  info "Dumping '$REMOTE_DB' from the server (custom format, compressed)"
  # -Fc = custom format: compressed, and restorable with pg_restore.
  # Streamed straight to a local file so nothing is written to the server's disk.
  if [ "$REMOTE_PG_MODE" = "docker" ]; then
    ssh_cmd "docker exec -i '$REMOTE_CONTAINER' pg_dump -U '$REMOTE_DB_USER' -d '$REMOTE_DB' -Fc" > "$out"
  else
    ssh_cmd "pg_dump -U '$REMOTE_DB_USER' -d '$REMOTE_DB' -Fc" > "$out"
  fi

  # pg_dump exiting non-zero mid-stream can still leave a small file behind
  if [ ! -s "$out" ]; then
    rm -f "$out"
    die "Dump was empty — nothing written. Check REMOTE_CONTAINER ('$REMOTE_CONTAINER') and REMOTE_PG_MODE ('$REMOTE_PG_MODE')."
  fi

  info "Dump saved: $out ($(du -h "$out" | cut -f1))"
  DUMP_FILE="$out"
}

# ── restore ───────────────────────────────────────────────────────────────────
do_restore() {
  local file="$1"
  [ -f "$file" ] || die "Dump file not found: $file"

  docker compose ps --status running --services 2>/dev/null | grep -qx db \
    || die "Local 'db' container is not running. Start it with: docker compose up -d db"

  if [ "$ASSUME_YES" != "1" ]; then
    printf '\nThis DROPS and recreates the local "%s" database.\n' "$LOCAL_DB"
    printf 'All local-only data will be lost. Restoring from: %s\n' "$file"
    printf 'Type "yes" to continue: '
    read -r reply
    [ "$reply" = "yes" ] || die "Aborted by user."
  fi

  info "Stopping app containers so they release DB connections"
  docker compose stop web worker beat >/dev/null 2>&1 || true

  info "Terminating any remaining connections to '$LOCAL_DB'"
  docker exec -i "$LOCAL_CONTAINER" psql -U "$LOCAL_DB_USER" -d postgres -v ON_ERROR_STOP=1 -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$LOCAL_DB' AND pid <> pg_backend_pid();" >/dev/null

  info "Recreating database '$LOCAL_DB'"
  docker exec -i "$LOCAL_CONTAINER" psql -U "$LOCAL_DB_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS $LOCAL_DB;" -c "CREATE DATABASE $LOCAL_DB OWNER $LOCAL_DB_USER;" >/dev/null

  # Dump format is detected from the file itself rather than the extension:
  # pg_dump -Fc (custom) starts with the magic bytes "PGDMP" and needs
  # pg_restore; plain-SQL dumps are fed to psql instead.
  local fmt
  if [ "$(head -c 5 "$file")" = "PGDMP" ]; then
    fmt=custom
  elif gzip -t "$file" 2>/dev/null; then
    fmt=gzip
  else
    fmt=plain
  fi
  info "Restoring dump (format: $fmt) — this can take a while"

  case "$fmt" in
    custom)
      # --no-owner/--no-privileges: the dump may reference roles that don't
      # exist locally. Extension/comment warnings are normal and non-fatal, so
      # no --exit-on-error; the verification step below is the real check.
      docker exec -i "$LOCAL_CONTAINER" pg_restore -U "$LOCAL_DB_USER" -d "$LOCAL_DB" \
        --no-owner --no-privileges < "$file" \
        || info "pg_restore reported warnings (usually harmless — verifying below)"
      ;;
    gzip)
      gunzip -c "$file" | docker exec -i "$LOCAL_CONTAINER" \
        psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB" -v ON_ERROR_STOP=1 -q \
        || die "psql restore failed"
      ;;
    plain)
      docker exec -i "$LOCAL_CONTAINER" \
        psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB" -v ON_ERROR_STOP=1 -q < "$file" \
        || die "psql restore failed"
      ;;
  esac

  info "Restarting app containers"
  docker compose start web worker beat >/dev/null

  info "Applying any migrations the dump predates (e.g. api_keys)"
  # Production may be on an older schema than this checkout. Bring it up to head
  # so the local app matches the code you're running.
  sleep 3
  docker compose exec -T web alembic upgrade head || die "alembic upgrade failed — inspect with: docker compose logs web"

  info "Verifying"
  docker exec -i "$LOCAL_CONTAINER" psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB" -c "
    SELECT 'feeds' AS table, count(*) FROM rss_feeds
    UNION ALL SELECT 'standards', count(*) FROM standards
    UNION ALL SELECT 'users', count(*) FROM users
    UNION ALL SELECT 'api_keys', count(*) FROM api_keys;"

  cat <<'NOTE'

==> Done. Two things to know:

 1. api_keys.key_value is encrypted with API_KEY_ENCRYPTION_KEY. If your local
    .env has a different key than production, feed polling will fail locally
    with "Could not decrypt secret". Copy the production value into your local
    .env, or re-add the keys locally via POST /api-keys.

 2. Feeds restored from production keep their api_key_id. If production had
    feeds with no key assigned, run:
       docker compose exec web python scripts/backfill_api_keys.py

NOTE
}

# ── main ──────────────────────────────────────────────────────────────────────
case "${1:-}" in
  dump)
    do_dump
    ;;
  restore)
    [ -n "${2:-}" ] || die "Usage: $0 restore <dump-file>"
    do_restore "$2"
    ;;
  sync)
    do_dump
    do_restore "$DUMP_FILE"
    ;;
  *)
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
