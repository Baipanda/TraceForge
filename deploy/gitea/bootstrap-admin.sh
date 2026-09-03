#!/bin/bash
# Bootstrap Gitea without the flaky web install wizard.
set -euo pipefail

MARKER=/data/gitea/.traceforge_bootstrapped

# Start the official entrypoint in background-equivalent fashion:
# run migrate/admin after gitea is up by using a sidecar loop.
(
  for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:3000/" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if [ ! -f "$MARKER" ]; then
    echo "[traceforge-gitea] running first-time migrate + admin create"
    # Wait a bit more for DB files to settle after first boot.
    sleep 2
    su-exec git gitea migrate || true
    su-exec git gitea admin user create \
      --admin \
      --username "${TRACEFORGE_GITEA_ADMIN_USER:-gitea-admin}" \
      --password "${TRACEFORGE_GITEA_ADMIN_PASSWORD:-TraceForge@2026}" \
      --email "${TRACEFORGE_GITEA_ADMIN_EMAIL:-gitea-admin@traceforge.local}" \
      --must-change-password=false \
      || echo "[traceforge-gitea] admin may already exist, continue"
    touch "$MARKER"
    echo "[traceforge-gitea] bootstrap done"
  fi
) &

exec /usr/bin/entrypoint "$@"
