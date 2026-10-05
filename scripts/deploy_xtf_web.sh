#!/usr/bin/env bash
set -euo pipefail

readonly DEFAULT_DEPLOY_TARGET="ubuntu@51.161.113.154"
readonly REPOSITORY_URL="https://github.com/Master-Cas/XRay-Texts-Forensics.git"
readonly PUBLIC_BASE_URL="https://xtf.technolution.cl"
readonly DEPLOY_TARGET="${XTF_DEPLOY_TARGET:-$DEFAULT_DEPLOY_TARGET}"
readonly REMOTE_LOCK="/opt/xtf/deploy/.deploy.lock"

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy_xtf_web.sh <40-hex-git-sha>
  scripts/deploy_xtf_web.sh --dry-run <40-hex-git-sha>

The SHA must exactly match the current origin/main SHA. --dry-run performs
validation and prints the production plan without opening an SSH connection.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

validate_sha() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "SHA must be exactly 40 lowercase hex characters"
}

verify_local_origin_main() {
  local sha="$1"
  local origin_main
  origin_main="$(git ls-remote origin refs/heads/main | awk 'NR == 1 {print $1}')"
  [[ "$origin_main" =~ ^[0-9a-f]{40}$ ]] || die "could not resolve origin/main"
  [[ "$sha" == "$origin_main" ]] || die "requested SHA does not match current origin/main"
  printf 'Verified origin/main: %s\n' "$sha"
}

dry_run_plan() {
  local sha="$1"
  cat <<EOF
DRY RUN — no SSH connection will be opened.
Target: $DEFAULT_DEPLOY_TARGET
Public URL: $PUBLIC_BASE_URL
Release: /opt/xtf/releases/$sha
Image: xtf:$sha
Persistent data: /var/lib/xtf (preserved and backed up)
Reference library: /opt/xtf/reference-data/library (preserved read-only)
Compose base: /opt/xtf/deploy/compose.yaml (not rewritten)
Runtime override: /opt/xtf/deploy/compose.release.yaml
Environment file: /opt/xtf/deploy/xtf.env (never modified)
Cutover: XTF service only; Caddy is not restarted
Health gate: /api/v1/health + /api/v1/ready, both must report build_sha=$sha
Rollback: restore prior symlink/runtime override and restart prior XTF service
EOF
}

dry_run=0
case "$#" in
  1)
    sha="$1"
    ;;
  2)
    [[ "$1" == "--dry-run" ]] || { usage >&2; exit 2; }
    dry_run=1
    sha="$2"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

validate_sha "$sha"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || die "run this script from an XRay repository checkout"
cd "$repo_root"
verify_local_origin_main "$sha"

if (( dry_run )); then
  dry_run_plan "$sha"
  exit 0
fi

printf 'Deploying XTF Web SHA %s to %s\n' "$sha" "$DEPLOY_TARGET"

ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$DEPLOY_TARGET" \
  "flock -n '$REMOTE_LOCK' bash -s -- '$sha'" <<'REMOTE_SCRIPT'
set -euo pipefail
umask 077

sha="$1"
repository_url="https://github.com/Master-Cas/XRay-Texts-Forensics.git"
public_base_url="https://xtf.technolution.cl"
xtf_root="/opt/xtf"
current_link="$xtf_root/current"
releases_root="$xtf_root/releases"
deploy_dir="$xtf_root/deploy"
compose_file="$deploy_dir/compose.yaml"
runtime_override="$deploy_dir/compose.release.yaml"
dockerfile="$deploy_dir/Dockerfile"
env_file="$deploy_dir/xtf.env"
data_root="/var/lib/xtf"
reference_root="$xtf_root/reference-data/library"
backups_root="$xtf_root/backups"
service="xtf"
container="xtf-xtf-1"
image="xtf:$sha"
release="$releases_root/$sha"

