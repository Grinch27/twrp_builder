# Builder maintenance contract

Read README.md, AUDIT.md and source.lock.json before changes. Use Chinese for user-facing reports. This repository is a build orchestrator; Grinch27/twrp_selene remains a read-only private archive unless the current user explicitly changes that scope.

- Device/firmware: selene, China MIUI V14.0.4.0.TKUCNXM. Target: twrp_selene-eng / bootimage. Do not silently substitute a Global/India or MIUI 12.5 tree.
- Preserve the small source-input allowlist. Never copy private archive source, logs, identifiers from device logs, credentials, historical artifacts or backups into this public repository or public Actions logs.
- A new script starts with comments listing requirements, ambiguity, research, optimization, risks and validation. Do not set HOME/CODEX_HOME or change global Java/Python on a host.
- Use independent output directories, bounded sync/build time and a real exit status. Stop at the first failure. Do not add ALLOW_MISSING_DEPENDENCIES, BUILD_BROKEN flags, test disabling, permissive SELinux or cross-version binary substitutes to make a build appear successful. The four inherited BoardConfig flags are disclosed, not newly approved workarounds.
- push/PR run static validation and a bounded repo initialization/sync smoke test with a public synthetic manifest and one public bionic project. The smoke test never reads private inputs or secrets and never syncs the full Android tree. A manual build reads ten private inputs using a user-configured read-only secret; do not dispatch it without the requested source-processing authorization. Public artifacts/releases require explicit publish=true. Paid runners and external private-log storage require separate approval.
- The disk cleanup script may run only on a disposable GitHub-hosted runner during the explicitly triggered build; never run it locally or on self-hosted infrastructure.
- Run the standard-library unit suite, bash -n, YAML parsing and actionlint when available. Validate actual manifest/overlay identities locally without adding those private fixtures to this repo. No delegation/subagents unless explicitly requested.
- An image requires static verification in addition to compilation. Compilation and synthetic test fixtures never prove device boot, touch, FBE, backup/restore or flash safety. Do not access devices or modify partitions.
- Before remote writes inspect current refs and changes. Never force-push, overwrite existing Releases, remove archived evidence or expand the input allowlist without explicit authorization.
