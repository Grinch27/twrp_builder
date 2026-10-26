#!/usr/bin/env bash
# Requirements: a disposable GitHub-hosted Linux runner, never a personal host.
# Ambiguity: reclaimed space varies with the current runner image.
# Research: if 50 GiB is unavailable, choose a suitable runner explicitly.
# Optimization: numbered cleanup and 12 GiB extra swap for Soong's memory peak.
# Risks: destructive cleanup of disposable SDKs; refuse self-hosted/local execution.
# Validation: runner identity guard, symlink rejection, actual free disk and memory.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]]
: "${RUNNER_TEMP:?}"
: "${GITHUB_ENV:?}"
cleanup_index=0
printf 'Runner preparation: starting approved four-item cleanup.\n'
df -h "${RUNNER_TEMP}"
for unused in /usr/local/lib/android /opt/hostedtoolcache /usr/share/dotnet /usr/local/share/powershell; do
  cleanup_index=$((cleanup_index + 1))
  cleanup_started="$(date +%s)"
  printf 'Runner cleanup item %s/4: start\n' "${cleanup_index}"
  [[ ! -L "${unused}" ]]
  run_sudo rm -rf -- "${unused}"
  printf 'Runner cleanup item %s/4: complete, elapsed=%ss\n' \
    "${cleanup_index}" "$(( $(date +%s) - cleanup_started ))"
done
available="$(df --output=avail -B1 "${RUNNER_TEMP}" | tail -n 1)"
if (( available < 66571993088 )); then
  printf 'At least 62 GiB free is required for 12 GiB swap and 50 GiB source space.\n' >&2
  exit 1
fi
memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
(( memory_kib >= 12582912 ))
build_root="$(mktemp -d "${RUNNER_TEMP}/twrp-selene.XXXXXXXX")"
mkdir "${build_root}/logs"
printf 'BUILD_ROOT=%s\n' "${build_root}" >> "${GITHUB_ENV}"
swap_path="${build_root}/native-swap"
run_sudo install -m 0600 /dev/null "${swap_path}"
run_sudo fallocate -l 12G "${swap_path}"
run_sudo mkswap "${swap_path}" > /dev/null
run_sudo swapon "${swap_path}"
printf 'Disposable runner: added 12 GiB swap; original swap remains active.\n'
df -h "${build_root}"