log() {
  printf '[xtf-deploy] %s\n' "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "invalid SHA"
for path in "$compose_file" "$dockerfile" "$env_file" "$data_root" "$reference_root"; do
  [[ -e "$path" ]] || fail "required production path is missing: $path"
done

remote_main="$(git ls-remote "$repository_url" refs/heads/main | awk 'NR == 1 {print $1}')"
[[ "$remote_main" =~ ^[0-9a-f]{40}$ ]] || fail "could not resolve authorized remote main"
[[ "$sha" == "$remote_main" ]] || fail "requested SHA no longer matches authorized remote main"
log "Verified authorized remote main: $sha"

public_endpoint_matches() {
  local path="$1"
  local expected_status="$2"
  curl --fail --silent --show-error --max-time 10 "$public_base_url$path" |
    python3 -c '
import json
import sys
expected_sha, expected_status = sys.argv[1], sys.argv[2]
payload = json.load(sys.stdin)
raise SystemExit(
    0 if payload.get("build_sha") == expected_sha
    and payload.get("status") == expected_status else 1
)
' "$sha" "$expected_status"
}

current_sha="$(basename "$(readlink -f "$current_link" 2>/dev/null || true)")"
running_image="$(sudo -n docker inspect "$container" --format '{{.Config.Image}}' 2>/dev/null || true)"
running_health="$(sudo -n docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
if [[ "$current_sha" == "$sha" && "$running_image" == "$image" && "$running_health" == "healthy" ]] \
  && public_endpoint_matches "/api/v1/health" "ok" \
  && public_endpoint_matches "/api/v1/ready" "ready"; then
  log "SHA $sha is already deployed and healthy; nothing to do."
  exit 0
fi

mkdir -p "$releases_root"
install -d -m 0700 "$backups_root"
if [[ ! -d "$release/.git" ]]; then
  [[ ! -e "$release" ]] || fail "release path exists but is not a Git checkout: $release"
  git clone --quiet "$repository_url" "$release"
fi
git -C "$release" remote set-url origin "$repository_url"
git -C "$release" fetch --quiet origin main
[[ "$(git -C "$release" rev-parse FETCH_HEAD)" == "$sha" ]] ||
  fail "remote main changed while preparing release"
git -C "$release" checkout --quiet --detach "$sha"
[[ "$(git -C "$release" rev-parse HEAD)" == "$sha" ]] || fail "release checkout mismatch"
[[ -z "$(git -C "$release" status --porcelain=v1)" ]] || fail "release checkout is dirty"
log "Prepared detached release: $release"

sudo -n docker build --pull -f "$dockerfile" -t "$image" "$release"
sudo -n docker run --rm -e "XRAY_BUILD_SHA=$sha" "$image" python -c '
import importlib.metadata
from xray_text_forensics.web import WebSettings
settings = WebSettings.from_environment()
assert settings.build_sha is not None and len(settings.build_sha) == 40
assert importlib.metadata.version("xray-texts-forensics")
'
log "Image smoke passed: $image"

compose_service_image() {
  sudo -n docker compose "$@" config --format json |
    python3 -c '
import json
import sys
payload = json.load(sys.stdin)
service = sys.argv[1]
image = payload.get("services", {}).get(service, {}).get("image")
if not isinstance(image, str) or not image:
    raise SystemExit(1)
print(image)
' "$service"
}

old_current="$(readlink -f "$current_link")"
old_image="$(sudo -n docker inspect "$container" --format '{{.Config.Image}}')"
restore_compose_args=(-f "$compose_file")
if [[ -f "$runtime_override" ]]; then
  previous_override=1
  restore_compose_args+=(-f "$runtime_override")
else
  previous_override=0
fi
resolved_old_image="$(compose_service_image "${restore_compose_args[@]}")"
[[ "$resolved_old_image" == "$old_image" ]] ||
  fail "pre-cutover compose image does not match running image"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$backups_root/$timestamp"
install -d -m 0700 "$backup_dir"
install -m 0600 "$compose_file" "$backup_dir/compose.yaml"
printf '%s\n' "$old_current" > "$backup_dir/current.target"
printf '%s\n' "$old_image" > "$backup_dir/previous-image.txt"
chmod 0600 "$backup_dir/current.target" "$backup_dir/previous-image.txt"
if (( previous_override )); then
  install -m 0600 "$runtime_override" "$backup_dir/compose.release.yaml"
fi

cutover_started=0
rollback() {
  local rc="$?"
  local rollback_failed=0
  local restored_image=""
  local restored_resolved_image=""
  local state="unknown"
  trap - ERR
  if (( cutover_started )); then
    log "Cutover failed; restoring prior XTF release/config."
    ln -sfn "$old_current" "$current_link"
    if (( previous_override )); then
      install -m 0600 "$backup_dir/compose.release.yaml" "$runtime_override"
    else
      rm -f "$runtime_override"
    fi

    restore_compose_args=(-f "$compose_file")
    [[ -f "$runtime_override" ]] && restore_compose_args+=(-f "$runtime_override")
    restored_resolved_image="$(compose_service_image "${restore_compose_args[@]}" 2>/dev/null || true)"
    if [[ "$restored_resolved_image" != "$old_image" ]]; then
      log "ROLLBACK FAILED: restored Compose resolves '$restored_resolved_image', expected '$old_image'."
      rollback_failed=1
    elif ! sudo -n docker compose "${restore_compose_args[@]}" up -d --no-deps "$service" >/dev/null; then
      log "ROLLBACK FAILED: docker compose could not restore XTF."
      rollback_failed=1
    else
      for _ in $(seq 1 30); do
        state="$(sudo -n docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
        [[ "$state" == "healthy" ]] && break
        sleep 2
      done
      restored_image="$(sudo -n docker inspect "$container" --format '{{.Config.Image}}' 2>/dev/null || true)"
      if [[ "$restored_image" != "$old_image" ]]; then
        log "ROLLBACK FAILED: restored container image '$restored_image', expected '$old_image'."
        rollback_failed=1
      fi
      if [[ "$state" != "healthy" ]]; then
        log "ROLLBACK FAILED: restored container state is '${state:-unknown}'."
        rollback_failed=1
      fi
    fi
    if (( rollback_failed )); then
      log "ROLLBACK FAILED: manual recovery is required."
    else
      log "Rollback verified: image=$old_image state=healthy"
    fi
  fi
  exit "$rc"
}
trap rollback ERR

log "Stopping only XTF for a consistent data backup."
sudo -n docker stop "$container" >/dev/null
cutover_started=1
sudo -n tar --numeric-owner -C /var/lib -czf - xtf > "$backup_dir/xtf-data.tgz"
chmod 0600 "$backup_dir/xtf-data.tgz"
log "Consistent private data backup created: $backup_dir/xtf-data.tgz"

override_tmp="$runtime_override.tmp.$$"
cat > "$override_tmp" <<EOF
services:
  xtf:
    image: $image
    environment:
      XRAY_BUILD_SHA: "$sha"
EOF
mv "$override_tmp" "$runtime_override"
chmod 0600 "$runtime_override"
ln -sfn "$release" "$current_link"

compose_args=(-f "$compose_file" -f "$runtime_override")
sudo -n docker compose "${compose_args[@]}" config -q
sudo -n docker compose "${compose_args[@]}" up -d --no-deps "$service" >/dev/null

state="unknown"
for _ in $(seq 1 45); do
  state="$(sudo -n docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  [[ "$state" == "healthy" ]] && break
  [[ "$state" =~ ^(unhealthy|exited|dead)$ ]] && fail "new XTF container entered state $state"
  sleep 2
done
[[ "$state" == "healthy" ]] || fail "new XTF container did not become healthy"

public_endpoint_matches "/api/v1/health" "ok" || fail "public health gate failed"
public_endpoint_matches "/api/v1/ready" "ready" || fail "public readiness/build gate failed"

[[ "$(readlink -f "$current_link")" == "$release" ]] || fail "current symlink mismatch after cutover"
[[ "$(sudo -n docker inspect "$container" --format '{{.Config.Image}}')" == "$image" ]] ||
  fail "running image mismatch after cutover"

cutover_started=0
trap - ERR
log "Deployment complete: $sha"
log "Backup retained at: $backup_dir"
REMOTE_SCRIPT
