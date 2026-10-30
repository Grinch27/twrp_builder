# selene Logo 初始化等待：源码复用与诊断方案

日期：2026-10-30（Asia/Shanghai）。基线：`main@102234a5a088d13dce9503a44db3c1179e5dfca8`。

## 目标与证据边界

针对 China MIUI `V14.0.4.0.TKUCNXM` 上已发生的 TWRP Logo 卡点，在保持现有加密、分区配置、内核及设备覆盖的条件下，区分具体阻塞阶段。本方案提供诊断，不宣称已经修复启动。

- Facts：已测试镜像来自 Native run `40620660730`；Recovery ADB 可用，但主菜单验收失败，触控受阻未测。同版本原厂 boot 回刷后，正常 Android 启动及桌面观察通过。
- Results：已分析两次旧日志及进程等待记录；日志相隔约129秒仍为8063字节且内容相同。单线程的自愿上下文切换增加258，非自愿切换未变；采样为带超时参数的私有 futex 等待。
- Assumptions：主界面加载前的元数据解密及 keystore2 服务等待是优先候选。上下文切换数量不能直接推算重试周期，futex 也不能单独证明死锁。
- Unknowns：没有该次运行的 logcat、服务状态、内存映射或用户态符号栈；不能确认 keystore2 实际状态或断言 TEE 失败。

原始实机日志、设备标识、执行记录和私有输入留在本地；不作为仓库文件、测试 fixture 或 Actions 附件。

## 已核对的现成项目

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

## 匹配源码与候选调用链

- Recovery：[`TeamWin/android_bootable_recovery@5c3d206a5eeb3d446bcda8248a405a4b278bab5c`](https://github.com/TeamWin/android_bootable_recovery/tree/5c3d206a5eeb3d446bcda8248a405a4b278bab5c)。
- Vold：[`TeamWin/android_system_vold@a164ba05c5fef288059774a776b2e6e1119957cf`](https://github.com/TeamWin/android_system_vold/tree/a164ba05c5fef288059774a776b2e6e1119957cf)。
- Binder：[`frameworks/native@89c808424fbce9e40c0d4e0d1920b3c64a191b7f`](https://github.com/LineageOS/android_frameworks_native/blob/89c808424fbce9e40c0d4e0d1920b3c64a191b7f/libs/binder/IServiceManager.cpp)。

启动顺序是 `gui_init()` 显示 splash，再执行分区后处理，随后 `gui_loadResources()` 加载主界面。分区后处理在设置存储后调用 `Decrypt_Data()`；元数据密钥读取可进入 `Keymaster` 构造，其调用 `AServiceManager_waitForService()` 等待 keystore2。匹配 Binder 的服务等待使用条件变量定时重试。

当前核心已使用递归 DataManager 锁，且 GUI 未运行时变量通知直接返回。不能仅凭最后一条备份目录日志，就把等待归因为 DataManager 自锁。以上仍为候选链，不是实机栈。

## 提案实现

- `patches/recovery-startup-diagnostics.patch`：在存储变量更新、分区设置、加密状态、metadata 分区处理、元数据解密及主界面资源加载前后记录固定阶段。
- `patches/vold-keystore-diagnostics.patch`：直接向 stderr 记录元数据密钥读取、keystore2 获取及安全级别 RPC 前后标记，避免只依赖 logcat。
- 标记前缀固定为 `SELENE_STARTUP`；新增输出只有固定阶段、enter/exit 和布尔结果，不打印路径、设备标识、凭据、密钥或密钥内容。
- Native 启动器固定设置 `SELENE_STARTUP_DIAGNOSTICS=1`；共享构建脚本仅在该值为1时应用诊断补丁。Docker 启动方式没有新增该变量，原有补丁流程保持。
- 所有五份补丁先完成 `git apply --check`，才开始应用；检查失败立即退出，不继续编译。应用过程中失败同样保留真实失败；临时 checkout 不自动重试或回滚。
- 维持原有十项输入、全部源码 revision、四个设备覆盖、加密开关、等待 API、重试逻辑和镜像验收；没有新增服务启停、解密绕过、数据清除或设备命令。
- Native 工作流的 build Job 名称明确标记 startup diagnostics；自身路径触发规则保持。这次 YAML 变更获批推送到 main 后会自动完整构建，不额外 dispatch。

## 下一次实测应如何判读

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

## 本次提案路径

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

## 验证与批准边界

本地验证包括：五份补丁对匹配公开源码的应用检查、真实 Shell preflight 的禁用/检查失败/应用失败分支、Native 环境白名单、标准库测试、Shell/YAML 及差异检查。主机局部编译只能检查语法与测试替身行为，不能代替完整 Android 编译。

实际本地结果：170项标准库测试中166通过、4项环境跳过，新增5项全部通过；五份补丁组合应用通过；6种C++17替身行为通过；三份YAML、36个内联Shell及全部独立Shell语法、普通源码/文档差异检查及补丁实际新增C++行空白检查通过；unified-diff上下文前缀单独处理。actionlint未安装，未执行。

当前提案未完成真实诊断镜像构建或新实机验收；旧镜像卡 Logo 的事实保持。2026-10-30用户已明确批准上述10个文件提交main，并由该次push自动启动一次Native诊断构建，publish=false，沿用既有明文/CMS成品交付；不额外dispatch或自动重试。`publish=false` 关闭额外 Release，明文 Artifact 仍按既有规则公开可下载。

手机已恢复原厂启动；全部旧设备状态改变批准已经消费。未来每次进入 Bootloader、写入明确单槽、重试、切槽、重启或调试干预都使用独立人工 Gate。本仓库没有新增 ADB/Fastboot 执行入口。
