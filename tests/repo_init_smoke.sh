#!/usr/bin/env bash
# Requirements: reproduce repo initialization with public, synthetic inputs only.
# Ambiguity: the first private-input build failed before a compiler was invoked.
# Research: expose the initialization error without publishing private build logs.
# Optimization: sync one small public project, never the complete Android tree.
# Risks: upstream availability and ephemeral container package installation.
# Validation: exact repo revision, noninteractive initialization and one-project sync.
set -euo pipefail

if [[ "${1:-}" == container ]]; then
  run_sudo apt-get -qq update
  run_sudo apt-get -yqq --no-install-recommends install ca-certificates curl git gnupg python3 util-linux
  groupadd --gid "${BUILDER_GID}" builder
  useradd --no-log-init --create-home --uid "${BUILDER_UID}" --gid "${BUILDER_GID}" builder
  exec runuser -u builder -- bash /builder/self/tests/repo_init_smoke.sh user
fi

if [[ "${1:-}" == user ]]; then
  cd /builder/work
  read -r repo_ref repo_commit launcher_digest < <(python3 - /builder/self/source.lock.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))['repo_tool']
print(d['version'],d['commit'],d['launcher_sha256'])
PY
  )
  mkdir bin manifest android
  curl --fail --silent --show-error --location --retry 2 --max-time 60 \
    "https://raw.githubusercontent.com/GerritCodeReview/git-repo/${repo_commit}/repo" --output bin/repo
  printf '%s  %s\n' "${launcher_digest}" bin/repo | sha256sum --check --status
  chmod 0755 bin/repo
  export PATH="/builder/work/bin:${PATH}"
  export GIT_TERMINAL_PROMPT=0 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
  export GIT_AUTHOR_NAME=twrp-builder GIT_COMMITTER_NAME=twrp-builder
  export GIT_AUTHOR_EMAIL=twrp-builder@users.noreply.github.com
  export GIT_COMMITTER_EMAIL=twrp-builder@users.noreply.github.com
  export GIT_CONFIG_COUNT=2
  export GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=twrp-builder
  export GIT_CONFIG_KEY_1=user.email GIT_CONFIG_VALUE_1=twrp-builder@users.noreply.github.com
  cat > manifest/default.xml <<'XML'
<manifest>
  <remote name="aosp" fetch="https://android.googlesource.com"/>
  <default remote="aosp" revision="refs/tags/android-12.1.0_r4"/>
  <project name="platform/bionic" path="bionic" revision="11fa611f2c52e17e23f679869724278e2becc862"/>
</manifest>
XML
  git -C manifest init --initial-branch=main --quiet
  git -C manifest add default.xml
  git -C manifest commit --quiet -m 'Public synthetic initialization fixture'
  cd android
  timeout --signal=TERM --kill-after=20s 180s repo init \
    --manifest-url=file:///builder/work/manifest --manifest-branch=main \
    --manifest-name=default.xml --depth=1 --groups=all --no-clone-bundle \
    --no-use-superproject --repo-rev="${repo_ref}" < /dev/null
  [[ "$(git -C .repo/repo rev-parse HEAD)" == "${repo_commit}" ]]
  printf 'PUBLIC_REPO_INIT_SMOKE=PASS\n'
  timeout --signal=TERM --kill-after=20s 180s \
    repo sync -c -j1 --no-clone-bundle --no-tags --fail-fast --retry-fetches=2
  printf 'PUBLIC_REPO_SYNC_SMOKE=PASS\n'
  exit
fi

: "${RUNNER_TEMP:?}"
: "${GITHUB_WORKSPACE:?}"
smoke_root="$(mktemp -d "${RUNNER_TEMP}/repo-init-smoke.XXXXXXXX")"
export BUILDER_UID="$(id -u)" BUILDER_GID="$(id -g)"
sudo_command="$(command -v run_sudo)"
docker run --rm --init --cpus=2 --memory=2g --security-opt=no-new-privileges \
  --env BUILDER_UID --env BUILDER_GID --env DEBIAN_FRONTEND \
  --volume "${GITHUB_WORKSPACE}:/builder/self:ro" \
  --volume "${smoke_root}:/builder/work" \
  --volume "${sudo_command}:/usr/local/bin/run_sudo:ro" \
  --workdir /builder/work "${CONTAINER_IMAGE:-ubuntu:22.04}" \
  bash /builder/self/tests/repo_init_smoke.sh container
