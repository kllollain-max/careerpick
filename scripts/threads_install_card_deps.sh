#!/usr/bin/env bash
# Public dependency downloads only. Never send, reserve or change source checks.
set -euo pipefail
retry_download() {
  local attempt status
  for attempt in 1 2 3; do
    if timeout 90 "$@"; then
      return 0
    else
      status=$?
    fi
    if [[ "$attempt" == 3 ]]; then
      echo "Dependency download failed after 3 attempts (exit $status)" >&2
      return "$status"
    fi
    echo "Dependency download unavailable; retry $attempt of 2" >&2
    sleep 2
  done
}
retry_download sudo apt-get -o Acquire::Retries=0 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update -qq
retry_download sudo apt-get -o Acquire::Retries=0 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 install -y fonts-nanum
retry_download python -m pip --retries 0 --timeout 20 install 'Pillow>=10,<13'
