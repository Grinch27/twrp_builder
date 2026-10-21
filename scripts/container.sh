#!/usr/bin/env bash
# Requirements: disposable Ubuntu 22.04 container, reviewed inputs, unprivileged build.
# Ambiguity: upstream dependency closure and the first complete build are unverified.
# Research: inspect the first failed stage before changing the locked manifest.
# Optimization: source-provided JDK/Clang/Python; four compilation jobs.
# Risks: disk/memory exhaustion; no host devices or Docker socket are mounted.
# Validation: dependency setup, real compile exit status and independent image checks.
set -euo pipefail

: "${BUILDER_UID:?}"
: "${BUILDER_GID:?}"
[[ "${BUILDER_UID}" =~ ^[1-9][0-9]*$ && "${BUILDER_GID}" =~ ^[1-9][0-9]*$ ]]
run_sudo apt-get -qq update
run_sudo apt-get -yqq --no-install-recommends install \
  bc bison build-essential ca-certificates cpio curl file flex g++-multilib \
  gcc-multilib git gnupg gperf lib32ncurses-dev lib32readline-dev lib32z1-dev \
  libelf-dev liblz4-tool libncurses5 libncurses-dev libssl-dev \
  libxml2-utils lzop pngcrush python-is-python3 python3 rsync unzip \
  util-linux xsltproc zip zlib1g-dev
groupadd --gid "${BUILDER_GID}" builder
useradd --no-log-init --create-home --uid "${BUILDER_UID}" --gid "${BUILDER_GID}" builder
exec runuser -u builder -- bash /builder/self/scripts/build.sh
