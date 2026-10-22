#!/usr/bin/env bash
# Requirements: fresh work, archive manifest plus public CTS/annotation projects.
# Ambiguity: 284 full checkouts have not yet passed a clean bootimage build.
# Research: stop at the first failure; no automated dependency suppression.
# Optimization: bounded sync/build time, JDK/Clang from the selected Android tree.
# Risks: source availability, old prebuilts, capacity; preserve the failure logs.
# Validation: exact checkout identities, mka exit 0, AVB and boot payload checks.
set -eo pipefail
umask 077
SELF=/builder/self
WORK=/builder/work
stage=initialization
mkdir -p "${WORK}/logs" "${WORK}/output"
set_stage() {
  stage="$1"
  python3 - "${WORK}/output/status.json" "${stage}" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'stage':sys.argv[2]})+'\n')
PY
}
finish() {
  local result=$?
  trap - EXIT
  if ((result != 0)) && [[ "${stage}" == compile && -f "${WORK}/logs/compile.log" ]]; then
    if ! python3 "${SELF}/scripts/summarize_compile_failure.py" \
      --log "${WORK}/logs/compile.log" --manifest "${WORK}/manifest/default.xml" \
      --source "${WORK}/android" --output "${WORK}/output/compile-error-summary.json"; then
      printf 'Structured compiler diagnostics unavailable.\n' >&2
    fi
  fi
  if ((result != 0)) && [[ -n "${phase_log:-}" && -f "${phase_log}" ]]; then
    if ! python3 "${SELF}/scripts/summarize_repo_failure.py" \
      --log "${phase_log}" --manifest "${WORK}/manifest/default.xml" \
      --output "${WORK}/output/source-error-summary.json"; then
      printf 'Structured repository diagnostics unavailable.\n' >&2
    fi
  fi
  python3 - "${WORK}/output/status.json" "${stage}" "${result}" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"stage":sys.argv[2],"exit_code":int(sys.argv[3])})+'\n')
PY
  exit "${result}"
}
trap finish EXIT

# This file is invoked only in a newly created work directory.
[[ ! -e "${WORK}/android" && ! -e "${WORK}/out" && ! -e "${WORK}/manifest" ]]
read -r repo_ref repo_commit launcher_digest < <(python3 - "${SELF}/source.lock.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))['repo_tool']
print(d['version'],d['commit'],d['launcher_sha256'])
PY
)
mkdir "${WORK}/bin" "${WORK}/manifest" "${WORK}/android" "${WORK}/tmp"
set_stage repo_tool
curl --fail --silent --show-error --location --retry 2 \
  "https://raw.githubusercontent.com/GerritCodeReview/git-repo/${repo_commit}/repo" \
  --output "${WORK}/bin/repo"
printf '%s  %s\n' "${launcher_digest}" "${WORK}/bin/repo" | sha256sum --check --status
chmod 0755 "${WORK}/bin/repo"
export PATH="${WORK}/bin:${PATH}"
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME=twrp-builder GIT_COMMITTER_NAME=twrp-builder
export GIT_AUTHOR_EMAIL=twrp-builder@users.noreply.github.com
export GIT_COMMITTER_EMAIL=twrp-builder@users.noreply.github.com
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=twrp-builder
export GIT_CONFIG_KEY_1=user.email GIT_CONFIG_VALUE_1=twrp-builder@users.noreply.github.com
python3 "${SELF}/scripts/source_inputs.py" compose \
  --manifest "${WORK}/inputs/default.xml" --output "${WORK}/manifest/default.xml"
git -C "${WORK}/manifest" init --initial-branch=main --quiet
git -C "${WORK}/manifest" add default.xml
git -C "${WORK}/manifest" commit --quiet -m 'Use reviewed locked manifest'

set_stage repo_initialization
cd "${WORK}/android"
phase_log="${WORK}/logs/repo-init.log"
timeout --signal=TERM --kill-after=30s 180s \
  repo init --manifest-url="file://${WORK}/manifest" --manifest-branch=main \
  --manifest-name=default.xml --depth=1 --groups=all --no-clone-bundle \
  --no-use-superproject --repo-rev="${repo_ref}" > "${phase_log}" 2>&1
set_stage repo_tool_verification
[[ "$(git -C .repo/repo rev-parse HEAD)" == "${repo_commit}" ]]
set_stage source_sync
phase_log="${WORK}/logs/repo-sync.log"
timeout --signal=TERM --kill-after=60s 140m \
  repo sync -c -j4 --no-clone-bundle --no-tags --fail-fast --retry-fetches=2 > "${phase_log}" 2>&1
phase_log=

set_stage checkout_verification
python3 "${SELF}/scripts/source_inputs.py" checkout \
  --manifest "${WORK}/inputs/default.xml" --source "${WORK}/android"
[[ "$(git -C device/xiaomi/selene rev-parse HEAD)" == c77512445ab5be5908ddb3ca9c659e6b149c78de ]]
cp -a "${WORK}/inputs/overlay/." "${WORK}/android/"
cp -a "${WORK}/inputs/prebuilts" "${WORK}/prebuilts"

set_stage preflight
[[ "$(df --output=avail -B1 "${WORK}" | tail -n 1)" -ge 19327352832 ]]
test -s prebuilts/jdk/jdk11/linux-x86/lib/modules
test -s prebuilts/tools/common/m2/repository/com/android/support/test/monitor/1.0.2-alpha1/monitor-1.0.2-alpha1.aar
prebuilts/jdk/jdk11/linux-x86/bin/java -version
export OUT_DIR="${WORK}/out"
export TMPDIR="${WORK}/tmp"
export GOMAXPROCS=2
unset ALLOW_MISSING_DEPENDENCIES PYTHONPATH PYTHONHOME
# Android envsetup is not nounset-compatible. lunch must run in this shell.
set +u
source build/envsetup.sh
lunch twrp_selene-eng
[[ "${TARGET_PRODUCT}" == twrp_selene && "${TARGET_BUILD_VARIANT}" == eng ]]

set_stage compile
# mka is a shell function. The child shell explicitly reconstructs its environment.
timeout --signal=TERM --kill-after=60s 160m bash -c '
  set -eo pipefail
  source build/envsetup.sh
  lunch twrp_selene-eng
  mka bootimage -j4
' > "${WORK}/logs/compile.log" 2>&1

set_stage static_validation
image="${OUT_DIR}/target/product/selene/boot.img"
python3 external/avb/avbtool.py info_image --image "${image}"
python3 external/avb/avbtool.py verify_image --image "${image}" \
  --key external/avb/test/data/testkey_rsa2048.pem
python3 "${SELF}/scripts/verify_boot.py" --image "${image}" \
  --stock "${WORK}/prebuilts/selene-stock-v14" \
  --report "${WORK}/output/static-validation.json"
cp "${image}" "${WORK}/output/boot.img"
cd "${WORK}/output"
sha256sum boot.img static-validation.json > SHA256SUMS
set_stage complete
