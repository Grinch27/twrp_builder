# selene TWRP 构建前审查

核验日期：2026-10-22，Asia/Shanghai。源仓库 `Grinch27/twrp_selene` 的基线为 `main@b0aef415d0a5eabf66663c8882d16e1e227381dd`。新构建仓库为 `Grinch27/twrp_builder`，检查开始时为空且公开；源仓库私有。

## 事实与范围

本次按根目录和子树递归读取 Git tree；对超限/截断响应继续下钻，最终无未完成子树。共枚举 **370,374 个 Git 文件/链接对象、3,925 个符号链接**，逻辑字节合计 26,246,399,889。该数字包括当前维护文件，与原归档仅统计原始文件的数字范围不同。未进行 370,374 个文件的逐行代码审查或全部二进制下载。

重点读取根 AGENTS/agents/readme、重建 manifest、删除前审计、Release 清单、设备配置、实际最后构建退出记录与日志、测试禁用清单、扫描排除记录、源码闭包报告、公开设备树和构建参考。未恢复旧工作区、未运行旧构建器、未连接手机。

| 领域 | 本次确认事实 | 影响 |
| --- | --- | --- |
| 最新归档构建 | 2026-10-06 最后退出码为 1，新运行目录没有 boot.img | 旧 artifacts 内的 boot.img 不能作为当前源码成功证据 |
| 最后失败 | Soong 图生成阶段缺少 Robolectric monitor 1.0.2-alpha1 AAR；当前 Git 清单中也没有该 AAR | 补齐一个文件不能推出全部闭包已完成 |
| Manifest | 282 个唯一项目，282 个 40 位 SHA，12 个 copy/link 指令 | 可作为锁定输入；尚无干净完整同步及构建证明 |
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

- 本地标准库边界测试：20 项通过，包含多组子案例；覆盖输入路径、覆盖拒绝、链接逃逸、下载身份、manifest 锁定及危险指令、boot/cpio/解压边界、错误 kernel/DTB/fstab 和未验证状态保留。
- 新增 Python 可解析、全部 shell 通过 bash -n、工作流 YAML 可解析、手动触发与公开产物条件检查通过。
- 实际归档 manifest 经新校验器通过：282 个项目、40 位锁定 revision、受限下载来源与路径。
- GitHub Actions [运行 39693140718](https://github.com/Grinch27/twrp_builder/actions/runs/39693140718) 已成功：在代码提交 `dadd8c3dcfcc9e50d5d99e0c129b4cfcbacf47a6` 上，20 项测试、actionlint v1.7.7、官方下载校验及共享 Runner 解析均通过。完整编译 job 为 skipped，不能将这条绿色记录称作 TWRP 编译成功。
- 本轮连接不支持查询 Actions Secret 或发起 workflow_dispatch；`TWRP_SOURCE_TOKEN` 是否配置尚未核实。当前没有以其他身份或接口绕过该限制。
- 完整 repo sync、Ubuntu 容器依赖安装、mka bootimage、真实 boot.img 静态验收：**NOT_EXECUTED**。
- 新镜像启动、触摸、FBE、备份/恢复、动态分区/snapshot：**NOT_TESTED**。

## 后续顺序与停止点

1. 先验证公开 builder 的 push 静态检查。失败时仅修改 builder。
2. 用户明确授权私有输入在 GitHub runner 中处理，并配置只读 `TWRP_SOURCE_TOKEN`。不要在聊天中提供令牌。
3. 手动运行一次 publish=false 的完整任务；上限 350 分钟。任何输入、同步、容量、Soong 或静态验收失败即停止，不自动反复构建。
4. 需要保留私有失败日志时先约定私有出口；临时 runner 结束后本地日志不可恢复。不将它们写入公开日志或 Artifact。
5. 构建成功后，是否公开镜像与是否进行设备验收分别决定。设备操作不在当前授权中。

当前最大不确定性：完整的 282 项上游 checkout 能否闭合 Soong 依赖并在标准 runner 空间内生成新 boot.img。

用户可能遗漏：跨仓库私有读取需要单独的只读凭据；公开镜像也会包含配置/固件；publish=false 不保留可下载镜像或完整诊断日志。

Q1：是否批准十个指定私有输入由 GitHub 托管 runner 处理，并自行配置只读 secret？
Q2：首次运行保持 publish=false，还是明确批准公开成功产物与实验性 Release？
Q3：若首次失败，选择私有 runner/存储保留诊断，还是先在独立本地环境复现？
