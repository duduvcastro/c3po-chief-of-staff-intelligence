#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] && [ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] && [ "${GITHUB_ACTIONS:-}" = true ] || exit 1
sha256sum -c --quiet SHA256SUMS
mkdir -p linux_root
sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted GITHUB_ACTIONS=true /usr/bin/python3 -I -B linux_root/secret_config_proof.py > linux_root/SHAPES.secret-config.json
sha256sum -c --quiet SHA256SUMS
