#!/usr/bin/env bash
# Requirements: a disposable GitHub-hosted Linux runner, never a personal host.
# Ambiguity: reclaimed space varies with the current runner image.
# Research: if 50 GiB is unavailable, choose a suitable runner explicitly.
# Optimization: remove only the listed preinstalled SDK/tool caches before syncing.
# Risks: destructive cleanup of disposable SDKs; refuse self-hosted/local execution.
# Validation: runner identity guard, symlink rejection, actual free disk and memory.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]]
: "${RUNNER_TEMP:?}"
: "${GITHUB_ENV:?}"
for unused in /usr/local/lib/android /opt/hostedtoolcache /usr/share/dotnet /usr/local/share/powershell; do
  [[ ! -L "${unused}" ]]
  run_sudo rm -rf -- "${unused}"
done
available="$(df --output=avail -B1 "${RUNNER_TEMP}" | tail -n 1)"
if (( available < 53687091200 )); then
  printf 'At least 50 GiB free is required; stop before source download.\n' >&2
  exit 1
fi
memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
(( memory_kib >= 12582912 ))
build_root="$(mktemp -d "${RUNNER_TEMP}/twrp-selene.XXXXXXXX")"
mkdir "${build_root}/logs"
printf 'BUILD_ROOT=%s\n' "${build_root}" >> "${GITHUB_ENV}"
df -h "${build_root}"
