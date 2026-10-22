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
| HIGH | 282 项重建图仍可能缺少 Soong 全局依赖 | 完整 checkout，先核对每个 HEAD 和 clean 状态，首个失败停止；不循环补库或禁用测试 |
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

- 当前标准库边界测试：48 项通过，包含多组子案例；覆盖输入路径、覆盖拒绝、链接逃逸、下载身份、manifest 锁定及危险指令、公开补充项目的身份/路径/版本冲突与 checkout、boot/cpio/解压边界、错误 kernel/DTB/fstab、未验证状态保留、同步和编译安全摘要，以及加密交付认证、进度字段白名单和诊断再次校验。
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

1. 先验证公开 builder 的 push 静态检查。失败时仅修改 builder。
2. 用户明确授权私有输入在 GitHub runner 中处理，并配置只读 `TWRP_SOURCE_TOKEN`。不要在聊天中提供令牌。
3. 手动运行一次 publish=false 的完整任务；上限 350 分钟。任何输入、同步、容量、Soong 或静态验收失败即停止，不自动反复构建。
4. 需要保留私有失败日志时先约定私有出口；临时 runner 结束后本地日志不可恢复。不将它们写入公开日志或 Artifact。
5. 构建成功后，是否公开镜像与是否进行设备验收分别决定。设备操作不在当前授权中。

当前最大不确定性：已补入同版本 Tradefed，但 285 项依赖闭包和可成功编译的 boot.img 尚待验证。

用户可能遗漏：跨仓库私有读取需要单独的只读凭据；公开镜像也会包含配置/固件；publish=false 不保留可下载镜像或完整诊断日志。

Q1（私有输入授权）：已获批准，且实际读取与身份校验已通过。
Q2（公开产物）：本轮保持 publish=false；未批准公开镜像或 Release。
Q3（失败诊断）：本轮仅保留公开安全摘要；完整私有日志的持久出口尚未配置。
