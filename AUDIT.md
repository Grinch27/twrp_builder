# selene TWRP 构建前审查

核验日期：2026-10-22，Asia/Shanghai。源仓库 `Grinch27/twrp_selene` 的基线为 `main@b0aef415d0a5eabf66663c8882d16e1e227381dd`。新构建仓库为 `Grinch27/twrp_builder`，检查开始时为空且公开；源仓库私有。

## 事实与范围

本次按根目录和子树递归读取 Git tree；对超限/截断响应继续下钻，最终无未完成子树。共枚举 **370,374 个 Git 文件/链接对象、3,925 个符号链接**，逻辑字节合计 26,246,399,889。该数字包括当前维护文件，与原归档仅统计原始文件的数字范围不同。未进行 370,374 个文件的逐行代码审查或全部二进制下载。

重点读取根 AGENTS/agents/readme、重建 manifest、删除前审计、Release 清单、设备配置、实际最后构建退出记录与日志、测试禁用清单、扫描排除记录、源码闭包报告、公开设备树和构建参考。未恢复旧工作区、未运行旧构建器、未连接手机。

| 领域 | 本次确认事实 | 影响 |
| --- | --- | --- |
| 最新归档构建 | 2026-10-06 最后退出码为 1，新运行目录没有 boot.img | 旧 artifacts 内的 boot.img 不能作为当前源码成功证据 |
| 最后失败 | Soong 图生成阶段缺少 Robolectric monitor 1.0.2-alpha1 AAR；当前 Git 清单中也没有该 AAR | 补齐一个文件不能推出全部闭包已完成 |
| Manifest | 282 个唯一项目，282 个 40 位 SHA，12 个 copy/link 指令 | 已完成干净完整同步与 HEAD/clean 校验；尚无编译成功证明 |
| 源码现场 | CTS 在归档中只有 7 个 Git 文件；prebuilts/tools、Gradle 使用过稀疏恢复 | 归档 checkout 不等同于上游完整源码 |
| 测试禁用 | 清单实际为 43 个 Android.bp、56 个模块 | 新构建不回放这些实验调整 |
| 缺依赖绕过 | 最后 runner 含 ALLOW_MISSING_DEPENDENCIES，依然失败 | 新构建不设置该变量 |
| 超限输入 | 18 个 Release 原件，包括 Linux JDK lib/modules | 直接 clone 归档缺输入；新路线改从锁定上游同步完整 prebuilt |
| 设备形态 | recovery-as-boot、A/B；产品 twrp_selene-eng，目标 bootimage，64 MiB boot | 不改成 recoveryimage 或 vendorbootimage |
| 原厂输入 | kernel、DTB、DTBO、fstab、SHA256SUMS 五个文件存在 | 只下载这些指定输入，不复制整套历史产物 |
| 公开上游差异 | 上游设备树 104 个文件；归档设备树 105 个文件；其中 101 个 blob 与上游相同 | 只需应用 3 个修改文件与 1 个新增文件 |

设备覆盖文件是 BoardConfig、first_stage_ramdisk fstab、recovery.fstab，以及新增 stock-v14 fstab。路径与 blob 身份固定在 `source.lock.json`；这些私有原文没有复制进 builder。

## 关键风险

| 等级 | 风险 | 当前处理与验证边界 |
| --- | --- | --- |
| HIGH | 282 项重建图仍可能缺少 Soong 全局依赖 | 完整 checkout 并核对 HEAD/clean；每轮真实失败后审查公开提供方、验证修复再重试，不禁用测试 |
| HIGH | 私有归档与公开 builder 的信息边界 | 仅通过用户配置的只读 secret 读取十个锁定输入；凭据不进入 Docker；源码与原始日志不上传 |
| HIGH | 公开 boot.img 会携带配置及固件 | publish 默认为 false；只有显式 true 且构建和静态检查成功才上传与预发布 |
| HIGH | 干净源码、Git 对象和编译输出可能超出标准 runner 容量 | 手动构建时只清理四个明确列出的临时 runner SDK 目录；50/18 GiB 双阶段检查，资源不足即停止 |
| MEDIUM | Ubuntu 最新系统可能不含旧 ncurses ABI | 编译容器固定 Ubuntu 22.04，安装 libncurses5；宿主 Runner 使用共享动态解析 |
| MEDIUM | 原设备树已有四个 BUILD_BROKEN 标志、2021-07 vendor patch、测试 AVB key | 原样披露，不新增绕过项；不是生产安全性证明 |
| HIGH | exact stock FBE、动态分区与 snapshot 能力未闭合 | 仅做构建与静态镜像检查，设备功能始终 NOT_TESTED |
| CRITICAL | 刷写、格式化、切槽或错误回退可能丢数据 | 没有设备操作入口；需另行确认当前设备、有效备份、动作与回退 |

当前环境没有 Docker，且可用磁盘约 30 GiB；不适合在这里执行完整 Android 源码同步/编译。未安装主机依赖、未申请付费资源。源仓库始终只读。

## 公开项目参考及证据等级

