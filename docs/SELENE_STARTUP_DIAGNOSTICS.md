# selene keystore2 等待：Native 构建修正

日期：2026-11-01（Asia/Shanghai）。远端基线：`main@b8dcc69345a8b76345da1f1ec0746ef6254200c8`。本页前半部分是本轮已批准的构建修正，后半部分保留第一轮历史记录。

## 当前证据与目标

第一轮诊断构建 [41026784027](https://github.com/Grinch27/twrp_builder/actions/runs/41026784027) 成功，但实机仍卡 Logo。相隔60秒的两组标记均到达 `keystore2_wait enter`，未观察到 exit；ADB 可用，触控受阻未测。原厂 boot 回写后正常 Android 启动及桌面观察已确认，全部旧设备批准已消费。

旧采样中 keystore2、teei_daemon 和 Binder 管理进程存在，Keymaster 服务处于 stopped；两个 logcat 命令失败，且没有采到 logd 进程。以上不能证明 logd 二进制缺失、Keymaster 从未启动、TEE 故障或 userdata 损坏，也不能区分 keystore2 注册前的具体等待。

本轮先修补可观测性和 Native 交付流程，不宣称已修复 Logo 根因。新增镜像仍需完整 Android 编译和独立实机验收。

## 实现与边界

1. `recovery-required-modules.patch` 在原有日志条件中加入 `SELENE_STARTUP_DIAGNOSTICS=1` 分支，同时覆盖构建依赖和 ramdisk 文件列表：logd、libsysutils、libnl、`init.recovery.logd.rc`。保持现有 `TWRP_INCLUDE_LOGCAT` 外层条件。Native 固定启用诊断；未启用时继续遵循原有 `TARGET_USES_LOGD` 条件。沿用公开 Recovery 的 init 导入及 logd 服务定义，新镜像启动时该服务会按现有 rc 启动。
2. 新增 `keystore2-startup-diagnostics.patch`，只在既有调用前后插入固定日志语句，覆盖主服务创建/注册、TEE、可选 StrongBox、KeyMint 缓存锁、兼容服务、HIDL Keymaster 获取及硬件信息调用。不改等待 API、锁、返回分支、超时或重试，不增加线程和轮询。
3. 保留 Recovery/vold 第一轮阶段标记。六份补丁全部先完成 `git apply --check`，再开始应用；检查或应用失败保留真实失败，不继续编译或自动重试。
4. 按用户最新要求，Native 固定设置 `BUILDER_PLAINTEXT_ONLY=1`，跳过 CMS 封装，并移除 Native 的加密 Artifact 上传步骤。仅交付原有 `boot.img`、`static-validation.json`、`SHA256SUMS` 三文件明文 Artifact，保留三天，无需收件证书或私钥；`publish=false` 不创建 Release。旧 Artifact 不追溯删除，暂停的 Docker 默认交付分支保留。
5. 全部源码 revision、十项私有输入、四个归档覆盖及手机 FBE／数据解密功能保留；不复制私有原文、设备日志、标识、备份或凭据。本仓库没有新增设备操作入口。

## 日志判读

| 最后观察到的阶段 | 下一步定位范围 |
| --- | --- |
| `ks2_db_setup enter` | 参数路径与数据库初始化区间；不等于已经证明数据库损坏 |
| `ks2_tee_create enter`、`ks2_keymint_mutex enter` | 主服务注册前的 TEE 构造与 KeyMint 缓存锁 |
| `ks2_compat_register enter` 或 `ks2_compat_lookup enter` | 兼容服务注册或 Binder 获取 |
| `ks2_compat_lookup exit`、`ks2_keymint_resolve enter` 而无 resolve exit | 结合线程记录追查兼容 KeyMint RPC 或原生 KeyMint 获取分支 |
| `ks2_compat_mutex enter`、`ks2_keymasters_initialize enter` | 兼容层共享锁与底层枚举 |
| `ks2_hwservicemanager_get enter`、`ks2_manifest_list enter`、`ks2_hidl_keymaster_get enter` | HIDL 管理服务、manifest 枚举与具体 Keymaster 获取 |
| `ks2_hidl_hal_version enter` 或 `ks2_hardware_info enter` | HAL 版本或硬件信息 RPC |
| `ks2_service_register exit` | 主 keystore2 Binder 注册调用已经返回；仍需独立核对服务可用性及 Recovery 后续阶段 |

Rust 标记使用现有 `log::info!`，兼容层使用现有 `LOG(INFO)`；新增文本仅含固定阶段和 enter/exit。logcat 应保留 PID/TID，以区分共享秘密协商线程和主线程；不要把跨线程标记拼成单一顺序。exit 表示相应区间返回，不必然代表业务成功；`?`／panic 可以提前结束区间，因此缺少 exit 本身不能证明阻塞或死锁。需同时看错误、进程存活、Binder 注册状态及有时间间隔的线程采样。

原始 logcat、init、内核及线程记录只保存在实机主机；不得将它们放入公开仓库或 Actions 日志。采栈、发送信号、启动/停止服务、写分区、切槽或重启继续分别设 Gate。

## 已完成的本地验证

- 标准库174项：170通过、4项环境跳过（两个 `/proc` 命名空间限制、Go 缺失、aria2 缺失）。新增/更新用例覆盖六补丁先检查后应用、真实失败退出、Native 环境固定值、Native 不调用 CMS 及保留的 Docker 分支。
- 六份补丁在匹配公开源码上的全部预检查及组合应用通过，实际新增行空白检查通过。四个受改 security 文件删除新增固定日志行后与锁定原文逐字相同；这是语句保持验证，不是 Android 编译或运行证明。
- 实际补丁后的 GNU Make 代码通过36组组合，覆盖 Native 诊断值、旧日志开关以及 logcat 外层开关；核对依赖、init rc 名称、logd 和所需共享库的打包条件。
- 三份 YAML、36个内联 Shell 及全部独立 Shell 语法通过，工作流语义比较及差异检查通过。当前环境没有 rustc、actionlint 或 ShellCheck，未执行；尚未完成新的完整 Android 编译或实机测试。

## 本轮12文件清单与 Gate

```text
.github/workflows/twrp_native.yml
AGENTS.md
AUDIT.md
README.md
docs/SELENE_STARTUP_DIAGNOSTICS.md
patches/recovery-required-modules.patch
patches/keystore2-startup-diagnostics.patch
scripts/build.sh
scripts/run_native.py
tests/test_native.py
tests/test_recovery_required.py
tests/test_startup_diagnostics.py
```

建议提交：`[gpt-work] enable Native keystore diagnostics and plaintext delivery`。

2026-11-01用户明确要求“commit到main”，批准上述12文件提交 main，并由该次包含 Native 工作流的 push 自动启动一次 Native 构建，`publish=false`；不额外 dispatch 或自动重试。提交前已重新核对 main 仍为上述基线；使用该远端父提交及树提交最小变更，不推送本地合成审阅历史，不强推。真实构建结论以后续运行结果为准；此 Gate 不包含任何手机操作，后续设备干预继续分别批准。

## 匹配的公开源码

- [Recovery Android.mk](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/Android.mk) 与 [ramdisk 文件列表](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/prebuilt/Android.mk)。
- [keystore2 主入口](https://github.com/TeamWin/android_system_security/blob/14737db1429b8eebc15568bc748b2cd79ccad5c2/keystore2/src/keystore2_main.rs)、[主服务构造](https://github.com/TeamWin/android_system_security/blob/14737db1429b8eebc15568bc748b2cd79ccad5c2/keystore2/src/service.rs)、[KeyMint 连接](https://github.com/TeamWin/android_system_security/blob/14737db1429b8eebc15568bc748b2cd79ccad5c2/keystore2/src/globals.rs) 与 [兼容层](https://github.com/TeamWin/android_system_security/blob/14737db1429b8eebc15568bc748b2cd79ccad5c2/keystore2/src/km_compat/km_compat.cpp)。
- [锁定 Soong 的 Kati 调用](https://github.com/TeamWin/android_build_soong/blob/c6c059ab28c8c67921c0838a994bb70d53594aa7/ui/build/kati.go)：构建图阶段继承构建环境；独立 package 阶段另有限制。源码审阅支持 Native 诊断值传入 Make 的预期，真实构建结果仍待 CI。

---

## 2026-10-30 第一轮诊断提案（历史记录，旧批准已消费）

日期：2026-10-30（Asia/Shanghai）。基线：`main@102234a5a088d13dce9503a44db3c1179e5dfca8`。

### 目标与证据边界

针对 China MIUI `V14.0.4.0.TKUCNXM` 上已发生的 TWRP Logo 卡点，在保持现有加密、分区配置、内核及设备覆盖的条件下，区分具体阻塞阶段。本方案提供诊断，不宣称已经修复启动。

- Facts：已测试镜像来自 Native run `40620660730`；Recovery ADB 可用，但主菜单验收失败，触控受阻未测。同版本原厂 boot 回刷后，正常 Android 启动及桌面观察通过。
- Results：已分析两次旧日志及进程等待记录；日志相隔约129秒仍为8063字节且内容相同。单线程的自愿上下文切换增加258，非自愿切换未变；采样为带超时参数的私有 futex 等待。
- Assumptions：主界面加载前的元数据解密及 keystore2 服务等待是优先候选。上下文切换数量不能直接推算重试周期，futex 也不能单独证明死锁。
- Unknowns：没有该次运行的 logcat、服务状态、内存映射或用户态符号栈；不能确认 keystore2 实际状态或断言 TEE 失败。

原始实机日志、设备标识、执行记录和私有输入留在本地；不作为仓库文件、测试 fixture 或 Actions 附件。

### 已核对的现成项目

| 来源 | 锁定提交 | 对本轮的意义 |
| --- | --- | --- |
| [当前 Hasan 设备树](https://github.com/hasan6034/recovery_device_xiaomi_selene/tree/c77512445ab5be5908ddb3ca9c659e6b149c78de) | `c77512445ab5be5908ddb3ca9c659e6b149c78de` | 继续保留成功构建基线及四个受审覆盖 |
| [PBRP android-12.1-S](https://github.com/PitchBlackRecoveryProject/android_device_xiaomi_selene-pbrp/tree/f62d789cb6c11965bce397b81b9d13c36ca1e35b) | `f62d789cb6c11965bce397b81b9d13c36ca1e35b` | 对照 MIUI 13/14 配置；不是本机验收结果 |
| [Telegram a12-s](https://github.com/TelegramAt25/recovery_device_xiaomi_selene/tree/ab80ae4639f7186f48aeaa7333694449cba24a76) | `ab80ae4639f7186f48aeaa7333694449cba24a76` | 旧固件设备配置与服务启动方式参考 |
| [Telegram retakes](https://github.com/TelegramAt25/recovery_device_xiaomi_selene/tree/cd81ca4b346b6470b6d5ba16c4bb0b347300bbfb) | `cd81ca4b346b6470b6d5ba16c4bb0b347300bbfb` | 当前设备树的历史来源；不是新增同版本修复 |
| [Telegram retakes_nodecrypt](https://github.com/TelegramAt25/recovery_device_xiaomi_selene/tree/28e67c760b005ba30ea6dd58ed081979cd9ede1d) | `28e67c760b005ba30ea6dd58ed081979cd9ede1d` | 可研究基础功能路线，但改变功能范围，本轮不采用 |
| [OrangeFox TEE 记录](https://github.com/ngduyd/device_xiaomi_selene/commit/d87669e546b47fab068d55264f63eefc5be33427) | `d87669e546b47fab068d55264f63eefc5be33427` | 作者报告其设备的 TEE/Keymaster 失败；不能替代本机日志 |
| [OrangeFox 存储宏记录](https://github.com/ngduyd/device_xiaomi_selene/commit/740a1f894f1256beba05f8d6ce96ce2e2060dca5) | `740a1f894f1256beba05f8d6ce96ce2e2060dca5` | 非空 false 仍可能启用宏；已在本项目锁定核心中确认 |

已读取 PBRP、Telegram retakes、retakes_nodecrypt 和 a12-s 的 BoardConfig、fstab 及服务配置；同时只读核对当前受审覆盖，不复制私有原文。

| 具体差异 | 结论 |
| --- | --- |
| 当前覆盖使用原厂 `v2` 参数；PBRP-S 为 `v2+inlinecrypt_optimized`，Telegram retakes 为 `v2+emmc_optimized` | 固件配套不同，不作为可互换的修复项 |
| 当前覆盖与 retakes 的 metadata 源为 `md_udc`；PBRP-S 指向 `metadata` | 缺实机设备节点对应证据，不更改路径 |
| PBRP-S 和当前基线都含 Keymaster 4.1 及 listener 就绪触发 | 不能把已有功能重复当作待移植修复 |
| Telegram retakes 使用4.0服务，且有额外的 hwservicemanager 触发 | 不能盲目以旧服务或更早触发替换当前4.1链 |
| retakes_nodecrypt 删除加密开关，但仍定义 `RECOVERY_SDCARD_ON_DATA=true` | nodecrypt 名称不保证启动存储不依赖 /data |
| 当前 Recovery `Android.mk` 对 `RECOVERY_SDCARD_ON_DATA` 使用非空判断 | 赋值 false 仍定义该宏；若未来选择外部存储路线，应取消定义并另行完整审查 |
| a12-s 含缺依赖绕过和非真实安全补丁日期设置 | 不整体替换 builder 或复制其编译策略 |

### 匹配源码与候选调用链

- Recovery：[`TeamWin/android_bootable_recovery@5c3d206a5eeb3d446bcda8248a405a4b278bab5c`](https://github.com/TeamWin/android_bootable_recovery/tree/5c3d206a5eeb3d446bcda8248a405a4b278bab5c)。
- Vold：[`TeamWin/android_system_vold@a164ba05c5fef288059774a776b2e6e1119957cf`](https://github.com/TeamWin/android_system_vold/tree/a164ba05c5fef288059774a776b2e6e1119957cf)。
- Binder：[`frameworks/native@89c808424fbce9e40c0d4e0d1920b3c64a191b7f`](https://github.com/LineageOS/android_frameworks_native/blob/89c808424fbce9e40c0d4e0d1920b3c64a191b7f/libs/binder/IServiceManager.cpp)。

启动顺序是 `gui_init()` 显示 splash，再执行分区后处理，随后 `gui_loadResources()` 加载主界面。分区后处理在设置存储后调用 `Decrypt_Data()`；元数据密钥读取可进入 `Keymaster` 构造，其调用 `AServiceManager_waitForService()` 等待 keystore2。匹配 Binder 的服务等待使用条件变量定时重试。

当前核心已使用递归 DataManager 锁，且 GUI 未运行时变量通知直接返回。不能仅凭最后一条备份目录日志，就把等待归因为 DataManager 自锁。以上仍为候选链，不是实机栈。

### 提案实现

- `patches/recovery-startup-diagnostics.patch`：在存储变量更新、分区设置、加密状态、metadata 分区处理、元数据解密及主界面资源加载前后记录固定阶段。
- `patches/vold-keystore-diagnostics.patch`：直接向 stderr 记录元数据密钥读取、keystore2 获取及安全级别 RPC 前后标记，避免只依赖 logcat。
- 标记前缀固定为 `SELENE_STARTUP`；新增输出只有固定阶段、enter/exit 和布尔结果，不打印路径、设备标识、凭据、密钥或密钥内容。
- Native 启动器固定设置 `SELENE_STARTUP_DIAGNOSTICS=1`；共享构建脚本仅在该值为1时应用诊断补丁。Docker 启动方式没有新增该变量，原有补丁流程保持。
- 所有五份补丁先完成 `git apply --check`，才开始应用；检查失败立即退出，不继续编译。应用过程中失败同样保留真实失败；临时 checkout 不自动重试或回滚。
- 维持原有十项输入、全部源码 revision、四个设备覆盖、加密开关、等待 API、重试逻辑和镜像验收；没有新增服务启停、解密绕过、数据清除或设备命令。
- Native 工作流的 build Job 名称明确标记 startup diagnostics；自身路径触发规则保持。这次 YAML 变更获批推送到 main 后会自动完整构建，不额外 dispatch。

### 下一次实测应如何判读

| 最后阶段 | 优先检查 |
| --- | --- |
| `backup_variables enter` 无 exit | DataManager 变量更新及其下游调用 |
| `metadata_partition enter` 无 exit | metadata 分区状态及挂载路径；不执行清除 |
| `metadata_decrypt enter`，尚无 `metadata_key_read enter` | Fstab/加密选项解析、进入密钥读取前的调用 |
| `metadata_key_read enter`，尚无 `keystore2_wait enter` | 密钥文件读取或到达 Keymaster 构造前的操作 |
| `keystore2_wait enter` 无 exit | keystore2 服务注册、init 状态、服务崩溃、Binder/TEE 依赖及匹配用户态栈 |
| `keystore2_security_level enter` 无 exit | 已取得 keystore2 后的 TEE/KeyMint 处理 |
| 元数据解密 exit 且 result=0 | 失败返回，不等于死锁；结合其他记录分析 |
| `gui_resources enter` 无 exit | 主界面资源/主题加载；前段解密已越过 |
| 分区设置已退出但仍未进入可用主菜单 | 扩展到后续初始化；不能宣称所有图形或输入功能正常 |

阶段标记只能定位区间。下次测试还需限量采集 `logcat -b all -d`、指定服务的 `init.svc.*`、进程映射及可获得的用户态栈；原始记录只保存在实机主机。命令清单、规模和时间界限在实测方案中固定；调试器附加或信号采栈另设 Gate，不自动执行。

### 本次提案路径

允许提交范围仅为以下10个路径；提交前重新读取远端main，如已变化则重新评估差异与相关验证，不强推。

```text
.github/workflows/twrp_native.yml
scripts/build.sh
scripts/run_native.py
patches/recovery-startup-diagnostics.patch
patches/vold-keystore-diagnostics.patch
tests/test_native.py
tests/test_startup_diagnostics.py
README.md
AUDIT.md
docs/SELENE_STARTUP_DIAGNOSTICS.md
```

建议提交信息：`[gpt-work] add Native startup diagnostics for selene recovery`。

### 验证与批准边界

本地验证包括：五份补丁对匹配公开源码的应用检查、真实 Shell preflight 的禁用/检查失败/应用失败分支、Native 环境白名单、标准库测试、Shell/YAML 及差异检查。主机局部编译只能检查语法与测试替身行为，不能代替完整 Android 编译。

实际本地结果：170项标准库测试中166通过、4项环境跳过，新增5项全部通过；五份补丁组合应用通过；6种C++17替身行为通过；三份YAML、36个内联Shell及全部独立Shell语法、普通源码/文档差异检查及补丁实际新增C++行空白检查通过；unified-diff上下文前缀单独处理。actionlint未安装，未执行。

当前提案未完成真实诊断镜像构建或新实机验收；旧镜像卡 Logo 的事实保持。2026-10-30用户已明确批准上述10个文件提交main，并由该次push自动启动一次Native诊断构建，publish=false，沿用既有明文/CMS成品交付；不额外dispatch或自动重试。`publish=false` 关闭额外 Release，明文 Artifact 仍按既有规则公开可下载。

手机已恢复原厂启动；全部旧设备状态改变批准已经消费。未来每次进入 Bootloader、写入明确单槽、重试、切槽、重启或调试干预都使用独立人工 Gate。本仓库没有新增 ADB/Fastboot 执行入口。
