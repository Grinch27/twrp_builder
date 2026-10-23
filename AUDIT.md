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

1. 先验证公开 builder 的 push 静态检查。失败时仅修改 builder。
2. 用户明确授权私有输入在 GitHub runner 中处理，并配置只读 `TWRP_SOURCE_TOKEN`。不要在聊天中提供令牌。
3. 本次持续修复授权下，运行 publish=false 的完整任务，每次上限 350 分钟。任一失败立即结束当前尝试；根据真实证据审查、修正和验证后继续尝试，直至取得通过静态验收的成品。付费资源、扩大私有输入或设备操作仍需单独授权。
4. 需要保留私有失败日志时先约定私有出口；临时 runner 结束后本地日志不可恢复。不将它们写入公开日志或 Artifact。
5. 构建成功后，是否公开镜像与是否进行设备验收分别决定。设备操作不在当前授权中。

当前最大不确定性：397 项图是否闭合，以及实际 Soong、镜像编译与静态验收能否通过；尚无成功 boot.img。

用户可能遗漏：公开镜像也会包含配置/固件；publish=false 仅保留本地私钥可解密的成品密文，不保留完整私有诊断日志；独立会话必须持有对应私钥。

Q1（私有输入授权）：已获批准，且实际读取与身份校验已通过。
Q2（公开产物）：本轮保持 publish=false；未批准公开镜像或 Release。
Q3（失败诊断）：本轮仅保留公开安全摘要；完整私有日志的持久出口尚未配置。