| 项目 | 已核对证据 | 可借鉴内容 / 限制 |
| --- | --- | --- |
| [momo54181/Action-TWRP-Builder](https://github.com/momo54181/Action-TWRP-Builder) | [运行 21091917719](https://github.com/momo54181/Action-TWRP-Builder/actions/runs/21091917719) conclusion=success；[对应 Release](https://github.com/momo54181/Action-TWRP-Builder/releases/tag/21091917719) recovery.img=17,432,576 bytes | 确实存在 Actions 成功和产物链；该次是 Legacy 工作流与 GIONEE_G1605A，不能证明 selene / TWRP 12.1 成功 |
| [mlm-games/TWRP_OFOX_PBRP_SHRP_Recovery_Builder](https://github.com/mlm-games/TWRP_OFOX_PBRP_SHRP_Recovery_Builder) | [Release 10844332416](https://github.com/mlm-games/TWRP_OFOX_PBRP_SHRP_Recovery_Builder/releases/tag/10844332416) 有 m02s recovery.img=38,031,360 bytes；另有 veux 的 boot.img | 可参考产物分层；对应旧构建 run 在本次可见成功列表中未保留，不能声称复核了它的完整日志 |
| [azwhikaru/Action-TWRP-Builder](https://github.com/azwhikaru/Action-TWRP-Builder) | 已读当前工作流；本次成功运行查询为 0 | 通用结构参考，不能把热度或模板说明当成功构建证明 |
| [hasan6034/recovery_device_xiaomi_selene](https://github.com/hasan6034/recovery_device_xiaomi_selene/tree/c77512445ab5be5908ddb3ca9c659e6b149c78de) | 与归档上游相同的实际设备 commit；上游文档指定 bootimage | 上游说明以 MIUI 12.5 为背景，不能替代 China V14 适配；本次未找到该仓库的成功 Actions 记录 |
| [minimal-manifest-twrp](https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp/tree/twrp-12.1) | 已读官方 minimal manifest、README | 按 recovery 所在分区选择目标；官方示例的缺依赖绕过与当前项目约束冲突，因此不照搬 |

参考实现内的全局 Python 替换、忽略依赖同步错误、ALLOW_MISSING_DEPENDENCIES、make clean、SSH/远程终端等没有带入新项目。用户附件 `uboot_allinone.yml` 提供共享 Runner、统一环境、Docker 编译和可选 Release 的结构；U-Boot 的 GCC 切换与特权宿主设备挂载不属于 Android 构建必要条件。

## 新构建器的实际验证状态

- 当前标准库边界测试：50 项通过，包含多组子案例；覆盖输入路径、覆盖拒绝、链接逃逸、下载身份、manifest 锁定及危险指令、公开补充项目的身份/路径/版本冲突与 checkout、boot/cpio/解压边界、错误 kernel/DTB/fstab、未验证状态保留、同步和编译安全摘要，以及加密交付认证、进度字段白名单、诊断再次校验和公开 Git blob 模块索引隔离。
- 新增 Python 可解析、全部 shell 通过 bash -n、工作流 YAML 可解析、手动触发与公开产物条件检查通过。
- 实际归档 manifest 经新校验器通过：282 个项目、40 位锁定 revision、受限下载来源与路径。
- GitHub Actions [运行 39693140718](https://github.com/Grinch27/twrp_builder/actions/runs/39693140718) 已成功：在代码提交 `dadd8c3dcfcc9e50d5d99e0c129b4cfcbacf47a6` 上，20 项测试、actionlint v1.7.7、官方下载校验及共享 Runner 解析均通过。完整编译 job 为 skipped，不能将这条绿色记录称作 TWRP 编译成功。
- 本轮连接不支持查询 Actions Secret 或发起 workflow_dispatch；已通过获授权的实际构建确认 `TWRP_SOURCE_TOKEN` 存在，十个输入全部下载并通过身份校验。没有读取或导出 Secret 值。
- Ubuntu 容器依赖安装、Repo 初始化和公开单项目同步已通过真实 runner 验证；282 项完整同步、mka bootimage 和真实 boot.img 静态验收的最新进度见下方继续执行记录。
- 新镜像启动、触摸、FBE、备份/恢复、动态分区/snapshot：**NOT_TESTED**。

## 后续顺序与停止点

2026-10-22 继续执行记录：用户确认已提供令牌权限并要求继续，已授权十个锁定输入在 GitHub runner 中处理。[首次完整运行 39694987634](https://github.com/Grinch27/twrp_builder/actions/runs/39694987634) 中，Secret 存在性、磁盘预检和全部输入下载/身份校验成功；清理后显示约 111 GiB 可用。容器依赖安装和 Repo launcher 下载校验已通过，随后在原先合并记录的 source_sync 阶段以 exit 1 停止，未进入编译，未发布产物。

本次 GitHub 连接仍无 workflow_dispatch 工具，因此使用只匹配一次提交标记的临时条件启动该已获授权的非发布任务；运行登记后立即恢复原触发条件。不是权限不足，也没有读取或导出 Secret 值。

[公开最小初始化测试 39695591966](https://github.com/Grinch27/twrp_builder/actions/runs/39695591966) 已成功，说明同一容器/Repo 版本能够完成非交互初始化。原失败原因尚未确定；现将 repo_initialization、repo_tool_verification、source_sync 分开记录，并增加不会回传原始日志的结构化摘要。新增四项摘要隐私边界测试，本地合计 24 项通过。完整原始日志没有上传，首次失败容器的日志不能从已结束的 runner 恢复。

后续诊断证据：[带细分诊断的运行 39696022513](https://github.com/Grinch27/twrp_builder/actions/runs/39696022513) 确认失败位于 repo sync。随后[公开单项目复现 39696416740](https://github.com/Grinch27/twrp_builder/actions/runs/39696416740) 给出明确错误 `fatal: ssh not installed`。初始容器使用 APT --no-install-recommends，依赖清单漏掉 openssh-client；已在正式容器和公开 smoke test 中补齐，并增加该错误类别的回归测试。无需扩大 Token 权限或配置 SSH 密钥。

修复提交 `f1b5fd7304cf8ac44f45e5db6b14db799f8893a5` 的 [CI 39696581000](https://github.com/Grinch27/twrp_builder/actions/runs/39696581000) 已通过 25 项单元测试、actionlint、公开 Repo 初始化与单项目实际同步；该次完整构建 job 为 skipped。之后才继续验证正式的 282 项源码路线。

[完整运行 39696743200](https://github.com/Grinch27/twrp_builder/actions/runs/39696743200) 使用 `cadbe391854ede5f0d1e406bb3ff1bdd3e302033`，验证 job 成功；十个私有输入校验、282 项完整同步、所有 checkout 的锁定 HEAD 和 clean 校验、设备覆盖、空间/JDK/原缺失 AAR 预检以及首次 lunch 均通过。容器于 08:01:04 进入 source_sync、08:18:52 进入 checkout_verification、08:19:37 进入 compile，08:21:07 以 exit 1 停止（Asia/Shanghai）。这只能证明编译阶段失败，不能推断具体 Soong/模块根因；该版本摘要尚未覆盖编译日志。Artifact 查询为空，发布步骤跳过，未进行镜像静态验收。

已补齐编译摘要的诊断缺口：完整日志仍在临时 runner；只输出固定类别、由锁定公开 Git blob 证实的文件位置与依赖字面量，明确排除私有覆盖文件。八项新增测试验证未知值、凭据、未跟踪路径、工作树私有修改和错误 revision 不会被回传。下一次仅验证这一诊断补丁，不改 manifest 或依赖图；取得第一个具体错误后停止。

[诊断运行 39699820379](https://github.com/Grinch27/twrp_builder/actions/runs/39699820379) 已结束：静态检查、公开同步测试、十个输入校验、282 项完整同步、checkout 和预检通过；08:38:40（Asia/Shanghai）在 compile 阶段以 exit 1 停止。受限摘要报告 `UNDEFINED_MODULE` 和 `SOONG_BOOTSTRAP_FAILURE`，公开位置为 `packages/modules/IPsec/tests/cts/Android.bp:19` 与 `packages/modules/StatsD/tests/apps/statsdapp/Android.bp:32`，缺失依赖为 `cts_defaults`。未上传 Artifact 或创建 Release。

2026-10-22 用户要求继续后，复核到原 manifest 没有 `platform/cts` 或 `platform/platform_testing`。同版 AOSP 标签 `android-12.1.0_r4` 的 [CTS 根 Android.bp](https://android.googlesource.com/platform/cts/+/5c5a1cac99f23a61564c60be33f9274ff7fcd5fa/Android.bp) 定义 `cts_defaults`，经 `cts_support_defaults` 引用 `cts_error_prone_rules_tests`，并直接依赖 `platform-test-annotations`；后者由同版 [platform_testing/libraries/annotations](https://android.googlesource.com/platform/platform_testing/+/af7eaff31e0aed03c06f6bade385397d792f4008/libraries/annotations/Android.bp) 提供。两个 tag 对应 SHA 均通过公开 Gitiles 元数据核对。CTS 完整 Git tree 已本地抓取：23,012 个文件，逻辑大小 2,032,706,654 bytes，含 1,561 个 Android.bp；不采用其他 Android 版本的 CTS 或自行编写空 defaults。

本次修复在 `source.lock.json.public_projects` 锁定这两个完整公开项目，由 `source_inputs.py compose` 验证原始 manifest 的 blob 身份后生成有效 manifest。原私有 manifest、十个下载输入、282 个原项目 SHA 及 12 条 copy/link 指令均保留；新增路径、项目名、remote 冲突或 Android tag 不匹配立即失败。完整 checkout 校验和受限诊断覆盖新增项目。40 项本地测试、Bash 语法、YAML/actionlint 和真实私有 manifest 组合检查已通过；284 项真实构建结果见下。本轮仅验证这一有明确来源的依赖补齐，不在失败后自动扩大图或禁用测试。

[完整运行 39728081394](https://github.com/Grinch27/twrp_builder/actions/runs/39728081394) 使用 `8ca01e413e2df619fc5bc2423692b420a6732bc7`。40 项测试、actionlint 和公开单项目同步均通过；完整 job 的输入下载/校验、284 项完整同步、锁定 HEAD/clean 校验、覆盖应用、空间/JDK/AAR 预检及 lunch 均通过。13:29:14 进入 source_sync，13:34:46 进入 checkout_verification，13:35:31 已进入 compile，13:37:46 在 Soong 以 exit 1 停止（2026-10-22，Asia/Shanghai）。新增完整 CTS 已提供原缺失的 defaults，但图尚未闭合；本轮受限摘要列出新的 `tradefed`、`compatibility-tradefed` 未定义错误，涉及 `cts/libs/install/Android.bp:174`、两个 VTS fastboot 测试、`platform_testing/libraries/audio-test-harness/tradefed/Android.bp:23` 和 `test/vts/tools/vts-core-tradefed/Android.bp:19`。摘要受固定数量和公开身份校验限制，不能作为全部错误清单。

该次运行 Artifact 列表为空；两个公开产物步骤均 skipped，未创建 Release，未进入静态镜像验收。一次性触发条件在登记后已恢复，当前完整构建仍只接受 main 的 workflow_dispatch。源码归档未修改，未新增缺依赖绕过或测试禁用；本轮在这一失败点停止，没有自动重跑。

后续依赖来源已完成只读核对：AOSP `platform/tools/tradefederation/prebuilts`，目标 checkout 路径 `tools/tradefederation/prebuilts`，`android-12.1.0_r4` 对应提交 `2a5fd21caf0d161ef6fc2efec1fadf2f31986039`。完整 Git tree 为 22 个文件、107,971,279 bytes；[test_harness/Android.bp](https://android.googlesource.com/platform/tools/tradefederation/prebuilts/+/2a5fd21caf0d161ef6fc2efec1fadf2f31986039/test_harness/Android.bp) 的第 25、58 行分别定义 `tradefed` 和 `compatibility-tradefed`，使用同版本官方预编译输入。该项目也存在于 TWRP 12.1 上游 default manifest，但不在当前归档 manifest。对现代 `platform/test/suite_harness` 和 Tradefed 源码仓库的相同 release tag 查询返回 404，因此不猜测跨版本分支作为替代。

下一入口：先审查这一项目的 JAR/filegroup 引用和现有图的重名情况，再决定是否将该 SHA 作为第三个公开补充项目（合计 285 项），随后单独验证。**它尚未写入 source.lock.json，也没有进行 285 项构建；不能保证只补它就能闭合全部依赖。**

2026-10-22 后续授权与实现：用户明确要求“继续：修正、构建。不断执行直至完全构建得到成品”，已覆盖旧的一轮失败停止策略；仍不允许隐瞒失败、缺依赖绕过、禁用测试、付费资源、公开明文产物或设备操作。已完成 Tradefed 同版本完整 tree 与 filegroups/JAR 非空检查，并将 `2a5fd21caf0d161ef6fc2efec1fadf2f31986039` 加入公开补充项目，合计 285 项；原 282 项、十个私有输入和 12 条 copy/link 不变。该图尚待真实编译验证。

为保留成功成品，新增标准 OpenSSL 3 CMS AES-256-GCM / RSA-OAEP 交付：只有通过既有镜像静态验收后，才加密打包 boot.img、static-validation.json、SHA256SUMS；工作流只自动上传 sealed-output.cms，七天留存。交付私钥留在本地工作区之外的私有临时目录，不进入 Git、Runner 或公开日志；仓库仅含收件公钥证书。本地已验证合成明文往返、内容严格限制及密文篡改认证失败。publish=false 继续禁止明文 Artifact 和 Release。

新增 build-progress 分支，仅镜像受限阶段/退出码以及经公开 Git blob 再次校验的诊断；不复制任意 JSON 字段或原始日志。宿主 GitHub token 不进入容器。编译摘要扩展至最多 64 个公开文件、128 个依赖，且可完整记录同一文件多条依赖错误。48 项测试、Bash、YAML/actionlint、真实 manifest 组合检查已通过。当前连接仍缺 workflow_dispatch 接口；本次持续修复仅以精确日期标记 `[selene-build-20261022] ` 的 main 提交触发，成功交付后恢复普通手动条件。

[285 项运行 39737597983](https://github.com/Grinch27/twrp_builder/actions/runs/39737597983) 使用 `0407905fb170ca3322690fc1f0380642b9dcabfa`。CI 的 48 项测试、actionlint 和公开同步通过；完整源码同步、checkout、预检通过，15:14:47 已进入 compile，15:16:21 因 Soong 未定义模块停止（Asia/Shanghai）。进度分支已实际回传受限阶段和再次核验的公开诊断，未公开原始日志。新缺项为 `CtsDeqpRunnerTests`、`py-parse_type`、`py-ply`、`vts_vndk_utils`，分别来自 CTS Tradefed 测试和 VTS kernel_proc_file_api_test 的公开 Android.bp。未取得可交付镜像，未上传明文或创建 Release。

下一组修复锁定同一 android-12.1.0_r4 的 `external/deqp`、`external/python/parse_type`、`external/ply`、`test/vts-testcase/vndk`，并按提供方实际 Android.bp 的直接引用补齐 `external/deqp-deps/{SPIRV-Headers,SPIRV-Tools,glslang,amber}`、DEQP Runner 测试的 EasyMock，以及 VNDK 测试的 ABI dump genrule 来源 `prebuilts/abi-dumps/vndk`。提交身份见 source.lock.json；四个直接模块的定义已在对应锁定公开树中核对，DEQP 和 VNDK 的新增依赖来自原始定义，未编写空模块、禁用测试或改用跨版本输入。当前合计 295 项，仍需真实构建检验。

[295 项运行 39740769101](https://github.com/Grinch27/twrp_builder/actions/runs/39740769101) 使用 `8de04c07ca5ec58800e76e743793ed30a7b210a7`，48 项测试与公开同步通过；15:32:10 进入同步，15:38:58 进入 checkout 校验，15:39:45 已进入 compile，15:42:04 因 Soong 未定义模块停止（Asia/Shanghai）。完整 checkout 和空间/输入预检通过，摘要这次列出的缺项为 `build/make/tools/signapk/Android.bp:23` 引用的 `apksig`。未进入镜像验收，没有明文或加密成品。

继续补齐同版 `platform/tools/apksig@c2b69bcc45dfac3a745e5f2fefcec42594dddb6c`，checkout 路径 `tools/apksig`。锁定公开 Android.bp 直接定义 `java_library_host` 模块 apksig，Java 1.8；其 apksigner 工具使用的 Conscrypt 已在原始 manifest 中。当前合计 296 项，等待真实构建验证；原始项目和私有输入未改动。

[296 项运行 39742649620](https://github.com/Grinch27/twrp_builder/actions/runs/39742649620) 使用 `fda36b1e1019352e0a04e4c9bd7af9eae8be80e6`，静态检查和公开同步通过；15:49:35 开始完整同步，15:57:08 进入 checkout 校验，15:57:55 进入 compile，15:59:58 以 exit 1 停止（Asia/Shanghai）。新的公开诊断是 `prebuilts/misc/common/robolectric/Android.bp:10` 缺少 `robolectric-host-android_all`。没有镜像成品。

下一次补齐同标签完整 `external/robolectric-shadows@fc6f4e51fa28f85090051012a491dd1ab0233eef`，其根 Android.bp 定义该实际框架聚合库，并引用 `android.car`。同标签完整 `packages/services/Car@af051f0a86d0ded75e4be48aa3387c68d569202b` 提供后者，两个完整公开 Git tree 与模块定义均已核对，合计 298 项。依赖闭包仍待实际 Soong 验证，不用占位模块替代框架库。为减少逐项猜测，进度分支新增来自锁定公开 Git blob 的模块名字面量索引；测试确认未跟踪文件、工作树私有改动及错误 HEAD 不会进入索引。该索引不证明生成模块或命名空间可见性。

[298 项运行 39747393426](https://github.com/Grinch27/twrp_builder/actions/runs/39747393426) 使用 `ae825a2c3575f634e24bebc0871cf9fdc3676c79`，50 项测试、actionlint 和公开同步通过；16:31:13 进入完整同步，16:38:01 进入 checkout 校验，16:38:48 进入 compile，16:41:16 因未定义模块 exit 1（Asia/Shanghai）。受限摘要确认缺少 `ConnectedAppsSDK_Annotations`、`dexlib2`、`dexlib2-no-guava-no-cli`、`google_java_format`、`mockito`、`mockito-host`、`modules-utils-build-testing`、`objenesis`、`objenesis-host`。未进入镜像静态验收，密文和明文产物步骤均跳过。

该次公开 Git blob 模块索引实际取得 16,064 个字面量名字。以实际错误为起点，并沿 Robolectric/Car 的公开 Android.bp 直接引用核对，新增同一 android-12.1.0_r4 的 28 个完整项目，合计 326 项。它们包括 Mockito/Objenesis、Connected Apps SDK、smali、Dagger/Google Java Format/Kotlin metadata、Dexmaker/dexter、libphonenumber、libprotobuf-mutator、okio、lottie/setupcompat/setupdesign、ZXing、modules-utils/proto_logging、Car 应用与公共库、Settings/ManagedProvisioning、Car 框架服务和 Setup Wizard，以及真正提供 glide-prebuilt 的官方 bumptech 预编译项目。外部 glide 源码未被当作 glide-prebuilt 替代，未加入清单。各标签 SHA、完整 Git tree、提供模块与传递引用已在公开锁定 Git 对象中检查；名字缺席不是缺依赖的充分证明，SDK/AIDL 自动生成名字仍由真实 Soong 检验。原 282 项身份、十个私有输入与 12 条 copy/link 不变。

Git Data ref 更新后的 `2d114b734e2111bbe6e2358ad85048ebd404145c` 未登记 Actions 运行；随后通过 Contents API 更新构建脚本需求注释，才产生上述 ae825a2 运行。本次后续提交将依赖锁定文件作为最后一次 Contents 更新，确保实际登记并验证任务。

[326 项运行 39750543645](https://github.com/Grinch27/twrp_builder/actions/runs/39750543645) 使用 `07eb95d4f5960939e1b5a84218b7a9bcbc53ddae`，50 项测试、actionlint 和公开同步通过；16:54:08 进入完整同步，17:00:12 进入 checkout 校验，17:00:59 进入 preflight，17:01:20 进入 compile，17:03:32 因 Soong 未定义模块 exit 1（Asia/Shanghai）。这次摘要列出 `system/bt/gd/rust/common/Android.bp:45`、`system/bt/gd/rust/gddi/Android.bp:10` 与 `external/rust/crates/anyhow/Android.bp:58`，缺少 `libcxx`、`libfutures`、`libgrpcio`、`libpaste`、`libtokio`。未生成可交付镜像，密文与公开产物步骤均跳过。

继续核对同标签完整 `external/rust/cxx` 和四个首层 crate，并沿实际 Blueprint 的 rustlibs、proc_macros、原生库和生成工具引用逐层查找提供方；37 个完整公开项目合计 6,559 个 Git 文件、47,341,749 bytes，所有标签 SHA、Git tree 和实际模块名已核对。结合 326 项公开模块索引，这批 Blueprint 的已识别引用均有字面量提供方；该静态结果不代替 Soong 的变体、命名空间或实际编译验证。已将 37 项锁定到 source.lock.json，当前总计 363 项。原始 282 项身份、十个私有输入、12 条 copy/link 均保留，没有新增缺依赖绕过或测试禁用。

[363 项运行 39762868028](https://github.com/Grinch27/twrp_builder/actions/runs/39762868028) 使用 `36dc8baa6daf49c71cec5dc543be959628ce1129`，完整同步、checkout 与预检后，Soong 因 `external/icu/icu4j/Android.bp:82` 引用的 `junit-params` 未定义而失败。下一次补齐同一 `android-12.1.0_r4` 的完整 `platform/external/junit-params@fa8720eb57ec6d8fe8fdfd7c74e581f094fd9219`；167 个 Git 文件、1,826,549 bytes，原始 Android.bp 定义真实 Java 库、兼容 host 库及其预编译测试依赖。仅引用原始完整项目，未加入测试禁用或占位模块。合计 364 项；原始 282 项、十个输入和 12 条 copy/link 均不变。

2026-10-22 用户明确授权根据新 AGENTS.md 补建非 container 单文件入口，并要求持续修正直至成品成功；此前仅制定规范的阶段已结束。新增 `.github/workflows/twrp_native.yml`，包含统一 `runner-image` 和直接运行的 build 两个 Job。原有 Docker 工作流保留。两者共享并发组；新的精确提交标记只触发原生完整构建。资源门槛、超时、来源锁定、静态验收、只读私有源和 publish=false 的 CMS 密文交付均沿用。

编写前已一次性核对 `actions/checkout`、`actions/upload-artifact` 的仓库、默认 main 分支、main/master 和实际 action.yml（均为 Node 24）；新入口采用 @main。共享仓库 `Grinch27/github-actions` 默认 main，master 不存在；实际读取 resolve-runner-image、run-sudo 和 env-toolchain 的 action.yml。采用前两者；env-toolchain 的清理/升级范围不符合本项目当前窄清理边界，未引入。参考上传的 OpenWrt 和 U-Boot YAML 的结构，未复制其容器权限、设备挂载、广泛清理或覆盖 Release 的行为。

按用户要求，主机 ncurses 不从源码构建。采用 Ubuntu 官方二进制归档 `https://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/`（工作流也支持官方 security.ubuntu.com 同路径），版本 `6.3-2ubuntu0.3`、amd64：libtinfo5 为 100,004 bytes，SHA-256 `4df4288404108f1a156d014e8764a064e977e34e6d44931ab60451694c03c90d`；libncurses5 为 106,866 bytes，SHA-256 `58da01991712c6856af0658dc5e9cb533c1a6854ab950055ade185e35bc9c276`。散列来自 packages.ubuntu.com 的 Jammy 下载元数据；本地实际下载、SHA-256 和 dpkg-deb 包名/版本/架构均已核对。二者分别依赖 libc6 >=2.33、>=2.34，libncurses5 另依赖相同版本 libtinfo5。它们提供真正 ABI 5，与当前 ABI 6 并存，不通过错误软链接伪装。只在一次性 Runner 安装，不改本地主机全局 Java/Python。

原生启动器将宿主进度上传与编译子进程分开：子进程环境白名单不含 CI token，HOME 保持原值；输出写入独占 0600 日志，仅输出固定阶段与退出码，SIGTERM/SIGINT 清理新建的构建进程组。54 项标准库测试（包括真实失败和取消子进程）、bash -n、两份 YAML 解析/内嵌 shell 检查、actionlint 1.7.7、实际归档 manifest 身份检查均通过。本地公开 repo smoke 在 GPG agent 启动时报错，未绕过签名验证，需以 GitHub runner 的原生公开 smoke 和完整构建结果继续验证。上述检查及官方包核对不构成原生完整构建成功的证据。

[首次原生 364 项运行 39789626001](https://github.com/Grinch27/twrp_builder/actions/runs/39789626001) 使用 `236d1ef2a950cbb0c70ec73406494610da09c1c2`。bootstrap 的 54 项测试、actionlint 和原生公开 repo 初始化/同步均成功；完整任务实际运行在动态解析的 Ubuntu 26.04，官方两个 ncurses 安装包于 13:49:44 UTC 通过 SHA-256，包身份和安装状态检查均通过。13:50:05 开始完整同步，13:58:07 进入 checkout 校验，13:58:39 进入 preflight，13:59:02 进入 compile，14:00:19 返回真实 exit 1。受限诊断列出 libdivsufsort、libdivsufsort64、libeigen、libflatbuffers-cpp、libgtest_isolated、libprotobuf-c-nano、libserde_json、libsonivoxwithoutjet；未生成成品，密文/明文产物和 Release 均跳过。此次证据解决了本地 GPG agent 因禁止创建套接字而无法执行公开 smoke 的环境限制，但不证明原生完整编译成功。

继续锁定同一 android-12.1.0_r4 的 11 个完整公开提供方：external/libdivsufsort、external/eigen、external/flatbuffers、system/testing/gtest_extras、external/nanopb-c、external/sonivox，以及 external/rust/crates 下的 serde_json、itoa、ryu、serde、serde_derive。合计 3,173 个 Git 文件、47,597,640 bytes；标签 SHA、完整 Git tree、实际模块定义和 Serde 的传递引用均已核对。结合本轮 16,521 个公开模块字面量索引，这 11 个项目的已识别 Blueprint 引用没有缺失字面量提供方；该结果仍不证明命名空间、生成模块、变体或真实构建闭包正确。当前 375 项，原始 282 项与私有输入/复制规则不变。

[原生 375 项运行 39793035672](https://github.com/Grinch27/twrp_builder/actions/runs/39793035672) 使用 `14a0f363a40c7182490eaf180eb5fcb0185eeaa0`，54 项测试、actionlint、公开 smoke、Ubuntu 26.04 官方主机包安装均通过。14:11:48 UTC 开始完整同步，14:19:21 进入 checkout 校验，14:20:08 进入 compile，14:21:38 返回 exit 1。受限摘要的新缺项为 libgoogle-benchmark、libusb、pybind11_headers，来自 libcore/NativeCode.bp、ADB tools、bionic benchmarks 和 Bluetooth gd 的公开定义。尚无镜像，产物与 Release 步骤均跳过。

下一次补齐同标签的 external/google-benchmark@770b190cd0052a180fe161abad59b4cbdfd99d46、external/libusb@b103c6be096fc0f1b0114188430e3ff5d39fdc35、external/python/pybind11@960c6f3b4ca0b7ac3d6178bd76cbcb7687ad5173。官方同标签 manifest 确认 Pybind11 的实际路径在 external/python 下；三个完整项目共 604 个 Git 文件、4,680,973 bytes，实际模块及其 Blueprint 引用已核对，当前合计 378 项。没有增加绕过标志或改动原始输入。

[原生 378 项运行 39795708159](https://github.com/Grinch27/twrp_builder/actions/runs/39795708159) 使用 `06f94090a2f11e51770b0d8d16b55c1a23e5a747`，Ubuntu 26.04 主机包安装、完整同步、checkout 和编译预检均通过。14:28:53 UTC 进入同步，14:41:41 进入 checkout，14:42:43 进入 compile，14:45:03 返回 exit 1；最新受限错误为 `cts/hostsidetests/atrace/Android.bp:19` 引用的 `trebuchet-core` 未定义。未生成可交付镜像。

下一次锁定 tools/trebuchet@cc86c36ffc7d164dc7f20373f072c821f36458c6。另对已报错的 14 份 Blueprint 做了公开来源预检：从实际锁定的 AOSP/TeamWin 提交读取文件，逐一核验 Git blob 身份；未使用私有覆盖层或日志内容。由 libcore/NativeCode.bp 的 static_libs 和 system/bt/gd/Android.bp 的 static_libs、rustlibs、proc_macros 直接引用，补齐同标签完整 external/fdlibm、external/google-breakpad、external/rust/crates/{num-derive,num-traits}。后四项是经原始公开定义确认的直接依赖，不是本轮编译摘要报告的额外错误。五个完整项目共 1,195 个 Git 文件、29,108,564 bytes，其已识别 Blueprint 引用均有字面量提供方。AIDL 生成名、Make 生成名及真正命名空间/变体的解析仍交由实际构建验证。合计 383 项；原始项目身份、私有输入和复制规则均不变。

本轮部分 GitHub 任务状态接口显示滞后，已通过带 no-cache 的 GitHub 公开 REST 读取和构建进度分支交叉核对，未据此更改并发取消策略或中断实际构建。383 项提交准备期间，本地执行环境断开；提交仅增加断开前已完成来源、完整 Git tree 与引用核对的公开项目，私有输入身份保持原值。本轮新提交的标准库测试、shell/actionlint 与公开 smoke 由 runner-image Job 执行，检查成功后才允许完整构建，不将尚未执行的本地检查记为通过。

[原生 383 项运行 39804153224](https://github.com/Grinch27/twrp_builder/actions/runs/39804153224) 使用 `89f9c912ed08d50bc44fa264cd7ec7cd6504ef75`。54 项测试、actionlint、公开 smoke、官方主机依赖安装、十个输入校验通过；15:25:38 UTC 进入同步，15:32:10 进入 checkout 校验，15:32:57 进入 preflight，15:33:19 进入 compile，15:35:21 返回 exit 1。受限诊断来自 frameworks/base 的 USB accessory 测试、frameworks/native 的 installd 和 ART disassembler，缺失 `libtinyalsa`、`libvixl`、`libvixld`、`server_configurable_flags`。没有进入镜像静态验收，成品步骤全部跳过。

下一次锁定同一 android-12.1.0_r4 的完整 `external/tinyalsa@5638a6e1d1a5775c9d064948e68ac40722814b31`、`external/vixl@eea8abec9ea365f30ac09461a6133077d34f5ca2` 和 `system/server_configurable_flags@cf0231f8f5c03f9c83a5a972cfbaa410782a63f4`。官方 manifest 确认 Flags 的 system 路径；三个完整 Git checkout 的 tag、commit、3,182 个文件和 422,766,297 bytes 已核对，原始 Blueprint 定义上述四个模块，已识别的直接 Blueprint 引用均在已核对的公开模块名字面量集中。该静态核对不证明变体、可见性或完整 Soong 图正确。合计 386 项，原 282 项身份、十个私有输入、12 条 copy/link、编译目标和镜像验收不变。

本轮接续已在本地找到原交付私钥；由 OpenSSL 导出公钥后与仓库收件证书逐字节比较一致。未更换收件证书，私钥未进入仓库、Runner 或公开日志。原生构建继续保持 publish=false。本地 54 项标准库测试、全部 shell 语法、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、实际锁定 manifest 的 386 项组合及 git diff --check 通过；完整构建结果待下一次运行验证。

[原生 386 项运行 39808641801](https://github.com/Grinch27/twrp_builder/actions/runs/39808641801) 使用 `5525774bf12db0368fc3e115a14436ff3346b840`。远端 54 项测试、actionlint、公开 smoke、主机依赖及十个输入校验通过，386 项完整同步、checkout 和编译预检均通过；compile 以 exit 1 停止。受限摘要这次仅列出 `bionic/libc/Android.bp:158` 引用的 `libjemalloc5`，仍未进入镜像静态验收，所有产物步骤跳过。主机软件包安装步骤曾耗时约 11 分钟，最终成功；公开日志没有提供明确安装失败信息，不据此改动依赖或系统配置。

继续补齐同一 android-12.1.0_r4 的完整 `external/jemalloc_new@6d4d27fd2651ed114386b89c2d251b816a849460`，326 个 Git 文件、2,874,669 bytes。官方 tag 与 checkout HEAD 已核对，原始 Blueprint 定义真实 `libjemalloc5` 及其辅助库，外部直接引用 `libc_headers`、`linux_bionic_supported` 均在现有公开字面量索引中。额外从原始锁定 Bionic commit `11fa611f2c52e17e23f679869724278e2becc862` 读取报错的 libc/Android.bp，已识别引用中只有 libjemalloc5 在该索引缺席；该核对仍不证明完整 Soong 图或实际编译正确。当前 387 项，原 282 项、十个私有输入、12 条 copy/link 和验收边界不变。 本地 54 项测试、Bash、YAML/内嵌 Shell、actionlint、真实 manifest 组合和输入契约比对全部通过，完整构建结果待验证。

[原生 387 项运行 39812919485](https://github.com/Grinch27/twrp_builder/actions/runs/39812919485) 使用 `6cd2d8f7f2313747f31e32a104097bef18abff95`。受限进度已确认同步、checkout、预检后在 compile 以 exit 1 停止，新缺项为 `frameworks/base/tools/fonts/Android.bp:50` 引用的 `fontTools`；尚无成功镜像。该次作业现已确认 conclusion=failure；核验期间状态接口曾延迟，实际编译结果由受限进度退出码和最终作业结论交叉确认。

继续锁定同一 android-12.1.0_r4 的完整 `external/fonttools@e76853bf40a5da5d1967ae174747408d080c17d6`，2,145 个 Git 文件、12,895,220 bytes；官方 tag/HEAD、实际 fontTools Python 模块及完整 Blueprint 引用已核对，没有发现项目外的直接 Blueprint 模块引用。当前共 388 项，原 282 项、十个输入、12 条 copy/link 和镜像验收均不变，实际闭包仍由下一轮构建验证。

2026-10-23 用户要求构建过程展示更多调试信息。本轮增强原生入口：获准的 Runner 清理逐项计时；APT 改用正常输出；新增受限数值遥测、约 60 秒心跳、实际阶段切换计时、Repo/Ninja 当前批次计数、磁盘/内存/Swap/负载和日志写入活跃度。原始日志只读取最多 256 KiB 尾部以提取计数，不回显日志文本或命令。`BUILD_DIAGNOSTICS` 直接向 Actions 输出再次核验的公开诊断，结束时将阶段耗时及诊断写入 Job Summary，并同步受限进度分支。未知字段、非法计数、非数值、布尔/NaN、未验证依赖和私有覆盖文本均不发布；报告故障保持真实子进程退出码。本地 66 项标准库测试、Bash/YAML/内嵌 Shell、actionlint、真实 388 项 manifest 和原始输入契约比对通过；新增测试包括 API 不可用时保留日志/摘要、真实子进程心跳及失败状态、字段和文本泄露边界。模块字面量索引仅在进入 compile 时生成一次，避免结束时重复扫描。新增行为仍需下一轮 Actions 实测，不能据本地合成测试认定远端已验证。

2026-10-24 接续核验：用户已明确只推进 `TWRP Selene (Native)`，暂缓 All in One Docker。Docker YAML/辅助代码保留，移除 push/PR 触发和提交标记条件，仅保留 workflow_dispatch 恢复入口；项目专属 AGENTS.md 和 README 记录该范围，Part I 不变。此前登记的 Docker 验证运行已结束，不发起新的 Docker 任务。

[388 项原生运行 39816458849](https://github.com/Grinch27/twrp_builder/actions/runs/39816458849) 已确认 failure。真实遥测和公开日志验证了心跳、Ninja 当前批次计数、实际阶段计时及再次核验的错误摘要输出；source_sync=481.733s、checkout=48.548s、preflight=3.909s、compile=82.815s，编译退出码 1，未进入镜像静态验收。结束采样可用磁盘 55,572 MiB、可用内存 14,797 MiB；Ninja 244/244 只描述当前批次，不代表镜像成功。新的 UNDEFINED_MODULE / SOONG_BOOTSTRAP_FAILURE 涉及七个公开 Blueprint 位置，但没有提取到缺失模块名字，下一步先核对公开源码的错误格式与诊断提取器，不据位置猜测依赖。

2026-10-24 诊断修正：七个报错位置的公开锁定源码均为使用 framework-module-defaults 的 java_sdk_library。锁定 Soong 的 android/module.go 确有未加引号、逗号分隔的 missing dependencies 错误格式；继承或生成依赖也可能不在报错的同一 Blueprint 内。新增该格式解析和最长 45 秒的跨项目公开 Git 字面量取证，最多 32 个证据文件；只接受从已核验公开错误位置提取的候选名，再次核验 pinned HEAD/blob 并排除私有覆盖。报告端也重新组合并比对锁定有效 manifest，避免替换清单授权诊断。没有将推测名字作为缺项，没有新增源码项目。74 项标准库测试、actionlint 和差异检查通过，包含继承/生成字面量、私有与未跟踪内容隔离、证据重验及替换 manifest 拒绝；真实 388 项图的下一轮结果仍待验证。

[388 项原生第 9 轮 40038843606](https://github.com/Grinch27/twrp_builder/actions/runs/40038843606) 使用 `92d4e33a638662070f1819dbfaf09ececdfefd60`，远端 74 项测试、actionlint 和公开 smoke 均通过。完整同步 607.524s、checkout 81.454s、预检 5.305s 后，compile 96.681s 返回 exit 1；作业已确认 failure。公开日志有 16 条 BUILD_METRICS 和最终再次核验的 BUILD_DIAGNOSTICS。摘要这次来自锁定 `external/skia/Android.bp:918` 和 `system/extras/simpleperf/Android.bp:71`，实际缺项为 libdng_sdk、libjpeg、libopencsd_decoder、libpiex、libsfntly、libwebp-decode、libwebp-encode。源码图没有改变而报错集合改变，不把此前七个 SDK 库视为已修复，也不将本次视为全部新增取证路径的真实覆盖。未进入镜像静态验收，产物步骤全部跳过。

下一轮锁定同一 android-12.1.0_r4 的九个完整公开项目：external/dng_sdk@9f8d75246e1989e4b325f3252a3912affcc1b22a、external/libjpeg-turbo@e78a6612493d491c4c24069db740022f2822f284、external/OpenCSD@bec745a24a3c9657ae5726e7b307760e69bdc288、external/piex@3778c33a5928ad2a1874ca4f9dc54c0467b689e6、external/sfntly@18570ec0301a59e3ddb0f3720db4cf00f833021c、external/webp@8c9c554a0dcb0f40f55ea7c440077bedd66194f1，提供上述七个实际缺项。另沿锁定 Skia 的直接定义补齐 external/harfbuzz_ng@29fd2884ecc5ffdb0b3ec56ebde8aeeaeea00de3；沿此前 SDK 库共用的 packages/modules/common/sdk/ModuleDefaults.bp:128 插件引用，补齐 tools/apifinder@eaf25fb9a7f47791310b8f3ba621311ec58c0d9b 及其直接引用 lint_api 的提供方 prebuilts/cmdline-tools@859a41090160f26e46438cd32f284ee1bab0d7ef。后三项来自公开直接引用预检，不是本轮摘要新增报告的实际缺项。九项共 3,759 个 Git 文件、172,756,426 bytes，tag/完整 Git tree、模块定义和已识别 Blueprint 引用均已核对；结合现有字面量索引未发现剩余名字缺席，仍不证明变体、命名空间或完整图正确。合计 397 项，原 282 项身份、十个私有输入、12 条 copy/link、只读归档和镜像验收不变。

397 项提交前，本地 74 项标准库测试、全部 Bash 语法、两份 YAML 及其内嵌 shell、actionlint 1.7.7、实际锁定归档 manifest 组合和差异检查全部通过；逐项比较确认先前所有 public pin 与其余输入/设备/验收契约均未改变。Docker 触发仍仅 workflow_dispatch。上述静态结果不能替代下一轮实际构建。

[397 项原生第 10 轮 40041039792](https://github.com/Grinch27/twrp_builder/actions/runs/40041039792) 使用 `15e4c1a1089df2c2a8f976c33c0a8ccbb48b6335`，远端标准库测试、actionlint 和公开 smoke 均通过。完整同步 379.790s、checkout 44.778s、预检 5.816s 后，compile 126.708s 返回 exit 1；作业已确认 failure。受限摘要本轮仅报告锁定 `frameworks/av/media/libstagefright/flac/dec/Android.bp:20` 的 libFLAC 未定义。未进入镜像静态验收，没有成品。

继续锁定同一 android-12.1.0_r4 的完整 external/flac@702c7e785c9b8b6f587eb5deb827571f5a188d6a，原始 Blueprint 定义 libFLAC。另从 frameworks/av 的原锁定提交 ae5c3b1fe0c949fde91c585e00876dac8e32edfd 获取完整公开 Git 对象，对 314 份 Blueprint 做了直接引用预检，再沿实际提供方的公开定义检查传递引用。本轮共增加 26 项：FLAC、JSMN、AAC、AOM、AVC、GAV1、GSM、HEVC、MPEG2、VPX、XAAC、YUV、Sonic、WebRTC、Ogg、dynamic_depth、image_io，WebRTC 直接引用的 libsrtp2/pffft/rnnoise/usrsctp，以及 RenderScript 所需的 rs、cblas、gemmlowp、compile/libbcc 和 compile/slang。完整路径与 SHA 逐项记录在 source.lock.json。除 libFLAC 外的 25 项来自公开直接/传递引用预检，不是本轮实际报错新增报告的模块。

26 项共 19,491 个 Git 文件、277,907,679 bytes；官方清单路径、同版本 tag/commit、FETCH_HEAD、完整 Git tree 和预期模块定义均已核对。image_io 的路径按官方清单确认；libwebm 实际由 AOM/VPX 提供，未加入不提供该目标模块的独立 external/libwebm 候选项目。其余已识别的普通 Blueprint 引用均能在现有字面量集合或本批提供方中找到；RenderScript 的 SDK 自动生成 stubs 和 native_bridge 条件引用仍需实际 Soong 解析，未通过占位库、删除引用、测试禁用或放宽缺项规则处理。合计 423 项，原 282 项身份、十个私有输入、12 条 copy/link 与镜像验收不变。

423 项提交前，本地 74 项标准库测试、Bash、两份 YAML 及内嵌 shell、actionlint 1.7.7、实际归档 manifest 的 423 项组合、原有 pin/输入契约比较和 git diff --check 均通过。Docker 仍只有手动入口；实际完整构建结果待第 11 轮验证。

[423 项原生第 11 轮 40043134500](https://github.com/Grinch27/twrp_builder/actions/runs/40043134500) 使用 `d7d631b531ab31219499b808075670b2492df0f5`，远端标准库测试、actionlint、公开 smoke 与完整源码校验通过。source_sync 605.645s、checkout 49.369s、preflight 6.169s 后，compile 129.710s 返回 exit 1；作业已确认 failure。受限摘要本轮报告 `external/webrtc/Android.bp:215` 引用的 libopus 未定义，未生成可交付镜像。该名字已存在于 423 项公开字面量索引，实际失败再次说明名字出现不证明可用命名空间、模块类型或变体，未据索引跳过真实构建错误。

按官方清单确认正确项目路径为 external/libopus，锁定同一 android-12.1.0_r4 的完整 `platform/external/libopus@e00ebcdb4328689e18676d25f4fcbccfd125747c`，430 个 Git 文件、4,270,318 bytes；官方 tag、FETCH_HEAD、完整 Git tree 和 libopus 的真实模块定义均已核对，其已识别 Blueprint 引用没有额外缺席的名字。另从原锁定 Eigen 的 blas/Android.bp 复核 libF77blas 和 libF77blasV8 的真实定义，未误加不存在的 blas 项目。当前共 424 项；原项目 SHA、十个私有输入、12 条 copy/link、构建目标和镜像验收均不变。

424 项提交前，本地 74 项标准库测试、Bash、YAML/内嵌 shell、actionlint 1.7.7、真实锁定 manifest 的 424 项组合及原有 pin/输入契约比较均通过，git diff --check 无错误。Docker 触发仍仅 workflow_dispatch；实际完整构建待第 12 轮验证。

[424 项原生第 12 轮 40056173806](https://github.com/Grinch27/twrp_builder/actions/runs/40056173806) 使用 `32f01bf3deef38216a1dcc0eecc318ed5addcbb3`，远端标准库测试、actionlint、公开 smoke 与完整源码校验通过。source_sync 426.749s、checkout 55.745s、preflight 6.059s 后，compile 130.685s 返回 exit 1；作业已确认 failure。摘要报告 `external/libbrillo/Android.bp:251` 引用的 libcurl 未定义，未进入镜像静态验收。该字面量也已存在于公开索引，仍以真实 Soong 解析结果为准。

补齐同一 android-12.1.0_r4 的完整 `external/curl@96813bdf12a382393ea0646d2beb82e813ad06cd`，3,238 个 Git 文件、19,557,364 bytes。官方路径、tag/commit、FETCH_HEAD、完整 Git tree 及 libcurl 实际定义均已核对；其已识别 Blueprint 引用没有新增缺席名字。另完整读取原锁定 libbrillo@c96dd99374b194a4ea3759b4447b16ed9fa1bc98 的公开 Git 对象，其 Blueprint 的普通引用在现有字面量集合或本批 Curl 中均可找到，仍不证明变体或命名空间正确。当前共 425 项，原有 pin、私有输入和验收契约不变。

为核对是否遗漏基础源码路径，读取官方 minimal-manifest-twrp/platform_manifest_twrp_aosp 的 twrp-12.1@6dc117d9cbd08430daa16db2013560e1c4017fa8。按 default.xml、twrp-default.xml 和 remove-minimal.xml 的 include/移除顺序计算后，有效清单为 249 个项目路径，当前图已覆盖全部这些路径；没有把原始 default.xml 的 1,061 项误作最小清单整体补入，也没有替换原锁定版本。其 README 使用缺依赖绕过的示例与本项目约束不符，继续不采用。

425 项提交前，本地 74 项标准库测试、Bash、YAML/内嵌 shell、actionlint 1.7.7、实际归档 manifest 组合及原有 pin/输入契约比较通过，git diff --check 无错误。Docker 仍仅手动入口；实际完整构建待第 13 轮验证。

针对 libopus/libcurl 两次出现“字面量已收录、实际仍未定义”的结果，补充公开索引的来源信息：同一次 pinned Git 扫描中记录 `prebuilts/` 项目与其他项目的名字集合，新增 public_prebuilts_project_only_names，排除同时在其他项目出现的名字；进入 compile 时另输出 BUILD_CATALOG 的两个数值计数。该分类不判断模块类型或可用性，也不推断本轮失败名字的具体出处。75 项本地标准库测试通过，新增场景同时验证来源交集、两个项目的私有工作树改动及未跟踪文件均不能进入输出；现有错误 HEAD、manifest 身份和隐私边界检查继续通过。此项尚待后续实际运行验证。

[425 项原生第 13 轮 40057518761](https://github.com/Grinch27/twrp_builder/actions/runs/40057518761) 使用 `4a56d01c3bad8df279cb29832520caba1fc972c0`，远端标准库测试、actionlint、公开 smoke 与完整源码校验通过。source_sync 442.582s、checkout 48.682s、preflight 5.819s 后，compile 126.513s 返回 exit 1；作业已确认 failure。受限摘要来自 `packages/modules/adb/Android.bp:260`，实际缺项为 libopenscreen-discovery 和 libopenscreen-platform-impl；尚无成品。

补齐同一 android-12.1.0_r4 的完整 `external/openscreen@264d76c60389dae367672f2ddb2a5987c0bf043a`，2,414 个 Git 文件、48,685,217 bytes。官方项目路径、tag/commit、FETCH_HEAD、完整 Git tree、两个实际 host static 模块及其内部 Abseil 提供方均已核对，已识别的项目外 Blueprint 模块引用没有额外缺席名字。另读取 ADB 原锁定 TeamWin commit c302c5023ba271cea0b6ece5785bd08e421d1dc1 的根 Blueprint；其 required 项 reboot.recovery 不是现有普通 BP 名字索引中的条目，继续由实际后续构建解析，未据此改名、添加占位模块或关闭该引用。合计 426 项，原有 pin、私有输入和验收契约均不变。

426 项提交前，本地 75 项标准库测试、Bash、YAML/内嵌 shell、actionlint 1.7.7、实际锁定 manifest 组合和原有 pin/输入契约比较通过；git diff --check 无错误。新增索引字段和 BUILD_CATALOG 计数待第 14 轮实测，不能据本地测试认定完整镜像构建成功。

[426 项原生第 14 轮 40059009918](https://github.com/Grinch27/twrp_builder/actions/runs/40059009918) 使用 `042f37b41b4dcf1723187f01877eeec36036f5e5`，远端 75 项测试、actionlint、公开 smoke 和完整源码校验通过。source_sync 578.372s、checkout 66.042s、preflight 5.963s 后，compile 100.796s 返回 exit 1；作业已确认 failure。摘要本轮报告 `external/conscrypt/Android.bp:606` 引用的 caliper-api-target 未定义，未进入镜像静态验收。新增来源分类已实际生成：17,129 个名字，979 个仅来自 prebuilts 项目；GitHub 日志的 BUILD_CATALOG 与分支数据一致。Tremolo/Libexif 的候选名字属于该集合，已添加源码的 libopus/libcurl 已不属于该集合；这仍不证明可用变体或命名空间。

为加快提供方研究，从同一官方 Android 清单的缺席顶层 external 项目中限时读取根 Blueprint；170 个候选中成功读取 142 份，共 835 个字面量名字。未读取的项目不作缺项判断，选中的提供方另取完整 Git 对象并逐一核对根 blob 与索引一致。该研究数据不是完整模块图，也不自动决定补入项目。

本轮增加同一 android-12.1.0_r4 的六个完整项目：external/caliper 提供实际缺项 caliper-api-target；其直接引用的 external/apache-commons-math 提供 apache-commons-math；沿原锁定 frameworks/av 的实际 Blueprint 引用补齐 external/tremolo（libvorbisidec）与 external/libexif（libexif）；沿原锁定 system/bt@9827945fd41eb3c7940b5ce983e21757fdbae5f6 的 95 份 Blueprint 中 main/Android.bp 的 required 引用，补齐 external/libldac 的两个 LDAC 模块；沿 system/media@612d1707ddd53b341512a8de9b3255c314e7c0b2 的 audio_utils/Android.bp 直接引用补齐 external/speex 的 libspeexresampler。只有 Caliper 是本轮实际错误报告项，其余五项来自直接/传递引用预检。

六项合计 1,207 个 Git 文件、19,957,529 bytes，官方路径、tag/commit、FETCH_HEAD、完整 Git tree、预期模块与根 blob 均已核对，SHA 逐项记录在 source.lock.json。已识别普通 Blueprint 引用在现有字面量集合或本批提供方中均可找到；蓝牙中的 AIDL 生成名字等仍由实际构建验证。未将只出现在预编译项目中的名字视为必然缺项，没有增加未找到当前引用依据的其他候选。当前共 432 项，原项目身份、十个私有输入、12 条 copy/link 和镜像验收均不变。

432 项提交前，本地 75 项标准库测试、Bash、YAML/内嵌 shell、actionlint 1.7.7、实际锁定 manifest 组合及原有 pin/输入契约比较通过，git diff --check 无错误。新增六项来源均为同版本官方公开项目，Docker 仍仅手动入口；实际结果待第 15 轮验证。


[467 项原生运行 40084243338](https://github.com/Grinch27/twrp_builder/actions/runs/40084243338) 使用 e8ae71f4f7dde52a6f5aabd5e1cfcf7befc33d25，runner-image 的标准库测试、actionlint 和公开 smoke 成功；原生 Job 已确认 failure。source_sync 493.650s、checkout 57.307s、preflight 4.760s 后，compile 98.476s 以 exit 1 结束。受限摘要来自 external/rust/crates/unicode-bidi/Android.bp:74 和 external/rust/crates/libm/Android.bp:66，实际缺项为 libserde_test、libno_panic；Ninja 244/244 仅是 bootstrap 批次完成，没有新 boot.img 或静态验收结果。

本轮以最新 e8ae71f 为基线，保留此前并发合入的 35 个公开项目及 AGENTS Part I 1.2.0，未重复覆盖原来的网络库修复。补齐同一 android-12.1.0_r4 的完整 external/rust/crates/no-panic@287890f55d0d225b176149c0ef2492e4f5fb886b（18 文件、35,293 bytes）与 external/rust/crates/serde_test@32fb05f66668b8efd0b6422b405294b6ec7f21e1（20 文件、120,663 bytes）。官方 tag、FETCH_HEAD、完整 Git tree 及实际 rust_proc_macro/libno_panic、rust_library/libserde_test 定义已核对；两者的普通 Blueprint 直接引用均在当前公开名字索引中，但仍不据此认定完整 Soong 图有效。共 469 项，其中原始 282 项、187 项公开补充；所有已有 pin、十个私有输入、12 条 copy/link、编译目标和静态验收不变。 提交前本地 75 项标准库测试、全部 Bash 语法、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、真实锁定 manifest 组合与 git diff --check 均通过，原交付私钥公钥与收件证书匹配；这些结果不代替下一轮完整构建。


[469 项原生运行 40099732022](https://github.com/Grinch27/twrp_builder/actions/runs/40099732022) 使用 412ae9faba20c5634badeb91f6afdcb8fe2fa7bd，远端 75 项标准库测试、actionlint、公开 smoke 和主机准备成功。source_sync 495.965s、checkout 46.889s、preflight 4.427s 后，compile 83.151s 以 exit 1 结束。最新受限摘要报告 frameworks/base/libs/WindowManager/Shell/Android.bp:114 与 frameworks/libs/net/common/testutils/Android.bp:19 引用的 iconloader_base、libnanohttpd 未定义；尚无镜像或静态验收结果。

等待该轮结果期间，按公开 source.lock.json 检查了 61 个 Rust 项目以及本地已有完整 Git 对象的公开提供方；这类普通引用检查不证明生成模块或命名空间有效。其中网络工具测试直接引用 libnanohttpd、当前公开索引缺席，该项随后也由实际构建确认。额外从私有原始 manifest 派生公开查询的本地研究被自动审批拒绝（元数据外传风险），已停止该研究；未把拒绝的检查记为通过，后续只使用公开锁定清单及经过验证的运行摘要开展提供方研究。

本轮补齐同一 android-12.1.0_r4 的完整 external/nanohttpd@66670dfc0fb50cb769a9a1ca62dbe8c6e7d5a84a 与 frameworks/libs/systemui@d68101a3e72cb65afc9b3f1279942cdc62d14b58。前者根 Blueprint 定义 libnanohttpd；后者 iconloaderlib/Android.bp 实际定义 iconloader_base。官方 tag、FETCH_HEAD、完整 Git tree、149 个文件及 743,000 bytes 已核对；全部已识别普通 Blueprint 引用均有现存字面量提供方，仍须实际构建验收。总计 471 项，原始 282 项与所有既有 pin、十个私有输入、12 条 copy/link 和镜像验收契约不变。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、仅在本地进行的实际 manifest 身份组合及 git diff --check 均通过。


[471 项原生运行 40100887810](https://github.com/Grinch27/twrp_builder/actions/runs/40100887810) 使用 b82be420aea6a27c45fcde51b848eb71e221fd77，远端 75 项测试、actionlint、公开 smoke、主机准备及完整源码校验通过。source_sync 365.066s、checkout 49.582s、preflight 5.844s 后，compile 126.587s 以 exit 1 结束，Job 已确认 failure。受限摘要报告 frameworks/base/packages/SettingsLib/Android.bp:10 与 frameworks/opt/telephony/Android.bp:81 的 WifiTrackerLib、ecc-protos-lite 未定义；没有生成通过静态验收的新镜像。

本轮增加同一 android-12.1.0_r4 的完整 frameworks/opt/net/wifi@f11dcd29a20a842da1ab09715ce2ebbc45c1baec（libs/WifiTrackerLib/Android.bp 定义 WifiTrackerLib）、packages/services/Telephony@ffe7afdfe3f17a4e1915bdd56da74678e4669ef6（ecc/conversion_toolset_v1/proto/Android.bp 定义 ecc-protos-lite），以及 Telephony 根 Blueprint 直接引用的 packages/apps/PhoneCommon@8cfe17c2aa6972af863e7a78de1b364c783a3a39（com.android.phone.common-lib）。只有前两个模块是本轮实际摘要报告项。官方 tag、完整 Git tree 与 FETCH_HEAD 均已核对，合计 1,654 文件、21,391,693 bytes；已识别的普通 Blueprint 引用无额外缺席名字，生成模块/命名空间仍交由实际构建验证。没有加入不提供 WifiTrackerLib 的 packages/modules/Wifi 候选项目。合计 474 项；原始 282 项、全部既有 pin、十个私有输入、12 条 copy/link 和镜像静态验收不变。 本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、仅本地的实际 manifest 身份组合及 git diff --check 均通过；完整结果待下一次实际运行。


[474 项原生运行 40101912369](https://github.com/Grinch27/twrp_builder/actions/runs/40101912369) 使用 11ae4644a2232bd18f8aca236f19385da4dc83d7，远端标准库测试、actionlint、公开 smoke 及主机准备成功。source_sync 506.126s、checkout 43.662s、preflight 4.164s 后，compile 78.481s 以 exit 1 结束。受限摘要来自 cts/tests/tests/media/libndkaudio/Android.bp:20、art/libartpalette/Android.bp:46、cts/apps/CtsVerifier/jni/megaaudio/Android.bp:21，实际缺项为 libOpenSLES、libartpalette-system、oboe；尚无镜像。

用户本轮将维护轮询节奏调整为：每次新运行启动后等待至少 12 分钟，随后每 60 秒查询一次工作流进展。已写入 AGENTS Part II 与 README（58148d5f6fef437898e39381833f3864a595c7a9）；不更改工作流自身的遥测心跳、并发策略或时限。

继续锁定同一 android-12.1.0_r4 的完整 frameworks/wilhelm@c62ed86e8a9a4b627f3df39c64604a7eedfc53cf、system/libartpalette@77055a71c70b08ba706c40733149fa5449da2a9b 与 external/oboe@79ec5d57a7aa727fb696996ef0f5531976ff6780。三者根 Blueprint 实际定义上述三个模块；官方 tag、FETCH_HEAD、完整 Git tree、1,530 文件及 20,894,236 bytes 已核对。普通 Blueprint 引用除 framework-permission-aidl-cpp 这个生成名字外均能找到已核对的字面量提供方；现有公开索引包含 framework-permission-aidl 生成器名字，但不据此证明 C++ 生成变体可用，继续由实际构建验证。合计 477 项，所有既有 pin、原始 282 项、十个私有输入、12 条 copy/link 与镜像验收均不变。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、严格本地的实际 manifest 身份组合及 git diff --check 通过。


[477 项原生运行 40103120938](https://github.com/Grinch27/twrp_builder/actions/runs/40103120938) 使用 45729bff04a8161433cd1d0e98169840f6718179，远端标准库测试、actionlint、公开 smoke、主机准备与源码身份校验通过。source_sync 502.724s、checkout 47.148s、preflight 4.432s 后，compile 87.748s 以 exit 1 结束。受限摘要报告 frameworks/base/packages/SystemUI/Android.bp:69 引用的 kotlinx_coroutines、kotlinx_coroutines_android 未定义，仍无可交付镜像。

补齐同一 android-12.1.0_r4 的完整 external/kotlinx.coroutines@78dd9159461464bde631bd1bc2289440949179c4（根 Blueprint 实际定义上述两个 java_library），以及它直接引用的 external/kotlinx.atomicfu@4b155e4f2fb7ca1d776171331553580978c16276（kotlinx_atomicfu）。AtomicFU 不是本轮摘要的额外报错，而是已核对的直接依赖。两个项目合计 1,286 文件、5,873,554 bytes，官方 tag、FETCH_HEAD、完整 Git tree、模块定义与普通 Blueprint 引用均已核对；与现有字面量集合合并后未发现其他普通引用名字缺席，这仍不证明整个 Soong 图或可用变体正确。当前共 479 项，全部既有 pin、282 项原始身份、十个私有输入、12 条 copy/link、编译目标和镜像静态验收不变；继续采用首查等待 12 分钟、此后每分钟一次的轮询节奏。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、严格本地的实际 manifest 身份组合及 git diff --check 通过。


[479 项原生运行 40104300303](https://github.com/Grinch27/twrp_builder/actions/runs/40104300303) 使用 e6190e59a708ad58e17499fe04212945c438f9a4，远端标准库测试、actionlint、公开 smoke、主机准备与源码身份校验通过；Job 已确认 failure。source_sync 363.177s、checkout 66.728s、preflight 5.917s 后，compile 127.097s 以 exit 1 结束。受限摘要来自 frameworks/base 的 RenderThreadTest、SimAppDialog、PackageInstaller、WAPPushManager、CameraExtensionsProxy 和 TransitionTests 的公开 Blueprint，实际缺项为 android-common、androidx.camera.extensions.impl、androidx.camera.extensions.stub、setup-wizard-lib、xz-java。未生成通过静态验收的镜像。

本轮利用首查等待期，仅从公开 source.lock.json 的 CTS/platform_testing pin 获取完整 Git 对象，逐项确认其 tag 与当前公开锁定 SHA 一致；没有从私有 manifest 派生外部查询。读取 CTS 的 1,561 份、platform_testing 的 155 份 Blueprint，共 1,716 份，对明确声明的直接引用及实际提供方的传递引用逐层核对。字面量索引缺席仅用于选取研究候选，选中的每个项目另核验完整 Git tree、FETCH_HEAD 和实际定义，未将生成模块名字简单当作普通缺项。

本轮增加同一 android-12.1.0_r4 的 15 个完整公开项目，路径及 SHA 逐项写入 source.lock.json。其中 frameworks/ex 提供实际报告的 android-common 与两个 Camera Extensions 模块；external/xz-java 提供实际报告的 xz-java；frameworks/opt/setupwizard@8a1063519e8cc0529e0b55fa3d2bdcc1a3530839 提供实际报告的 setup-wizard-lib。其余 12 项来自公开直接/传递引用预检，不是本轮摘要的额外实际错误：external/{androidplot,apache-commons-compress,glide,wycheproof,seccomp-tests,bcc}、system/bpf、packages/apps/Car/RotaryController、packages/apps/Launcher3，以及传递依赖 external/{giflib,volley} 与 system/bpfprogs。frameworks/ex 同时提供 CTS 引用的 android-ex-camera2；Commons Compress 直接引用 XZ Java；Glide 引用 Volley；BPF 所需 libbpf 由同版本 external/bcc 根 Blueprint 定义，未加入不适用的 external/libbpf 或 system/libbpf 路径。BPF 程序的两个 required 文件由完整 system/bpfprogs 提供。

15 项合计 4,410 个 Git 文件、61,327,754 bytes，官方清单路径、tag/commit、完整 Git tree 和预期定义均已核对，已识别普通 Blueprint 引用均有当前字面量提供方；余下 Android test SDK stubs、HIDL/AIDL 版本名均有当前公开索引中的生成器名字，但这不证明具体生成变体、命名空间或整个 Soong 图有效。当前共 494 项，原始 282 项身份、全部既有公开 pin、十个私有输入、12 条 copy/link、编译目标及镜像静态验收契约不变，继续按 12 分钟后每分钟一次检查。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、严格本地的实际 manifest 身份组合、15 项官方清单/commit 身份复核及 git diff --check 全部通过。


[494 项原生运行 40105439621](https://github.com/Grinch27/twrp_builder/actions/runs/40105439621) 使用 04fa77d326dee350e5aac1bfaa3e90d34aec3fcb，远端标准库测试、actionlint、公开 smoke、主机准备与源码身份校验通过。source_sync 580.467s、checkout 77.379s、preflight 6.388s 后，compile 102.079s 以 exit 1 结束。受限摘要仅报告 packages/modules/NeuralNetworks/common/random/Android.bp:33 引用的 tensorflow_headers 未定义；尚无镜像。

等待该轮首次查询期间，继续仅按公开 source.lock.json 获取、复核公开项目，完整检查了 209 个公开补充项目的 Git Blueprint/Make 定义与已识别直接引用，覆盖前述 CTS 预检批次。三个未取完整 Git 对象的补充项目是二进制预编译仓库；原有公开索引仍参与名字核对。所检查的普通 Blueprint 引用均能找到现有名字提供方；余下 SDK stubs、AIDL/HIDL 版本名与 RenderScript native_bridge 条件引用继续留给实际构建，未据字面量或生成器名字宣称整个图有效。该研究不覆盖全部原始 282 项，因此没有据此忽略 NeuralNetworks 的真实新错误，也没有新增缺项绕过或源版本替换。

本轮补齐同一 android-12.1.0_r4 的完整 external/tensorflow@2334215c2f3fb57dccd4cd1a950d7a0618ae522f，根 Blueprint 实际定义 tensorflow_headers。沿其 TensorFlow Lite 的直接引用，补入 external/ruy@1921442fc185b4d6ebcbf54b637d0ae3cd30b4aa、external/libtextclassifier@be51d516f665267a1bc1fd9fc6661e964e8b1a03；再沿 libtextclassifier 的实际引用补入 external/marisa-trie@627dea58d55e302266a5fb3399b46b7bf66a709f、external/libutf@39547c9d9307d4ce7b72b74e7443414bf1d2374d 与 external/tflite-support@3812149ba9f7e82aa37e6f0ba6b623afc7095500。只有 tensorflow_headers 是本轮实际错误，其余五项来自直接/传递引用预检。六项官方路径、tag/commit、FETCH_HEAD、完整 Git tree、27,165 文件与 347,222,417 bytes 已核对；实际模块定义及已识别普通引用在合并集合中均有提供方，仍不证明变体、命名空间或全图正确。

当前共 500 项（原始 282 项、218 项公开补充），所有既有 pin、十个私有输入、12 条 copy/link、构建目标和镜像静态验收不变。继续保持 Native、publish=false、同一收件证书和首查 12 分钟后每分钟一次的检查节奏。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、严格本地的实际 manifest 身份组合、六项官方清单/commit 身份复核及 git diff --check 全部通过。


[500 项原生运行 40107188457](https://github.com/Grinch27/twrp_builder/actions/runs/40107188457) 使用 b4a179f5083da1a09105558123d292223763510e，已确认整体 failure；远端标准库测试、actionlint、公开 smoke、主机准备及源码身份校验通过。source_sync 576.650s、checkout 137.848s、preflight 6.609s 后，compile 99.575s 以 exit 1 结束。受限摘要报告 packages/modules/Wifi/service/Android.bp:52 引用的 ksoap2 未定义；没有通过静态验收的镜像。

本轮补齐同一 android-12.1.0_r4 的完整 external/ksoap2@93a77e277f823796a75ad9e8915dd28349e39023，官方 tag 的 commit、完整 Git tree、48 文件及 352,644 bytes 已重新核对。根 Blueprint 实际定义 java_library/ksoap2，使用 system_current SDK、min SDK 30，未声明额外模块库引用；这不代替实际变体或完整 Soong 图验证。合计 501 项（原始 282 项、219 项公开补充），所有既有 pin、十个私有输入、12 条 copy/link 和镜像静态验收均不变。

本地工作区因自动维护清理丢失，包括旧交付私钥；已从公开 main 恢复 builder，并仅从已锁定的只读归档输入恢复 default.xml，用于严格本地身份验证。旧收件私钥没有归档副本，且此前没有成功成品；依照 AGENTS 交付约定，为后续构建生成新的本地 3072 位 RSA 私钥与对应收件证书，逐字节比对导出公钥一致。密钥强度与旧证书相同，私钥仍在仓库及 Runner 之外；本次只提交公共 delivery-recipient.pem，CMS AES-256-GCM/RSA-OAEP 和 publish=false 不变。原清理前的研究数据不作为本轮已经重新执行的本地检查证据。 本轮新环境中 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、经官方校验和验证的 actionlint 1.7.7、锁定 manifest 的本地 501 项组合、既有 pin/输入契约比较和 git diff --check 均通过；收件公钥与本地私钥再次匹配。


[501 项原生运行 40141921753](https://github.com/Grinch27/twrp_builder/actions/runs/40141921753) 使用 d2d11d6d81f489ff5ffa586190328cf9247b1e9f，远端 75 项标准库测试、actionlint、公开 smoke、主机准备与源码身份校验通过。source_sync 447.876s、checkout 53.819s、preflight 6.339s 后，compile 134.650s 以 exit 1 结束。受限摘要仅报告 packages/modules/NetworkStack/tests/unit/jni/Android.bp:21 引用的 libapf、libpcap 未定义；尚无可交付镜像。

补齐同一 android-12.1.0_r4 的完整 hardware/google/apf@ecccd0be025d8b6212ef5e5f3b8c1af1b2b0c34e 和 external/libpcap@b07fcc4515671dc3602fa433f4bbbfed29e4ea5a。前者根 Blueprint 定义实际 cc_library_static/libapf（SDK 24），其主机工具直接引用 libpcap；后者根 Blueprint 定义实际 cc_library/libpcap，支持 host、vendor 和 SDK 29 的 NetworkStack 测试。官方清单路径、tag/commit、FETCH_HEAD、完整 Git tree、368 文件与 4,100,108 bytes 已核对；已识别普通 Blueprint 引用在合并集合中没有额外缺席名字，仍须实际 Soong 变体和全图验证。共 503 项，原始 282 项、所有既有 pin、十个私有输入、12 条 copy/link、静态验收及当前配对收件证书不变。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、官方路径/commit 复核、严格本地的实际 manifest 503 项组合、既有 pin/输入契约比较及收件密钥配对验证均通过。


[503 项原生运行 40143163358](https://github.com/Grinch27/twrp_builder/actions/runs/40143163358) 使用 5be05c9faf6cb994bbdd99fab0446c993b4f24b8，已确认 Job failure；远端标准库测试、actionlint、公开 smoke、主机准备与源码身份校验通过。source_sync 404.584s、checkout 64.710s、preflight 6.078s 后，compile 126.664s 以 exit 1 结束。受限摘要仅报告 system/media/audio_route/Android.bp:36 引用的 libtinyalsav2 未定义；尚无成功镜像。

补齐同一 android-12.1.0_r4 的完整 external/tinyalsa_new@aa15f54e97e2a4cf1a4a72e344f4df546cb783c3，75 文件、459,819 bytes。官方清单同时列出 external/tinyalsa 与 external/tinyalsa_new；本轮保持既有 TinyALSA pin，新增完整后者。其根 Blueprint 实际定义 cc_library/libtinyalsav2，支持 host 与 vendor，工具模块名称以 2 结尾；声明的 system_shared_libs 为已有 libc、libdl，已识别普通 Blueprint 引用均有提供方。官方路径、tag/commit、FETCH_HEAD、完整 Git tree、实际定义已核对，仍须实际 Soong 变体及全图验证。共 504 项，原始 282 项、全部既有 pin、十个私有输入、12 条 copy/link、当前配对收件证书及镜像验收均不变。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、官方路径/commit 复核、严格本地的实际 manifest 504 项组合、既有 pin/输入契约及收件密钥配对检查全部通过。


[504 项原生运行 40144251033](https://github.com/Grinch27/twrp_builder/actions/runs/40144251033) 使用 ebda5ad8b2e0e680648048195811d4ea6e2c98bd，已确认 Job failure；远端标准库测试、actionlint、公开 smoke、主机准备及源码身份校验通过。source_sync 366.631s、checkout 56.948s、preflight 6.271s 后，compile 130.944s 以 exit 1 结束。受限摘要仅报告 hardware/interfaces/confirmationui/1.0/vts/functional/Android.bp:26 引用的 libcn-cbor 未定义；仍无可交付镜像。

补齐同一 android-12.1.0_r4 的完整 external/cn-cbor@b1412f245b5256c30e3757ac9e8cf245deaf5040，33 文件、109,514 bytes。公开官方根 Blueprint 索引提供定位线索后，再取得完整 Git 对象，核对官方路径、tag、FETCH_HEAD 与根 Blueprint blob 9ca75f9de224acc8cc017def67e1f5d71aa678fe 完全一致；实际 cc_library/libcn-cbor 支持 host、vendor、VNDK，未声明额外的项目外模块库依赖。已识别普通 Blueprint 引用均有现有提供方，仍须实际变体、命名空间及完整图验证。当前共 505 项，原始 282 项、全部既有 pin、十个私有输入、12 条 copy/link、当前收件证书及镜像验收均不变。 提交前本地 75 项标准库测试、Bash、两份 YAML/20 段内嵌 shell、actionlint 1.7.7、官方路径/commit/根 blob 身份复核、严格本地的实际 manifest 505 项组合、既有 pin/输入契约及收件密钥配对检查全部通过。


[505 项原生运行 40145320510](https://github.com/Grinch27/twrp_builder/actions/runs/40145320510) 使用 f4d2d0d24d34606a9b9c786076f1e41f9a5c8367，runner-image 检查成功，完整 Job failure。source_sync 381.887s、checkout 52.348s、preflight 6.308s 后，compile 128.193s 以 exit 1 结束。受限摘要仅报告 system/extras/profcollectd/libprofcollectd/Android.bp:37 引用的 libchrono、libmacaddr、libuuid、libzip 未定义；尚无成功镜像。

本轮补齐同一 android-12.1.0_r4 的完整 external/rust/crates/{chrono,macaddr,uuid,zip}，其根 Blueprint 均实际定义对应 rust_library，支持 host。沿 chrono 的 rustlibs 补入 num-integer；沿 zip 的 rustlibs 补入 byteorder、crc32fast、flate2。后四项是公开源码声明的直接/传递依赖，不是运行摘要额外报告的缺项。flate2 的 liblibz_sys、liblibc、libcfg_if 等名字已在既有公开索引中，未重复添加它们的项目；字面量存在不证明可用变体。

本地执行环境在研究期间断开。本轮通过 aosp-mirror-neo 和 Microsoft 的 msft-mirror-aosp 两份公开 AOSP 镜像，交叉核对八个 android-12.1.0_r4 annotated tag 对象 SHA 完全一致，读取其 peeled commit、未截断的完整递归 Git tree 清单及实际根 Android.bp blob；同标签公开 platform_manifest/default.xml 确认八个 path/name。没有声称本地取得完整 Git 对象或验证 tag 的 PGP 签名。八项共 287 个 Git 文件、1,883,409 bytes。构建仍从官方 AOSP remote 取得锁定 commit，并逐项验证实际 checkout HEAD/clean，镜像来源不替代 runner 的源码身份检查。

| 项目 | commit | tag object | Android.bp blob |
| --- | --- | --- | --- |
| external/rust/crates/chrono | 35633fa1226ef05eb47ad54429ebbab8d897b40a | 026ea552e9688dbd09e824a4e4ed4dbcf3e8d8cc | ecc8ca0ea6f8c81cc1952351876002936507ba26 |
| external/rust/crates/macaddr | efc9bb88df45a8bf5840874c828537d1d7a64f71 | cf6bb5fe0ee5b1a3f82d16b558fae092d87e7a65 | 7430a0f59829735ee8c58f82d6c93de5793573bb |
| external/rust/crates/uuid | 621eaf85d35127eb9ca35fc17f0b9597dbbccaa7 | ad39d1b4be953475b03f946d4d417c62efedc53a | aafe9e07918be8c703d0305d9da6cef297df229c |
| external/rust/crates/zip | 767cae43e318f7b3319c3350e3b359df99dded18 | a0bb8e9a6b959511d4eeefd63f6ac047e7f98d42 | e5b607d3f48dbd61395b1dc22e34563e47626e10 |
| external/rust/crates/num-integer | c72f03e26b6742eee471428005c81e1f98d89951 | 91db858a906cb27d2c5e9e07da0c6d9e1cca2d26 | b97f98c5cd16aef8e041ab5c7f206c7179c35cc2 |
| external/rust/crates/byteorder | 2a0cc4020d08e109081d8a561c94b339bc2f8749 | 8f76add7ee41d2889592877f1bdb6c54c501147d | 3efba93c39cf48b602eabb0e99c374a5605723c4 |
| external/rust/crates/crc32fast | b5ef892746e22c6a9bb17af18d9289c284fdea70 | 488c94f8c55f88a47178940600f9c8a529ca2e8e | 678f976cc45a9b2c8c55a472b8a007af6aea3d8e |
| external/rust/crates/flate2 | c4d185c8aacc1abfba4a8b49901b4acb30fbcd34 | d335c2d491302e05a47582efd644d19ba04c7670 | 649ce3bcfe17e994c5c8233aa52b054ae373b136 |

当前共 513 项（原始 282 项、231 项公开补充）。云端比较确认 source.lock.json 仅追加这八项，其余输入契约及既有 pin 完全相同；十个输入、12 条 copy/link、目标、CMS 收件证书、publish=false 与镜像静态验收不变。本轮未执行新的本地测试、实际私有 manifest 组合或收件密钥配对检查；同一持续交付期间，私钥在 505 项提交前已确认配对，本次环境断开只说明当前不能访问，不能据此认定它已丢失。标准库测试、Bash、actionlint 和公开 smoke 由现有 runner-image Job 执行，全部成功才允许完整 Job；实际 manifest 组合与 checkout 校验由完整 Job 执行。后续恢复本地环境时仍须确认收件私钥可用，取得密文不等同于完成解密交付。保持每轮首查等待 12 分钟、之后每分钟一次。


[513 项原生运行 40147542417](https://github.com/Grinch27/twrp_builder/actions/runs/40147542417) 使用 0d9ce7aefcc3ee8002e2e72c7de8651ec9afeef0，远端 75 项标准库测试、actionlint、公开初始化/同步 smoke、主机准备和十个输入校验均通过，完整 Job failure。source_sync 553.443s、checkout 146.612s、preflight 6.880s 后，compile 104.073s 以 exit 1 结束。受限摘要仅报告 system/core/trusty/confirmationui/Android.bp:82 引用的 libteeui_hal_support 未定义；没有通过静态验收的 boot.img。

本轮补齐同一 android-12.1.0_r4 的完整 system/teeui，其 libteeui/Android.bp 实际定义 cc_library/libteeui_hal_support，支持 host/vendor；完整项目的六份 Blueprint 均已读取，与既有名字集合比较后已识别普通引用没有额外缺席名字，HIDL 生成名仍由实际 Soong 验证。

首查等待期继续核对公开依赖，新增七项来自直接/传递源码引用，不是本轮运行摘要额外报告的实际错误。packages/modules/NeuralNetworks/driver/sample/Android.bp:92-93 的样例服务直接引用 libXNNPACK、libpthreadpool，对应完整 external/XNNPACK、external/pthreadpool；沿其静态库和头文件依赖补齐 external/{cpuinfo,FP16,FXdiv}。libclog 由同一 cpuinfo 的 deps/clog/Android.bp 实际提供，无需猜测另一个 external/clog 项目。frameworks/base/apct-tests/perftests/core/Android.bp:51 引用 :GoogleFontDancingScript，由完整 external/google-fonts/dancing-script 的 filegroup 提供；frameworks/base/mime/Android.bp:97 引用 :debian.mime.types.minimized，由完整 external/mime-support 的 java_genrule 提供。这三个公开调用方的同标签源码在断开前已通过严格本地比较，确认与 allowlist manifest 中锁定的 caller 身份相同；本轮只用固定公开 tag 读取相同引用，没有向外部服务发送私有 manifest 派生的 SHA。其 Git blob 分别为 9294b687ea041c70b640dcfbd54b1610c7fa57b0、2182f0bc2501d6706dddc472e2c3b408a880c870、a3ea65cb2efe4835feb7ac2013fb9cd74d9d81a2。

八项均按上一轮的两镜像同标签交叉核对方式，读取未截断的完整递归 Git tree 清单、所有 Blueprint 与实际定义，并由同版本公开 platform_manifest 确认 path/name。共 5103 个 Git 文件、78,942,010 bytes；没有声称本地完整 Git checkout 或 PGP 签名验证。

| 项目 | commit | tag object | 提供方 Blueprint blob |
| --- | --- | --- | --- |
| system/teeui | a0ec5efe611788e97f1c5d4673824750dbc19a5b | 0f31c3b38b8b8a26f5607bd441990d5cc33a234d | b349a1088a1aeef9ed0358a8c3ad1f081301ccbd |
| external/XNNPACK | 0cea1a1e068bd8e413cb7d86e7f5d7b5d8bb4146 | 97910015b3939fdf822b754b52167c5f67321257 | 16b757e16fcbbee85ec498bbba9ba84dbb38a1ba |
| external/pthreadpool | b505d1624df02b2abd496fb94abdfc7e1bda5877 | be6db6e21e913d97643c0b6469c47f3e47b70dab | a027498865d328a0bf5b83879dee662826e29969 |
| external/google-fonts/dancing-script | 82e7f54b5b544a62a0215b1e4254904c9489608f | 3dc566e0d085ca1dddb7d7e33e40347b4c0165b4 | a93470f811d9c09b7bd136672893acb1a23de35e |
| external/mime-support | 983cab4ee2f036103b6d3f365928d2ba836a68c5 | a2124be9b609299c453fc4f529c67882a0cf28f5 | 806821ef38a6e96ee4d237e2b6c03aede9ee3663 |
| external/cpuinfo | d55f522b37f0caba7509a808387733966d2fe26d | dae639d06a85e94e2d364097540b48b3dab40c3e | 79a901dfe72a313ba923ad7fedc648009fc085ab |
| external/FP16 | fa719c9ca65bafbec85348690fc03af69309b994 | 70fe58301398af664fc023a403c616a1b4dc2987 | 3aaa01b4ae094a33d7f6c79a5d06d351a0f7d94d |
| external/FXdiv | c8c0fad85b70aaedd1ce6e21bf3a4fc557dc5a53 | 4bf4213d93b33c316f5345be8154925a4ddaad2f | e4e0bc8c3cd9e487046584c20645f61ade341fd9 |

ARC 的 libarcbridge、libarcbridgeservice 确在 product_variables.arc 条件下，仅凭字面量缺席不能认定当前 selene 缺项，未加入；switcher4 的实际提供方仍未确认，已核对的 doclava 不定义它，未加入猜测项目。八项已识别普通 Blueprint 引用在合并名字集合中均有提供方；这不证明模块生成、命名空间或变体正确。

当前 521 项（282 原始、239 公开补充），云端逐字段比较确认既有 pin、输入/设备/镜像验收契约和收件证书不变。本轮执行环境仍未恢复，未声称新的本地测试、私有 manifest 组合或密钥配对通过；由现有 runner-image 的测试/Bash/actionlint/公开 smoke 门槛和完整 Job 的真实 manifest/checkout 校验继续验证。publish=false、只读十个输入、Native 和 12 分钟后每分钟一次检查均不变。


[521 项原生运行 40148911648](https://github.com/Grinch27/twrp_builder/actions/runs/40148911648) 使用 a995859fdd9bde44fda788162e503bf89bf21fd4，runner-image 检查成功，完整 Job failure。source_sync 623.378s、checkout 70.834s、preflight 6.608s 后，compile 104.211s 以 exit 1 结束。受限摘要仅输出 build/soong/Android.bp:49 和 UNDEFINED_MODULE / SOONG_BOOTSTRAP_FAILURE，public_dependencies 为空，未获得成功镜像。

同版本公开 AOSP Soong 和当前 TeamWin android-12.1 的根 Android.bp 均为 Git blob 8f7f3e2258687e04b11d1e59ed9bf1abaaded66b；第 49 行为 toolchain_library/libwinpthread，notice 属性采用 :mingw-libwinpthread-notice 标签。但这只是公开源码位置研究，不能据此把该名字宣称为本轮已提取的实际缺项，未添加猜测提供方。

已从代码确认诊断器缺口：依赖在错误中通常只有名字，而公开源中可能以精确带引号的 :name 标签出现；旧版 json.dumps(name) 的 literal 验证和跨项目 grep 会丢弃这种证据。新增共享的严格字面量匹配，仅接受完全相同的 quoted name 或 quoted :name；quoted/bare 错误中的一个前导冒号被规范化。摘要提取、限时 Git 证据搜索和 report_progress 的发布前二次核验均使用同一规则；NAME 语法、64 位置/32 证据/128 名字限额、锁定 HEAD/blob、排除覆盖/工作树及 45 秒搜索限制不变。不导出源码或任意日志，也不支持未知路径/命名空间标签。

新增四项合成 Git 测试，覆盖同文件 source label 的真实摘要与发布、继承文件 source label 的再次核验与排除、工作树/未跟踪注入和伪造摘要拒绝，以及部分名字/路径标签拒绝。本地环境仍不可用，测试尚未在本地执行；本轮交由现有 runner-image 的完整标准库测试、Bash、actionlint 和公开 smoke 验证，全部通过后才执行完整作业。此次仅改诊断，不修改 source.lock.json、521 项项目、十个输入、12 条 copy/link、收件证书或任何构建/镜像验收条件。switcher4 已进一步定位到同版本 tools/doc_generation 的实际 python_binary_host，标签/commit/tree/根 blob 已交叉核对，但仍只作为后续候选，未写入本轮源码锁。继续 Native、publish=false 和 12 分钟后每分钟一次检查。


[521 项诊断修正运行 40150195255](https://github.com/Grinch27/twrp_builder/actions/runs/40150195255) 使用 4c669326109ce4dc74bbdc0172a1da4a0f250d20，远端 79 项标准库测试、actionlint、公开初始化/同步 smoke、主机准备及源码身份校验通过，完整 Job failure。source_sync 430.058s、checkout 61.448s、preflight 6.237s 后，compile 133.018s 以 exit 1 结束。新的受限摘要在同一 build/soong/Android.bp:49 实际提取并再次核验出 mingw-libwinpthread-notice；这验证了 :module 标签诊断路径，不构成编译成功。

实际缺项由同一 android-12.1.0_r4 的完整 prebuilts/gcc/linux-x86/host/x86_64-w64-mingw32-4.8 提供：根 Android.bp 定义 filegroup/mingw-libwinpthread-notice，引用的 licenses/mingw-w64-svn-r5861/mingw-w64-libraries/winpthreads/COPYING 在该完整 Git tree 中确实存在。同步完整上游项目，不拷贝单个 notice 或使用跨版本工具链，不修改 Windows 模块/测试启用状态，也不改变实际 bootimage 的原工具链选择。

同时纳入公开引用预检已经确认的完整 tools/doc_generation；frameworks/base/ApiDocs.bp:404 明确声明 tools: [switcher4, ...]，其同版本提供方根 Blueprint 定义 python_binary_host/switcher4，保持官方 py2/py3 设置，未修改全局 Python。switcher4 是预检依赖，不是这次运行摘要报告的实际缺项。两个项目的同标签 annotated tag 在 aosp-mirror-neo 与 msft-mirror-aosp 中完全一致；公开同版本 platform_manifest path/name、peeled commit、完整未截断递归 tree 清单和全部 Blueprint 已核对，共 4,005 个 Git 文件、356,879,558 bytes。本地执行环境仍不可用，没有声称本地完整 Git checkout 或 PGP 签名验证；完整构建仍只从官方 AOSP remote 同步锁定 commit，并校验实际 HEAD/clean。

| 项目 | commit | tag object | Android.bp blob |
| --- | --- | --- | --- |
| prebuilts/gcc/linux-x86/host/x86_64-w64-mingw32-4.8 | b1f41225c9b400670ea28bf387cd85849a8c93b4 | de00b7ca1f9e2f8ac883f53250847d5e6e6345f5 | ae93b9feaef045a36ee4e0d24aea4acb4cb69ea3 |
| tools/doc_generation | ae81e21a4c6de7562f7718d063e1fde1a89f7919 | 8ad38f6d0ed6efb73ef4bbd1bc06b7c2f16c2167 | 4f473a082974042a7055d8880172c452575b7efe |

当前共 523 项（282 原始、241 公开补充）；云端逐字段检查确认 source.lock.json 只追加这两项，既有 pin、十个私有输入、12 条 copy/link、收件证书和镜像验收全部不变。诊断修正的 79 项测试已有上述实际 runner 通过证据；本轮新增 pin 的检查继续由现有 runner-image 门槛与完整 Job 的实际 manifest/checkout 校验执行，不把先前通过结果记为本轮已经执行。本地环境和收件密钥可访问性尚待恢复，私钥不进入 Runner 或公开仓库。Native、publish=false、每轮 12 分钟首查和此后每分钟一次均不变。


[523 项原生运行 40151162025](https://github.com/Grinch27/twrp_builder/actions/runs/40151162025) 使用 9f6cf9af9ce1dad567c4fc7ab34d0960c25107e4，远端 79 项标准库测试、actionlint、公开初始化/同步 smoke、主机准备及完整源码身份校验通过，完整 Job failure。source_sync 457.299s、checkout 65.418s、preflight 6.222s 后，compile 134.715s 以 exit 1 结束。受限摘要仅报告 frameworks/base/wifi/java/Android.bp:35 引用的 libwificond_ipc_aidl 未定义；尚无通过静态验收的 boot.img。

补齐同一 android-12.1.0_r4 的完整 system/connectivity/wificond@dfd60f8706b928b3d7d014fc9e06926ab6c45abd，115 个 Git 文件、846,607 bytes。根 Android.bp 的 filegroup/libwificond_ipc_aidl 实际包含十份 nl80211 AIDL，libwificond_ipc 也使用相同 :libwificond_ipc_aidl 引用。公开同标签 platform_manifest path/name、两镜像 annotated tag 0bb8eacdfeb7a9e7178fcd6601e8cd514391f36f、peeled commit、未截断的完整递归 tree 清单和根 Blueprint blob e417aaf403cedc0d034a6d499db17304c6dd6e52 均已核对。全部 Blueprint 已识别普通引用在既有名字集合与本项目定义中都有提供方；android.security.legacykeystore-ndk_platform 是已有 android.security.legacykeystore AIDL interface 的生成引用，同版本公开 system/security/keystore2/aidl/Android.bp 明确启用 NDK backend，但仍不据生成器名字或另一个公开 tag 的配置保证当前生成变体可用，交由真实 Soong 验证，未重复添加 system/security。

当前 524 项（282 原始、242 公开补充），source.lock.json 只追加这一项，所有既有 pin、十个私有输入、12 条 copy/link、收件证书和镜像验收保持原值。本地环境仍不可用，未声称本轮本地完整 Git checkout、单元测试、私有 manifest 组合或收件密钥复核；由现有 runner-image 检查门槛和完整 Job 的真实 manifest/checkout 校验执行。继续 Native、publish=false 和每轮首查等待 12 分钟、此后每分钟一次。


[524 项原生运行 40152231653](https://github.com/Grinch27/twrp_builder/actions/runs/40152231653) 使用 34fff53d2ec0756619488d1af04c4284eeb9abac，远端 79 项标准库测试、actionlint、公开初始化/同步 smoke、主机准备及源码身份校验通过，完整 Job failure。source_sync 407.394s、checkout 56.947s、preflight 6.263s 后，compile 130.039s 以 exit 1 结束。受限摘要仅报告 frameworks/base/startop/iorap/Android.bp:31 引用的 iorap-aidl 未定义；尚无成功 boot.img。

补齐同一 android-12.1.0_r4 的完整 system/iorap；根 Blueprint 实际定义 filegroup/iorap-aidl，包含 IIorap.aidl 与 ITaskListener.aidl，并设置 path 为 binder。沿其实际 shared_libs/header_libs，补入完整 external/google-fruit（cc_library/libfruit）和 external/Reactive-Extensions/RxCpp（cc_library_headers/librxcpp）；再沿 RxCpp 测试的 whole_static_libs 补入完整 external/catch2，提供 libcatch2 与 libcatch2-upstream。这三项是已读取的直接/传递引用，不是该次受限运行摘要额外报告的缺项，没有禁用测试或编写空 defaults。

四项的公开同标签 platform_manifest path/name、两份独立 AOSP 镜像 annotated tag、peeled commit、完整未截断递归 tree 清单及所有 Blueprint/Make 文件均已核对，共 1,215 个 Git 文件、8,590,246 bytes。依赖预检使用保留字符串的注释处理，避免把 src/**/*.cc 中的斜线星号误当成块注释；合并实际定义与既有名字集合后，已识别普通模块引用没有额外缺席名字，但仍不证明生成模块、可用变体或命名空间解析。

| 项目 | commit | tag object | Android.bp blob |
| --- | --- | --- | --- |
| system/iorap | e2fff5521c256e529e0c06832d97ba4c4904241d | 430013bb8f8b2aa209c7077cb7326d950181a125 | 736bc401de381d31637a1243fd30aa36f326da8b |
| external/google-fruit | 163edb54c696ce93dd90072d69ae45e2392f340c | ae5b4c70973450474726cad561df0fdef8d6e86f | 444c19ca7b5a532dcab3aa441259778bed7fc0ca |
| external/Reactive-Extensions/RxCpp | ac5bf92f435fd44bd418de92917454ef02b867b7 | bfb6c77a1ba188e45c75c1007b103cfc1ba9eafd | 1ba32cae50c8934e4f1beb86219fc426854718dd |
| external/catch2 | a19571a8d820d3851a44dbfc75272360584a5f50 | 95582facd1e63d3f5ce7d09b2b08c74a7489a3e5 | 99a231e5bae67b15004715d2de903c2b698729f3 |

当前 528 项（282 原始、246 公开补充），云端逐字段比较确认 source.lock.json 只追加以上四项；既有 pin、十个私有输入、12 条 copy/link、收件证书、编译目标和镜像静态验收不变。本地执行环境仍不可用，未声称本轮本地完整 Git checkout、标准库测试、实际私有 manifest 组合或收件密钥配对通过；新提交仍由现有 runner-image 检查门槛及完整 Job 的实际身份校验验证。保持 Native、publish=false，首查等待 12 分钟后每分钟一次。

[528 项原生运行 40153189218](https://github.com/Grinch27/twrp_builder/actions/runs/40153189218) 使用 790e2c7cc35ef50ca2ca7e28a3fb9692ad33b034，远端检查、主机准备和源码身份校验通过，完整 Job failure。source_sync 573.720s、checkout 74.248s、preflight 5.389s 后，compile 104.210s 以 exit 1 结束。受限摘要明确报告 bootable/recovery/tests/Android.bp:124 引用的 res-testdata 未定义；没有成功镜像。

公开研究分支的 [40153512614](https://github.com/Grinch27/twrp_builder/actions/runs/40153512614) 已成功，83 项合成测试、actionlint 和公开 smoke 通过，完整 Native Job skipped。固定公开 Frameworks Base tag 的 721 份 Blueprint/Make 已扫描，报告 180 个字面量候选，主要为 AIDL/HIDL/SDK 生成模块、Make 目标和 ARC 条件引用；未将这些名字直接当成真实缺项。研究工具保留在独立分支，没有并入主线或修改本轮输入。

res-testdata 是源码资源缺失：同版本 AOSP 根 Blueprint blob 52de77038ca87af8b923a7ec4fff8e7a62ad0ac3 定义该 filegroup，srcs 为 res-*/images/*_text.png；公开 TWRP android-12.1 分支缺少定义和这些图片。本轮保留全部 528 项原锁定项目和十个私有输入，在 source.lock.json 新增独立 public_test_resources，固定 platform/bootable/recovery@e8aadb8b03fca3c1e0fd938e8f8486de4bafd965 的 25 张 PNG 与原 NOTICE，共 26 个公开资源文件、4,504,715 bytes。只下载测试实际引用的数据，不替换 Recovery 项目或其源码。新的 bootable/recovery/builder-testdata 目录保存原密度/图片相对路径，并提供与 AOSP 一致的非空 filegroup；独立声明原许可种类并保留 NOTICE。原测试仍启用，没有空模块或测试绕过。

新增 restore_public_testdata.py 按既有 Git 输入身份函数读取这份公开资源锁，四个有界读取器从固定官方 AOSP commit 下载，只接受预期图片路径和 NOTICE，在全部下载有效后才写入新目录和模块定义；已存在的目标目录、符号链接、错误来源或空资源集合直接失败。build.sh 在 checkout 后进入 public_resources 阶段，限时六分钟；该阶段加入既有遥测白名单，便于定位资源获取失败。没有新增 SHA256、签名证书、DEX、版本标记或成品扫描步骤。编译目标、十个私有输入、282 项原项目及全部既有 pin 保持原值。

本地六项新增测试通过，覆盖真实资源恢复、原源码保留、下载身份错误、目标冲突、许可/空数据、路径/来源和链接逃逸；实际公开下载与恢复 26 个资源成功，Bash 语法和差异检查通过。现有 runner-image 仍执行完整检查后才允许下一轮完整构建，不把局部测试或公开资源预检认定为镜像成功。执行环境已恢复，原交付私钥文件仍在，收件证书未变；未增加重复证书检查。

2026-10-25 用户将监控频率改为每轮启动后先等待 15 分钟，再每 60 秒检查一次；本轮已更新 Part II 和 README。此规则取代前述 12 分钟约定，适用于后续每次重试，不改变构建心跳和限时。继续仅推进 Native，publish=false；Docker 暂缓。

[528 项测试资源修复运行 40192716664](https://github.com/Grinch27/twrp_builder/actions/runs/40192716664) 使用 ee5f4c3a9b7ee52289daac56cb6fb6fe6689ebb4，85 项远端测试、actionlint、公开初始化/同步 smoke、主机准备和源码校验通过，完整 Job failure。source_sync 395.063s、checkout 65.500s、public_resources 1.437s、preflight 6.177s 后，compile 136.177s 以 exit 1 结束。公开资源恢复已实际通过；本轮明确缺项为 frameworks/opt/telephony/Android.bp:81 引用的 statslog-cellbroadcast-java-gen，没有成功 boot.img。

补齐同一 android-12.1.0_r4 的完整 packages/modules/CellBroadcastService@43c990d7e845365b526acc8366f44165a8f603cb。根 Blueprint 的 genrule/statslog-cellbroadcast-java-gen 使用已有 stats-log-api-gen，生成 CellBroadcastStatsLog.java；官方清单路径、tag 对应 commit、完整提供方及两份 Blueprint 的实际定义与直接引用已读取。已识别普通引用没有其他缺席提供方。CellBroadcastReceiver 是该生成模块的消费者，本轮没有额外加入。该来源审查用于修复当前明确缺项，没有新增成品校验或重复签名/版本检查。

当前共 529 项（282 原始、247 公开补充），公开测试资源锁及十个私有输入完全不变。实际锁定 manifest 的本地组合通过：529 项、12 条 copy/link；逐字段比较确认仅追加这个项目。构建/测试代码未改，继续沿用现有远端检查门槛，不重复运行已经通过的本地测试。Native、publish=false、原镜像验收和每轮启动后 15 分钟首查、此后每分钟一次均不变。

[529 项原生运行 40194255459](https://github.com/Grinch27/twrp_builder/actions/runs/40194255459) 使用 2d950cbfe070b48649f8c1d810c6024268d7b25f，runner-image 检查、主机准备和源码身份校验成功，完整 Job failure。source_sync 386.488s、checkout 90.950s、public_resources 1.737s、preflight 6.395s 后，compile 136.344s 以 exit 1 结束。明确缺项为 frameworks/base/startop/iorap/functional_tests/Android.bp:24 引用的 iorap-functional-test-apps；尚无成功 boot.img。

按实际测试引用找到同版本 platform/prebuilts/runtime，官方 android-12.1.0_r4 tag 对应 commit 9f18ff7a9984bcd4a1f7fbe9f1ec8a9697a08678。iorap/test/Android.bp 的 filegroup/iorap-functional-test-apps 引用三份官方测试 APK，完整公开 Git tree 中均为普通文件；该提供方未在原始或公开补充项目中。此次加入完整 prebuilts/runtime，保留所有原项目 pin，不摘取空文件组或禁用测试。

来源审查读取官方 tag 元数据、未截断的递归 Git tree 清单和全部 17 份 Blueprint；公开清单为 8,959 个 Git 文件、1,059,087,439 bytes，新增源码由 runner 完整同步与 checkout 验证。本地未为核验下载 APK、执行 DEX/签名/版本标记检查或重复成品校验。该项目已有 prefer:false 声明保持原状，没有通过配置强制用预编译替换现有源码；已识别普通引用没有额外缺席提供方，模块生成和变体仍由真实构建验证。

当前共 530 项（282 原始、248 公开补充）。本地真实 manifest 组合通过：530 项、12 条 copy/link；字段比较确认只新增此项目，原公开测试资源、十个私有输入、目标和镜像验收不变。没有构建/测试代码变化，继续沿用远端检查门槛；Native、publish=false、启动后 15 分钟首查及之后每分钟一次不变。

[530 项原生运行 40195813154](https://github.com/Grinch27/twrp_builder/actions/runs/40195813154) 使用 9edd6cb63db0f8a815abb455bbf33d361d208bdc，runner-image、主机准备和源码身份校验通过，完整 Job failure。source_sync 565.384s、checkout 57.127s、public_resources 2.183s、preflight 4.891s 后，compile 96.597s 以 exit 1 结束。实际公开缺项为 system/bt/apex/Android.bp:10 引用的 Bluetooth；尚无成功 boot.img。

补齐同一 android-12.1.0_r4 的完整 packages/apps/Bluetooth@3309ec0b75ef5e3757f21749571bd99b75294c1e；根 Blueprint 定义 android_app/Bluetooth。沿其实际 Java 引用一并加入 frameworks/opt/vcard@99ba408af2a2548cbfa99251223ca3a270958980（java_library/com.android.vcard）和 hardware/ril@52bdb3d68fc5fbca2d2211476c32aec1d93b098a（librilutils/Android.bp 定义 sap-api-java-static）。三个公开同标签提供方的完整 Git tree、模块定义和普通引用已审查，共 1,154 个文件、10,258,022 bytes；没有替换原项目、添加空模块或禁用测试。字面量预检仍不证明变体或命名空间解析。

工作区维护清理了此前临时文件；从远端恢复当前 builder 和唯一需要的允许列表 default.xml，不恢复整份私有归档。旧本地交付私钥已不可用，依照 Part II 在仓库之外建立新的 RSA 3072 交付密钥，并只替换仓库的公开收件证书，保持既有 CMS AES-256-GCM / RSA-OAEP 交付方式。未执行冗余证书、SHA256、DEX 或版本标记检查。

当前 533 项（282 原始、251 公开补充）。实际 manifest 本地组合通过：533 项、十个私有输入、12 条 copy/link；逐字段比较确认仅追加三个公开项目，原输入与公开测试资源锁不变。构建/测试逻辑未改，使用现有远端检查门槛，不重复运行已通过的全套本地测试。Native、publish=false、每轮启动后 15 分钟首查及之后每分钟一次不变。

[533 项原生运行 40243031911](https://github.com/Grinch27/twrp_builder/actions/runs/40243031911) 使用 7e5fe0f0b30637b4c6000e3953af284530afdf64，runner-image 成功，完整 Job failure。source_sync 399.006s、checkout 62.094s、public_resources 1.800s、preflight 6.136s 后，compile 138.253s 以 exit 1 结束。受限摘要明确报告 cts/tests/tests/openglperf/Android.bp:19 引用的 com.replica.replicaisland 未定义；没有成功镜像。

官方同标签清单定位到完整 external/replicaisland@55474b826586641a8a265751a60fd162819839d0，共 759 个 Git 文件、7,329,636 bytes。完整公开 Git tree 和唯一 Blueprint 已读取，根 Android.bp blob 5775d9b9fdbea29f37d38fd7ce7e759190edf8b2 实际定义 android_test_helper_app/com.replica.replicaisland，直接 static_libs/junit 已有提供方。保留官方源码和原有测试设置，没有编写占位模块或改动 CTS 测试。

公开预查另读取七个固定 AOSP tag 项目的 Blueprint/Make；离线与当前有效 manifest 比较，六个消费者版本相同，其余一个 ExtServices 不在当前清单内，因此没有加入其候选 libfft2d。生成 AIDL/SDK 名字继续交由真实构建验证，不将字面量候选全部视为缺项。

当前 534 项（282 原始、252 公开补充）。本地真实 manifest 组合通过，原十个私有输入、12 条 copy/link、所有既有 pin 和公开测试资源锁不变；仅追加上述公开提供方。沿用现有远端测试门槛，Native、publish=false、15 分钟首查及其后每分钟一次不变。

[534 项原生运行 40244297878](https://github.com/Grinch27/twrp_builder/actions/runs/40244297878) 使用 2aa590a0dddb13dbf0b8a9239137710a138ea002，runner-image 成功，完整 Job failure。source_sync 611.591s、checkout 95.011s、public_resources 3.202s、preflight 5.464s 后，compile 114.036s 以 exit 1 结束。摘要仅给出 external/e2fsprogs/lib/Android.bp:37 和 SOONG_BOOTSTRAP_FAILURE，未提取依赖名字；不能声称已有确切新缺项。

同版本公开 e2fsprogs 的该位置为 apex_available，公开 build/soong/android/apex.go 的 checkApexAvailableProperty 在 OtherModuleExists 为假时输出带引号的“is not a valid module name”。现有解析器仅支持 undefined module / missing dependencies，本轮为此新增受限 INVALID_APEX_AVAILABLE 分类及精确名字提取，仍需在锁定公开 Git blob 中有完整字面量证据，发布端仍独立复核。没有输出任意原始诊断、放宽 AllowMissingDependencies 或改动 Android 源码。

两项新合成测试覆盖公开 APEX 名字、发布端复核、错误附带的私有名字、工作树篡改与排除覆盖文件；完整 87 项标准库测试通过。当前保持同一 534 项源码图、收件证书、十个私有输入、目标及静态验收，仅修正诊断能力后再次实际运行，确认失败类型再决定是否加入 Virtualization 等提供方。Native、publish=false、15 分钟首查及其后每分钟一次不变。

[534 项诊断验证运行 40246026025](https://github.com/Grinch27/twrp_builder/actions/runs/40246026025) 使用 c6449a5a5998e34a8fef890e667897f05239c34c，runner-image 成功，完整 Job failure。source_sync 424.019s、checkout 68.964s、public_resources 2.357s、preflight 6.255s 后，compile 145.087s 返回 exit 1。新的受限分类实际报告 INVALID_APEX_AVAILABLE，并从 external/e2fsprogs/lib/Android.bp:37 提取到 com.android.virt；诊断修正已在真实运行验证，没有成功 boot.img。

同版本 packages/modules/Virtualization@d96e60966ff8d29d5beb7891f9c9b3b41c1ff0ae 的 apex/Android.bp 实际定义 apex/com.android.virt。其 authfs、zipfuse 和 vm 等直接引用 crosvm_defaults、libfuse_rust、libtempfile、libstructopt、libshared_child；前三项由同版本完整 external/crosvm 提供。沿实际 Blueprint/Make 引用继续核对 Crosvm、图形后端、Wayland、Rust、Cuttlefish、TPM 和 WebSocket/WebM 提供方，合计追加 34 个完整公开项目；精确 project/name/path、tag 和 commit 见 source.lock.json 新增尾部 34 项。

来源预查读取官方 android-12.1.0_r4 manifest，31 个源码提供方的完整 shallow Git tree 与全部 Blueprint/Make，共 13,340 个文件、262,631,932 bytes。另对较大的 Cuttlefish/5.10 内核预编译提供方只读取官方 tag commit、完整 Gitiles tree 元数据和全部四份构建描述，共 162 个文件记录；没有为核验下载或扫描二进制。它们为 Microdroid 测试提供 kernel_prebuilts-5.10-arm64、kernel_prebuilts-5.10-x86_64、cuttlefish_crosvm_bootloader、mkenvimage_host 等原有模块，不替换 Selene 原厂 kernel/DTB 或十项私有输入。合并现有名字及实际定义后，普通引用没有新增缺席提供方，剩余五个字面量候选是 AIDL/SDK 生成名；此结果不证明变体、命名空间或真实构建闭包。

官方清单中六项公开依赖位于 device/ 或 kernel/ 命名空间。原公开追加项验证器仅允许 platform/，本轮增加六个明确的 name/path 对照项，包含官方 kernel/prebuilts/5.10/x86-64 对应本地 x86_64 的别名；未笼统开放其他命名空间或更换下载主机。新增测试覆盖有效官方别名、私有输入保留、错配路径和未知 device/kernel 名称拒绝。完整 89 项标准库测试通过。

当前 568 项（282 原始、286 公开补充），真实 manifest 本地组合通过，原十个私有输入、12 条 copy/link、既有 pin、公开测试资源锁、Selene 目标和静态验收不变。没有缺依赖绕过、测试禁用或跨版本二进制替换；继续 Native、publish=false、15 分钟首查及其后每分钟一次。

[568 项原生运行 40247223923](https://github.com/Grinch27/twrp_builder/actions/runs/40247223923) 使用 e827148a3378143d8e7f22c09db9cd0d6bffa43c，runner-image 成功，源码同步、checkout、测试资源和预检通过。source_sync 640.530s、checkout 129.740s、public_resources 2.826s、preflight 7.048s 后，compile 104.416s 返回 exit 1。新的实际缺项为 packages/modules/Virtualization/microdroid/Android.bp:215 引用的 virt_device_prebuilts_kernel_modules-5.10-arm64；尚无成功 boot.img。后续文档/权限修正提交 f452ca64a1370343801273e6288228e0d5568497 仅恢复 source_inputs.py 原有 100755 模式，未重启完整构建或更换图。

补读锁定 Microdroid 原始 Blueprint：android_filesystem 的 deps 属性分别声明 arm64 和 x86_64 的两个 5.10 内核模块包。前一轮普通模块属性预检未覆盖这个 deps 属性，本轮对该文件全部 deps 名字重新比较，除这两个提供方外没有额外缺席字面量。官方同标签清单给出的完整项目为 kernel/prebuilts/common-modules/virtual-device/5.10/arm64 与同目录 x86-64；不采用空模块、摘取单个二进制或修改 Microdroid 源码。

两个独立公开 AOSP 镜像的 android-12.1.0_r4 annotated tag 与 peeled commit 一致：arm64 为 3f1820d76e31e8d39c9bf20e4b4c3c2a2981f598（tag b9cf0bd91145c75256fcb5f68961bb1c53c53201），x86-64 为 0ce01fc195f5957db4bcfcd5d5aa904240866239（tag 95ddf8fe79013abef068a4378d69ce2251d73a52）。未截断 Git tree 共 129 个文件记录、177,781,324 bytes；两份根 Blueprint 实际定义相应 prebuilt_kernel_modules，srcs 为 *.ko，并保留原架构选择。只读取树元数据和构建描述，没有下载或扫描内核模块二进制。官方 Gitiles 的本轮直接读取不可用，未将其记为成功；Runner 仍从固定官方 AOSP host 完整同步，并检验锁定 HEAD 和 clean 状态。

公开项目验证器只追加这两个准确 name/path 对照，现有有效/错配测试增加相应案例，继续拒绝任意 device/kernel 名称或错配路径。原十个私有输入、282 项原 pin、全部既有公开 pin、12 条 copy/link、公开测试资源及 Selene 原厂 kernel/DTB 输入不变。当前共 570 项（282 原始、288 公开补充）。

本地执行环境暂不可用，未声称本轮实际私有 manifest 本地组合、更新后的测试或产物解密通过；保留现有 runner-image 测试与完整 Job 身份校验门槛。此前在本地建立的交付私钥未被上传或更换，当前可达性仍取决于执行环境恢复。继续 Native、publish=false、每轮 15 分钟首查及之后每分钟一次。

[570 项原生运行 40249307508](https://github.com/Grinch27/twrp_builder/actions/runs/40249307508) 使用 8ffcf053c1c1ba45b598eb65aecbd371534fe63d，runner-image、源码同步和身份校验通过。source_sync 568.953s、checkout 46.688s、public_resources 3.090s、preflight 4.348s 后，compile 89.738s 返回 exit 1。受限摘要实际报告 libnativehelper/Android.bp:187 的 INVALID_APEX_AVAILABLE，缺少 com.android.extservices；尚无成功 boot.img。

补齐同一 android-12.1.0_r4 的完整 packages/modules/ExtServices@8dabea5aafff4e50f58ffcb37167fb6ac10e23b9，其 apex/Android.bp 实际定义 apex/com.android.extservices；一并补齐 native/tests/Android.bp 直接引用的 external/fft2d@bc2ce47fbe073485fd10360187d0a803880ec998，实际定义非空 cc_library_static/libfft2d。后者是先前公开预查发现、当时因消费者不在清单而没有加入的依赖，现在与实际缺失的消费者一起锁定。

两个独立公开镜像的同标签 commit 一致；完整未截断 Git tree 共 201 个文件、833,576 bytes，全部九份 Blueprint/Make 已读取。合并现有公开名字和两项目实际定义后，已识别普通、APEX 和 deps 引用没有其他缺席名字，visibility 的 __subpackages__ 为作用域标记；预查仍不证明生成模块、变体和命名空间解析。保留完整来源及原有许可文件、原有测试和架构设置，没有占位模块或测试绕过。

当前 572 项（282 原始、290 公开补充）。锁定清单仅追加这两项，既有 pin、十项私有输入、12 条 copy/link、公开资源锁及 Selene 目标保持原值。构建/测试实现未变化；本地环境仍不可用，不声称本轮实际 manifest 本地组合或测试通过，继续依赖现有远端门槛与官方源完整同步/HEAD 校验。Native、publish=false、15 分钟首查及其后每分钟一次不变。

[572 项原生运行 40251178634](https://github.com/Grinch27/twrp_builder/actions/runs/40251178634) 使用 6ed5a0e76cce0c8510d31418ee99db16520e97c6，runner-image 成功，完整 Job failure。source_sync 421.409s、checkout 71.451s、public_resources 2.199s、preflight 6.587s 后，compile 151.322s 以 exit 1 结束。实际受限错误为 frameworks/base/packages/SettingsLib/Utils/Android.bp:23 的 INVALID_APEX_AVAILABLE，缺少 com.android.cellbroadcast；尚无成功 boot.img。

补入此前已定位、当时尚无实际需要的同标签 packages/apps/CellBroadcastReceiver@ec8fa38ac7343c56ba52239174212a1e2b81a631。其 apex/Android.bp 实际定义 apex/com.android.cellbroadcast，apps 引用本项目的 CellBroadcastApp 与 529 项时已加入的 CellBroadcastServiceModule。本轮同时复读已锁定 CellBroadcastService 的原始根 Blueprint，确认其提供方身份，不重复加入已有项目。

两个独立公开镜像的 android-12.1.0_r4 commit 一致；完整未截断 Git tree 为 2,219 个文件、7,554,461 bytes，全部八份 Blueprint/Make 已读取。合并现有公开名字、已有 CellBroadcastService 与本项目实际定义后，已识别普通、APEX、deps 引用均有字面量提供方；仍须真实构建确认命名空间和变体。没有修改 APEX 声明、关闭测试或新增缺项绕过。

当前 573 项（282 原始、291 公开补充），仅追加这个完整公开项目。原有 pin、十个私有输入、12 条 copy/link、公开资源锁和 Selene 原厂 kernel/DTB 输入不变。构建/测试实现未改；本地执行环境仍不可用，未声称本轮本地 manifest 组合或测试通过，沿用远端检查与完整官方同步/身份校验。继续 Native、publish=false、15 分钟首查及其后每分钟一次。

[573 项原生运行 40252485700](https://github.com/Grinch27/twrp_builder/actions/runs/40252485700) 使用 dfced801d8d9ebacb911c6206fc44aaa8e1db93e，runner-image 成功，完整编译 exit 1。source_sync 433.362s、checkout 69.017s、public_resources 4.079s、preflight 6.196s 后，compile 持续 385.375s；Ninja 已进入后续 383 步批次，受限摘要给出 Recovery prebuilt、SELinux 和 build/make/core/main.mk 的公开位置，类别仅为 UNCLASSIFIED_COMPILE_FAILURE，尚无成功 boot.img。

公开 TeamWin/android_build 的 android-12.1 分支提交 1b692e2248609f50a27c48cce53b7445cecdcfc5，已与允许的原 manifest 严格离线比较并匹配；没有用私有原 SHA 发起外部查询。其 core/main.mk:750 明确为 Missing required dependencies 检查，753 行按 TARGET/HOST/HOST_CROSS 输出 requires non-existent module 列表，756 行终止构建。当前摘要器只在带源码位置的行里收集名字，因此未解析这些独立列表行。公开 Recovery 同分支也与原 pin 匹配，其 prebuilt/Android.mk:454 是 vendor_hw 警告；没有据此修改设备配置或加入 BUILD_BROKEN_MISSING_REQUIRED_MODULES。

本轮仅修正诊断，保留同一 573 项图。新增固定 MISSING_REQUIRED_MODULE 分类、严格完整 Make 行格式及可选 32/64 位后缀归一化；最多收集 128 个候选。只有错误位置对应锁定公开 build/make/core/main.mk，且该公共 Git blob 确有检查器固定格式时，列表名字才能进入原有的公开 Git 精确字面量取证。父模块名、未知名字和原始列表不输出；发布端仍独立复核，45 秒/32 个证据位置等界限不变。

新增两项合成测试，覆盖已核验检查器、公开名字、私有父/子名字、host/target 和位数后缀、排除检查器、缺少检查器、工作树伪造检查器。执行环境仍不可用，尚未声称新增测试本地通过；现有 runner-image 将先运行全部测试，通过后才允许完整 Job。原输入、pin、资源、目标和镜像验收不变，继续 Native、publish=false、15 分钟首查及其后每分钟一次。

[573 项 Make 诊断运行 40254471959](https://github.com/Grinch27/twrp_builder/actions/runs/40254471959) 使用 da77f4588e43e6ef259a8013027cc64ddb47e938，91 项远端测试、actionlint 和公开 smoke 通过。source_sync 538.841s、checkout 59.041s、public_resources 3.179s、preflight 4.699s 后，compile 362.947s 返回 exit 1。新 MISSING_REQUIRED_MODULE 分类已实际提取 18 个名字，均由公开 Git 精确字面量再次证明：NetworkPermissionConfig、PlatformCaptivePortalLogin、PlatformNetworkPermissionConfig、RemoteProvisioner、calendar-provider-compat-config、com.android.vndk.current、documents-ui-compat-config、ip、iptables、libbinderthreadstate、newfs_msdos、shflags、ss、tcpdump、twrp、ueventd、unzip、vndkcorevariant.libraries.txt。尚无成功 boot.img。

按实际引用补齐同一 android-12.1.0_r4 的 12 个完整公开项目：external/{iproute2,iptables,newfs_msdos,shflags,tcpdump}、packages/apps/{DocumentsUI,RemoteProvisioner}、packages/modules/{CaptivePortalLogin,NetworkPermissionConfig,vndk}、packages/providers/CalendarProvider，以及后者测试直接引用的 frameworks/opt/calendar。精确 pin 见 source.lock.json 新增尾部 12 项。system/apex 已在原清单中，未重复加入。两个独立公开镜像的 tag commit 一致，完整未截断 Git tree 共 3,787 个文件、60,549,292 bytes，全部 34 份 Blueprint/Make 已读取；普通 Blueprint、APEX、deps 及 Make 直接静态/共享库引用未发现其他缺席字面量，余项为已有 AIDL/SDK 生成名。此预查仍不证明变体或命名空间解析。

packages/modules/vndk 实际定义 com.android.vndk.current、vndkcorevariant.libraries.txt 和 v28/v29/v30/v31 APEX。libbinderthreadstate 已有同版本清单锁定的 v29 预编译定义，是否随完整 VNDK APEX 依赖图正确导出仍交由实际构建确认，没有添加 Android 旧版本源码或强制替换二进制。

另三项属于输出文件名与模块名混用。独立公开分支及严格离线比较确认当前 Recovery 为 TeamWin 5c3d206a5eeb3d446bcda8248a405a4b278bab5c，system/core 为 ac4f36c7eb076ea2c582061a21dfc49eaa71e623，libziparchive 为 AOSP a5d4eccd8b2c54d708bdd404b550730f86d470d2：orscmd 的 stem 是 twrp；init_second_stage 的 recovery 变体提供 ueventd 符号链接；ziptool 的 recovery 变体提供 unzip。当前公开 Soong c6c059ab28c8c67921c0838a994bb70d53594aa7 同样离线匹配，cc.go/cc/androidmk.go 确认 recovery 变体导出 .recovery 后缀。没有使用私有原 SHA 发起网络查询。

新增 patches/recovery-required-modules.patch，在完整 checkout 校验之后、preflight 内先 git apply --check，再应用两处公开源码修正：根必需项的 twrp 改为真实 orscmd，并保持原有 OEM 模式排除；relink 的 required 模块将 twrp、ueventd、unzip 分别映射到 orscmd、init_second_stage.recovery、ziptool.recovery。实际 relink 文件清单、复制动作、运行时文件名和原模块实现完全不变，没有禁用缺依赖检查或创建占位模块。原始项目 pin 保持不变，公开补丁由 builder 明确记录和应用，不写入私有归档。

新增三项合成测试覆盖 GNU Make 实际求值、真实模块拥有者、文件名清单保留、OEM 条件和源上下文不符时预检不写文件。本地环境不可用，未声称测试、补丁本地应用或新 manifest 本地组合已通过；现有 runner-image 将先执行完整检查，通过后才运行完整任务。

当前 585 项（282 原始、303 公开补充）。原十个私有输入、12 条 copy/link、全部既有 pin、公开测试资源锁、Selene 原厂 kernel/DTB、编译目标及镜像静态验收保持原值。继续 Native、publish=false、15 分钟首查及其后每分钟一次。

[585 项原生运行 40257561247](https://github.com/Grinch27/twrp_builder/actions/runs/40257561247) 使用 df01c27a602653ce5148f53e491cdccbf076ed6c，94 项远端测试、actionlint、公开 smoke、完整同步/checkout 和真实源码补丁应用均通过。source_sync 485.700s、checkout 66.854s、public_resources 2.635s、preflight 6.483s 后，compile 418.446s 返回 exit 1。Make 缺项由 18 个缩小为唯一 libbinderthreadstate；其余提供方与三个输出名/模块名修正已实际越过检查，但尚无成功 boot.img。

唯一残留来自公开 Recovery prebuilt/Android.mk:73 无条件打包 recovery/system/lib64/libbinderthreadstate.so。当前锁定 frameworks/native 与公开 android-12.1.0_r4@89c808424fbce9e40c0d4e0d1920b3c64a191b7f 严格离线匹配，libs/binderthreadstate/Android.bp 仅定义静态 libbinderthreadstateutils 和测试，libs/binder/Android.bp 已不链接旧 libbinderthreadstate。AOSP 的公开移除记录亦删除该空兼容共享库：https://android.googlesource.com/platform/frameworks/native/+/0d4dfb1c9b6344023495e8916251311415759b12%5E2..0d4dfb1c9b6344023495e8916251311415759b12/ 。VNDK 29 中同名预编译是旧 vendor 快照，不能据此当成当前 Recovery 源码实现或跨版本替代。

本轮在同一公开补丁中仅删除这条已过时的 Recovery 库打包输入，保留其余库、三个真实可执行模块映射、原 OEM 条件和全部功能实现。没有从旧 Android 回填库、创建空模块或关闭 Make 缺依赖检查。合成 GNU Make 测试增加有效库清单的完整比对，确认只移除旧条目、其余库及二进制文件名保持原样；上下文不符仍先失败且不写文件。本地环境不可用，本轮修改后的测试与补丁由现有远端门槛和真实预检验证，不声称本地通过。

准备期间 main 先后并入 722ab99a6de82cb945d7a58d30d7a01ee293ee02 和 dee7f8a43d24537d0a3a4a68e2813e67c7a48c15 的安全命令跟踪及换行修正。已读取完整差异，保留 scripts/build.sh、run_native.py 与新增跟踪测试，不覆盖并发工作。新增跟踪只输出固定允许列表命令模板，不输出私有参数或编译原文。

源码仍为 585 项，全部 pin、十个私有输入、12 条 copy/link、公开测试资源、Selene 内核/DTB、目标和静态验收保持原值。继续 Native、publish=false、每轮 15 分钟首查及之后每分钟一次。

1. 先验证公开 builder 的 push 静态检查。失败时仅修改 builder。
2. 用户明确授权私有输入在 GitHub runner 中处理，并配置只读 `TWRP_SOURCE_TOKEN`。不要在聊天中提供令牌。
3. 本次持续修复授权下，运行 publish=false 的完整任务，每次上限 350 分钟。任一失败立即结束当前尝试；根据真实证据审查、修正和验证后继续尝试，直至取得通过静态验收的成品。付费资源、扩大私有输入或设备操作仍需单独授权。
4. 需要保留私有失败日志时先约定私有出口；临时 runner 结束后本地日志不可恢复。不将它们写入公开日志或 Artifact。
5. 构建成功后，是否公开镜像与是否进行设备验收分别决定。设备操作不在当前授权中。

当前最大不确定性：585 项图的生成模块、变体和条件依赖能否正确解析，以及镜像编译与静态验收能否通过；尚无成功 boot.img。

用户可能遗漏：公开镜像也会包含配置/固件；publish=false 仅保留本地私钥可解密的成品密文，不保留完整私有诊断日志；独立会话必须持有对应私钥。

Q1（私有输入授权）：已获批准，且实际读取与身份校验已通过。
Q2（公开产物）：本轮保持 publish=false；未批准公开镜像或 Release。
Q3（失败诊断）：本轮仅保留公开安全摘要；完整私有日志的持久出口尚未配置。

## 2026-10-26 — Make 未加引号的模块诊断

运行 [40259619312](https://github.com/Grinch27/twrp_builder/actions/runs/40259619312)（96f8cdb4ab5e4a7ba5ce412fb354b1c2006197fd）完成 585 项源码同步、checkout 和补丁应用，compile 414.939 秒后 exit 1，类别仍为 MISSING_REQUIRED_MODULE，但公开依赖列表为空。当前批次 Ninja 382/383 不代表整个编译完成；尚无成功 boot.img。

公开 Make 模块声明及 required 列表使用未加引号的字面量，原诊断只核验带引号的 Blueprint/Go 字面量，因此空列表不能证明没有缺项。本轮只补充诊断：允许从锁定公开 Git 的 .mk 文件中，对 LOCAL_MODULE、LOCAL_REQUIRED_MODULES、库依赖、TWRP_REQUIRED_MODULES 和 PRODUCT_PACKAGES 赋值的完整独立 token 取证，支持续行，排除注释、未知变量、子串及工作树改动。摘要端和发布端使用相同规则，重新核验路径和固定 Git blob；宽匹配搜索仅定位候选文件，不授权输出。原始日志、父模块、未知名字仍不输出。

本地完整标准库套件 99 项通过（含新 Make 字面量与隐私回归）；585 项图、原 pin、十个私有输入、镜像验收和 publish=false 均保持不变。此轮没有根据空摘要猜测或删除 required 模块，需新运行确认实际缺项。

## 2026-10-26 — 原生编译资源压力缓解（待真实构建确认）

- 585 项运行 40264306025（main a9e25ab2c74edcc8b0a2e5c0bae29642a24e68b0）完成 runner-image 检查、私有输入受限获取、源码同步和 checkout，最终工作流 failure；Native 编译步骤标为 cancelled，进度分支没有最终 exit_code 或新的可信缺项诊断，也没有密文 Artifact。公开遥测最后一次记录 compile 835.0 秒、当前 Ninja 批次 245/246、MemAvailable 1052 MiB、SwapFree 51 MiB；工作流约一小时后结束。此证据提示显著内存压力，但**不能单凭它断言发生了 OOM 或确定 GitHub Runner 终止原因**。
- 本轮不依据旧 VNDK 预编译中的 libbinderthreadstate 字面量补造提供方，不修改 585 项公开源码锁定 pin 或缺项检查。仅将 Native `mka bootimage` 并行度由 4 降至 2，并同步公开命令模板、回归断言、README 与 source.lock.json 的非源码构建元数据；repo sync 仍为 -j4。保留原有日志白名单、失败退出、静态镜像验收及 publish=false 加密交付。此举是可回退的资源缓解措施，不是成功构建证明；下一轮须由真实 Runner 验证。

## 2026-10-26 — 有限原生进程清理及资源缓解

- 用户要求 Complete job 最多 3 分钟，超时放弃。已核对 GitHub 官方工作流语法与 actions/runner 的 JobExtension.cs、LinuxProcessExtensions：Complete job 是 Runner 的内建 FinalizeJob 阶段，孤儿进程扫描同步读取 `/proc/<pid>/environ`，没有 YAML 可配置的独立 3 分钟限时。不能伪称普通步骤 timeout-minutes 会控制此内建阶段。严格终止该阶段需要取消整次运行，无法仅跳过它并保留成功结果；本轮没有启用这种整次取消。
- 原 stop_group 在主 Shell 已退出、TERM-resistant 子进程仍存活时，只等待主 Shell，可能不再发送 KILL；本轮改为始终向本构建组补发 KILL，保留真实构建退出码。启动时记录独立 session 的进程组与 start ticks；额外 always 收尾步骤仅清理该记录会话，拒绝 PID 重用、自身进程组、身份变化和符号链接记录，忽略已死亡的僵尸进程，既不遍历环境也不输出原始进程数据。步骤 3 分钟上限，内部 175 秒 timeout 加 5 秒 KILL；仅清理失败允许继续，不改变编译失败状态。
- 9abc25f 的 40293182407 继续在同一 Ninja 批次 245/246 发生编译 cancelled；受限记录为 MemAvailable 1001 MiB、SwapFree 94 MiB、compile 306 秒，缺少最终构建 exit_code。此为内存压力线索，不是已确认的 OOM 诊断。该次运行已 cancelled，未产出成品。本轮在原有临时 hosted Runner 准备中新增 12 GiB Swap，不关闭原 Swap；磁盘初始门槛从 50 调为 62 GiB，保证分配后仍留原 50 GiB 源码空间。编译前原 18 GiB 检查、-j2、全部源码 pin、输入白名单、失败判定及加密交付不变。
- 本地 104 项标准库用例中 102 项通过、2 项因执行器 /proc 命名空间不暴露真实子 PID 而跳过；跳过项为真实会话记录/清理及 stubborn 子进程进程状态检查，需由 hosted Runner 执行。其余用例覆盖主进程退出后仍补发组 KILL、身份变更拒绝、有限等待和符号链接拒绝；Shell 语法、YAML 解析和差异检查通过。实际 hosted Runner 的 Swap 创建、新清理阶段和完整构建仍待真实运行；没有在本地执行 Runner 清理或 Swap 操作。

## 2026-10-26 — 首次正常收尾与真实 required 清单修正

运行 [40302227133](https://github.com/Grinch27/twrp_builder/actions/runs/40302227133)（ceea8003e1d39a9e2caef0155124bcfbf7280dfb）的 runner-image、actionlint、公开 smoke 和完整预检通过。增加 Swap 后，构建恢复真实 compile exit 1，417.358 秒；本轮结束时 SwapFree 15121 MiB。自定义清理和内建 Complete job 均在各自同一秒完成：10:05:22Z 与 10:05:23Z，没有此前数十分钟清理停顿。不能据此声称内建阶段已经被设置 3 分钟限时。

新的受限诊断实际给出 event-log-tags、fs_mgr、fscryptpolicyget.recovery、keystore_auth、permissive.sh、plat_hardware_contexts、task_recovery_profiles.json、teamwin 八项。完整公开 Recovery android-12.1 checkout 为 5c3d206a5eeb3d446bcda8248a405a4b278bab5c，已与锁定版本一致；额外公开 TeamWin extras/security 分支与锁定 ffbe71168883383d7048d076000f4db9936bc00a / 14737db1429b8eebc15568bc748b2cd79ccad5c2 一致。AOSP r4 sepolicy/logging commit 与原 pin 一致。没有用未知私有 SHA 探测外部服务。

- teamwin 在该公开 prebuilt 文件仅是随后 CLEAR_VARS 前未注册的旧 dummy 名，真正 relink 三模块及 twrp_ramdisk 已分别列入 required，保留其动作。permissive.sh 与 plat_hardware_contexts 没有当前提供方及 runtime 文件复制，保留真实 plat_hwservice_contexts、vndservice_contexts 和现有 SELinux 设置。删除这些过时必需项，不创建空模块。
- 公开 Recovery 全树搜索表明 keystore_auth、fscryptpolicyget 只出现在构建/复制清单中，不存在 C/C++、Shell 或 init.rc 调用；对应锁定 security/extras 已不提供它们。移除两个无提供方工具的 required 和复制项，保留 keystore2、所有现有加密库与加密实现。fs_mgr 的真实实现为现有 libfs_mgr，保留该库、F2FS 工具及相关源码；仅移除不存在的同名可执行项。event-log-tags 没有当前模块提供方，仅移除无效 required 名，保留 logcat/logd 和所有实际日志实现。设备 FBE/日志运行行为仍 NOT_TESTED。
- task_recovery_profiles.json 需要真实文件，不能仅删除。现有同一 system/core 的 task_profiles.json 有 40 个 Profiles，libprocessgroup 明确读取 /etc/task_profiles.json。本轮给现有非空文件增加与同文件 cgroups.recovery.json 同式的 Recovery prebuilt_etc 安装声明：module=task_recovery_profiles.json，filename=task_profiles.json，recovery=true。原 JSON 内容不改，原 required 名保留；不使用空配置或其他 Android 版本文件。新增公开补丁先检查再应用，585 项和全部 pin 不变。

本地 104 项用例为 102 项通过、相同 2 项执行器 /proc 限制跳过。GNU Make 夹具实际验证有效加密、日志、F2FS 和 relink 项仍保留，过时 required/工具复制项移除；公开真实 Recovery 完整差异及 system/core 原始 Blueprint 的补丁上下文检查通过。Shell 语法和差异检查通过，完整构建仍待实际执行。另恢复 prepare_runner.sh 原有 100755 模式；先前 API 提交只误改了该执行位，显式 bash 调用已验证未受影响。

## 2026-10-26 — HAL 名字诊断补齐

3642339 的运行 40305990297 完成真实源码补丁、task profile 安装规则预检和 compile 435.536 秒后返回 exit 1，类别仍为 MISSING_REQUIRED_MODULE，受限公开依赖为空。此时内存与 Swap 已回到充足状态，不是新取消或清理挂起。

进一步检查诊断正则发现它未接受 Android HAL 合法模块名中的 @，同时影响 required 行的父/子模块名、Soong 引号名及发布端复核。本轮仅将这些模块名字符集补上 @，仍限 128 字符、固定 Make 行格式和锁定公开 Git 精确字面量证明；不输出父模块、私有值或原始行，不修改源码图和 HAL 实现。新增合成测试覆盖带 @ 的父模块、公开子模块、64 位后缀及无公开证明的私有名字拒绝。

本地 105 项用例中 103 项通过，原 2 项 /proc 执行器限制跳过；差异及 Shell 语法检查通过。当前空列表的具体缺项仍待真实新运行，不能猜测或禁用 required 检查。

## 2026-10-26 — 当前公开 builder 补丁字面量取证

7018687 的运行 40308811240 完成预检，compile 357.458 秒返回 exit 1，MISSING_REQUIRED_MODULE 仍无可公开确认名字；清理和 Complete job 均已成功，没有旧的收尾停顿。@ 解析修正没有取得本次具体缺项，不能将空摘要解释为没有依赖问题。

当前诊断只查锁定 Android 上游，而公开 builder 自己的补丁也引入了如模块名映射的字面量。本轮增加一个严格限定的公开证据路径 builder-public/patches/recovery-required-modules.patch：仅从 HTTPS origin 为 Grinch27/twrp_builder、HEAD 等于本轮 GITHUB_SHA 的 Git blob 读取这一份固定补丁，最大 64 KiB，只接受新增行里的完整名字 token。工作树变更、其他仓库、旧 commit、被删行和其他文件不能授权输出。摘要端和发布端分别核验，发布端再次绑定本轮 builder_commit；只把通过格式校验的公开 GITHUB_SHA 元数据加入构建子环境，仍不传凭据。此举不证明模块变体可用，也不改变源码图、设备功能或私有输入范围。

新增 required_candidates、unverified_required_candidates 两项 0–128 的计数，帮助区分未解析与已解析但无公开名字证据的情形，不输出未知名字、父模块或原始错误行。合成 Git 回归覆盖公开补丁、工作树伪造、提交不符、错误 origin、发布端独立复核、公开元数据与凭据分离。本地 107 项用例中 105 项通过，原 2 项 /proc 执行器限制跳过；Shell 语法与差异检查通过。新诊断仍待真实运行，尚无成品。

## 2026-10-26 — 区分公开文件名与 HOST_CROSS 内部前缀

40324788270（main f116865）完整同步和预检通过，compile 359.044 秒后 exit 1；受限诊断为 MISSING_REQUIRED_MODULE，12 个候选均无字面量证明。仍未取得 boot.img。本轮先补齐诊断证据，而不猜测删除必需项：优先直接核验本次已确认的公开错误文件，再进入有界全图搜索；接受公开 Recovery relink 赋值中以固定 Make 路径变量开头的完整字面量文件名，不执行变量、不推断 .so 或 .recovery 后缀，也不读取工作树覆盖。

公开 TeamWin android_build/android-12.1 当前提交与原 pin 1b692e2248609f50a27c48cce53b7445cecdcfc5 一致，其 core/main.mk 在 HOST_CROSS 必需项解析前固定添加 host_cross_。仅在该锁定 Git blob 包含这条精确变换、且实际错误是 HOST_CROSS→HOST_CROSS 时，允许以去前缀后的**公开源码字面量名**独立取证、报告；不输出生成 ID、父模块或未知名称。新增有界数量 host_cross_required_candidates。该能力仅定位内部映射，不证明模块提供方或构建成功。

本轮继续 Native/main，源码585项及全部 pin不变；publish=false；不改变私有输入、加密交付、镜像验收或设备边界。新运行仍须等待15分钟后首查、其后间隔至少60秒。已有本地私钥文件仍可用，未复制、上传或输出其内容。

## 2026-10-26 — 修正已确认的 Vibrator / NTFS / Keystore 打包名

40330321140（a4da576）完整预检通过，compile 452.795秒返回1。新增诊断实际确认 android.hardware.vibrator-V2-ndk.so、keystore、keystore_cli、mkntfs、ntfs-3g、ntfsfix；HOST_CROSS计数0，排除该方向；另6项仍缺公开名字证明，不能声称全部解决。

公开 hasan6034 设备树在原pin c77512445ab5be5908ddb3ca9c659e6b149c78de 的 device.mk 确实把 Vibrator 文件名写入 TARGET_RECOVERY_DEVICE_MODULES。新增独立公开补丁，只将该模块项改为 android.hardware.vibrator-V2-ndk，保留共享库实际路径的 .so；不修改设备私有覆盖。先检查三份源码补丁，再应用，追踪模板同步新增两个固定事件。

公开 LineageOS ntfs-3g/lineage-18.1 与原pin 7471d6403640f1cd0878cc2c87279571a497bcb7 一致，其 Android.bp 从 ntfsfix.c、mkntfs.c 和 ntfs-3g.c 编译的模块/文件名分别为 fsck.ntfs、mkfs.ntfs、mount.ntfs。Recovery partition.cpp 已支持这些替代文件名。仅在公开 Blueprint 存在时自动选择现有正确打包分支，保留既有显式开关与旧源码分支；不删除NTFS功能。

公开 TeamWin security/android-12.1 与原pin 14737db1429b8eebc15568bc748b2cd79ccad5c2 一致，其 keystore/Android.bp 只定义 keystore_cli_v2，守护进程为 keystore2。公开 Recovery 源码已确认 init 启动 keystore2；旧 keystore/keystore_cli 仅出现在复制列表，无执行调用。本轮移除三处旧工具复制输入，保留 keystore2、keystore_cli_v2、全部现有加密库与配置，不新增跨版本替代。

诊断再补充 TARGET_RECOVERY_DEVICE_MODULES 的公开字面量、固定公开设备 device.mk 优先取证，以及公开库文件名去 .so 后的完整字面量 stem；不推断 .recovery 等变体、不执行Make表达式、不读取覆盖文本。新增回归实际执行GNU Make，核验设备模块/文件名区别、NTFS自动/显式选择和原有加密工具保留；公开完整设备文件的补丁precheck通过。继续585项目全部原pin、Native/main、publish=false与15分钟/每分钟节奏，实际完整编译待下一轮确认。
