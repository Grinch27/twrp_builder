# Selene：首次 Keymaster 版本输入与可复用 Stock 分析

适用：China MIUI `V14.0.4.0.TKUCNXM`；TWRP Native，源码基线 `1850e42a8b9c395ca0a0f7480614069eb984ff94`。这是固定固件的候选修正与离线提取设计，不是完整 FBE 实测成功声明。

## 1. 已确认事实与修正范围

| 项目 | 同版本原厂 | 已测试 Native 41374113681 | 本轮处理 |
| --- | --- | --- | --- |
| `ro.build.version.release` | `13` | `12` | 仅 Recovery 初始默认值改为 `13` |
| `ro.build.version.security_patch` | `2023-12-01` | `2022-04-05` | 仅 Recovery 初始默认值改为 `2023-12-01` |
| Recovery 框架 SDK | 不作为框架升级输入 | `32` | 保持 `32` |
| `ro.vendor.build.security_patch` | `2023-12-01` | `2021-07-01` | 消费者尚未追踪，本轮不改 |
| TEE 客户端 | V14 `libTEECommon.so` | 已与原厂一致 | 保留已有单库修正及最终镜像比较 |
| Keymaster HAL | V14 Beanpod HAL | 相关代码/常量段已确认相同 | 不替换 |
| 实际 Keymaster TA | `c09c9c5daa504b78b0e46eda61556c3a.ta`，非直接 ELF | 同名直接 ELF | 保留现状；安全封装及加载兼容性未验证 |
| 普通 Android 启动 | 原厂 | 用户已确认启动及再次重启可用 | 保留 `TW_NO_FASTBOOT_BOOT := true` |

版本值来自原厂 `system_a:/system/build.prop`。实际 HAL 调用 `GetOsVersion()`、`GetOsPatchlevel()`，其 Native 提供方 `system/lib64/libkeymaster4.so` 读取上述两个系统属性，并进入 HAL 的 `0x48` 配置请求。AOSP `CheckPatchLevel()` 中，key 的补丁级别高于当前配置可以返回 `INVALID_KEY_BLOB (-33)`；这与当前候选相容，尚未证明就是闭源 Beanpod TA 的实际拒绝分支。

不能把此候选称为升级了 Recovery 框架；不能改 SDK、未来补丁日期、OS_VERSION=0 或安全验证来绕过密钥版本绑定。

## 2. 为什么改生成规则

锁定 Recovery 先执行 `Process_Fstab()` 内的自动 metadata 解密，之后才执行 `process_recovery_mode()` 中的通用 `TW_OVERRIDE_SYSTEM_PROPS`。仅设置该宏可能错过第一次 HAL 配置。

`patches/recovery-target-keymaster-version.patch` 修改锁定 `TeamWin/android_build@1b692e2248609f50a27c48cce53b7445cecdcfc5` 的 `core/Makefile`：五份属性文件合并为 Recovery `prop.default` 后，删除这两个键的已有定义（含可选赋值），再各写入一个准确目标值。后续 ramdisk/boot/AVB 仍走原构建流程。

锁定 init 的 `PropertyLoadBootDefaults()` 只在 `IsRecoveryMode()` 分支读取 `/prop.default`；普通 Android 从其已挂载的系统属性源初始化。原 system/vendor 等构建输入不被该补丁改写。init 随后还会读取其他属性文件，因此最终检查也拒绝 ramdisk 内已知后续属性源中的冲突值。目标系统实际挂载和运行时优先级仍需实机验收。

Native 启动器固定 `SELENE_TARGET_KEYMASTER_VERSION=1`，父环境不能关闭。新补丁与已有八份补丁全部预检查成功后才开始应用。共享构建脚本默认不启用新补丁，暂停的 Docker 路线保持原默认行为。

最终 `verify_boot.py --target-keymaster-version` 要求：

- 根 `prop.default` 是常规文件；两个目标键各有一个正确值。
- 框架 SDK 仍为 `32`，不出现冲突的 ramdisk 初始属性源。
- 原有 kernel/DTB/fstab/TEE 客户端及 AVB 验收仍执行。
- 静态报告中的 runtime configure、FBE 等字段保持未测试，不将属性检查当作解密成功。

## 3. Stock 工作流的持久提取结果

原始 ROM 备份、全部 `images/` 载荷和现有清单仍交付。新分析只读取同一 Job 已提取的本地载荷，不重新下载 super、原始 ROM 分卷或 Native 镜像。

| 附件 | 内容 | 后续使用 |
| --- | --- | --- |
| `stock-analysis.md` / `.json` | 覆盖范围、来源、分片顺序、长度、空槽及未验证项 | 先看这两个入口 |
| `stock-analysis-index.tar.gz` | 小型索引、配置、文件目录、ELF 元数据和 TEE 模块 | 优先下载，通常无需获取 Android 二进制包 |
| `stock-analysis-bundle.tar.gz` | 索引及选中的实际二进制/依赖、TA、全部 TEE 模块、boot 节段 | 比较 HAL、库、加载器和 TA 时下载 |
| `logical-<partition>.img[.partNNNN]` | 按映射重建每个实际非空逻辑分区的 raw 内容 | 单独读取目标分区，无需再展开整个 super |
| `stock-files-<partition>.tar.gz[.partNNNN]` | 该分区所有常规文件及完整目录元数据 | 直接取得遗漏的新研究文件 |
| `stock-files-boot-ramdisk.tar.gz` | boot ramdisk 所有常规文件与 cpio 元数据 | 对照 init、权限及首次启动环境 |
| `stock-files-apex-<序号>-<名称>.tar.gz` | 每个 APEX/CAPEX 的 payload 文件系统 | 获取 Bionic、VNDK 等真实提供方 |

这些派生 raw 镜像不再执行 simg2img。原始 `super.img` 附件仍保持官方 sparse 格式。所有超过 `1,900,000,000` bytes 的派生文件同样连续分片，准确合并命令来自本轮清单，不能直接使用单个分片。

Sparse 的 DONT_CARE 区间在派生 raw 中按零填充；这些文件来自原厂固件，不是手机分区读回备份。

文件归档只写安全的常规 tar entry，使用中性宿主权限。原 UID/GID/mode/inode/link count、符号链接目标及特殊节点保存在 `filesystem.json`；不会在 Runner 创建原厂链接、设备节点或恢复特权权限。归档本身不是可直接刷写的文件系统。xattrs 未解码，原始逻辑分区仍完整保留它们。

本轮真实离线导出得到 43 个派生逻辑附件、46 个附件分片，合计 `12,761,131,079` bytes；小型索引为 `5,792,873` bytes，包含二进制的分析包为 `211,744,531` bytes。保留原包、原始载荷、raw 逻辑分区和文件集合会增加发布空间与上传耗时；取舍是后续可只下载约 5.8 MB 索引或一个目标分区，无需再处理整个 super。这些是本机提取结果，不是新 Actions 已发布成功的声明。

## 4. 分析包内的索引

| 路径 | 分析结果与证据用途 |
| --- | --- |
| `boot/header.json`、`boot/*.bin` | boot v0/v1/v2 节段偏移、长度、命令行及 kernel/DTB 等载荷；不把头部字段当作系统属性替代值 |
| `inventory/*.json` | 完整目录、数值权限、链接、inode、文件大小及来源；原厂文件集合差异的依据 |
| `super/partitions.json` | sparse→liblp 映射、各主元数据槽、extent、空/非空 A/B 分区及实际文件逻辑长度预算 |
| `apex/packages.json` | 原外层路径、payload 成员、内部 package name；实际运行时挂载仍未验证 |
| `configuration/index.json` | 目标 OS/SPL 属性、全部 init service/action/import 原块及行号、fstab、VINTF HAL XML、TEE/RPMB/persist/metadata 引用 |
| `elf/dependencies.json` | ELF 位数/机器类型/interpreter/SONAME/DT_NEEDED/RPATH/RUNPATH、强/弱导入及导出符号、候选提供方、未解析边、镜像内链接别名 |
| `tee/modules.json`、`tee/modules/*` | TEE 模块表的原命令行、偏移、长度与所有模块原字节，包括安全侧启动配置 |
| `selected-files.json`、`files/<scope>/*` | 已导出的配置/实际二进制清单及按来源命名的文件 |

提取范围覆盖全部 init/VINTF/SELinux/linker 配置、属性/fstab/ueventd、`thh/ta`，以及 Keymaster、Gatekeeper、keystore、Vold、TEE/存储相关程序。所有 APEX 内的 native 库/程序也进入可复用文件包；其余常规文件仍在每个文件系统归档内。

ELF 候选按名称和 ABI 列出，TEE 与 Android 分开解析；不将 ARM32 安全侧库当作 Android 提供方。多个分区/槽/APEX 中的候选全部保留，不擅自选定实际 namespace。GNU symbol version、Android linker namespace 和运行时 ABI 兼容性不因此得到证明。没有节表的 ELF 明确标为无法从节表取得动态符号，不将空列表当作无依赖的证明。

本轮 516 个 ELF、3891 条依赖边中保留 4 条未解析边，均来自原厂 boot ramdisk 的 `wait_for_keymaster`、`vold`、`keystore2`、`gatekeeperd`，涉及 `android.security.maintenance-ndk_platform.so`、`libkeystore2_vintf_cpp.so`、`android.security.authorization-ndk_platform.so`。不能把静态未解析等同于原厂 Android 缺库，也不能通过伪造别名把计数归零；后续应结合实际 linker namespace/挂载环境核对。

## 5. TEE 模块表与未知边界

本固定 V14 的 SOTER gzip 位于 `tee.img` 的 `0x6BEC0`，展开 `4,874,240` bytes。解析的是 `0x58` 开始的 100 个 16-byte 模块记录，通过记录中的开始、结束、名称偏移确定文件，不采用“ELF 排列顺序等于名称排列顺序”的猜测。第四字段在这份固件中均为零，不能由此推断其他专有 flag 的语义。

100 个模块中有 82 个 ELF；其余配置和其他载荷也按表记录保留。该结构与 Multiboot/L4 模块记录布局相符；顶层专有字段只按本固件已观察到的边界约束使用，不声称支持所有 Beanpod/SOTER 版本。未知容器形状、非零未支持字段、越界/重叠、异常 gzip 会使提取失败。

安全侧配置中的 `sst_client` capability 不等同于 Android init service。模块存在及 `ree_agent → wait_4_reeagent → sst-server` 的静态配置不能证明设备上 SST/RPMB/persist 已健康就绪。原厂非直接 ELF TA 保留封装，不解密、不移除验证，不读取设备 TEE 安全存储。

## 6. 流程、资源和失败语义

1. 保留原下载/断点接力：优先恢复同 ROM 的已保存原包；只有没有备份标记才访问小米源。16 连接、5h30m、最多 12 轮及 1 天交接 Artifact 不变。
2. 新唯一草稿先保存原始 ROM，最后上传原包备份清单。任何后续提取失败仍可从此草稿恢复。
3. 原始载荷只提取一次。`stock_rom_formats.py` 直接跨本地分片索引 sparse/liblp，不生成完整 raw super 副本。
4. 验证所有主 liblp 槽的布局一致、必需文件存在、文件系统受支持及实际空间预算，再导出各逻辑分区和完整文件集合。不同布局不会静默使用 slot 0 代替；备份元数据不在本次解析范围。
5. 预算使用原始逻辑分区长度加所有常规文件的实际 inode 长度，不能假定文件总逻辑长度一定小于分区。另保留 APEX/选中包的有界空间和余量。
6. 原生 Python 标准库解析；不挂载镜像，不执行 ROM 内程序/脚本。当前支持 extent-backed ext4，未知特性/EROFS 等明确失败，不标记完整成功。
7. 上限：逻辑分区合计 16 GiB、其常规文件总逻辑长度 32 GiB、每个文件系统 20 万 entry、缓冲读取 128 MiB、选中包输入 2 GiB、单个 APEX 1 GiB、APEX payload/导出内容各累计 2 GiB。上限是固定固件的资源边界，不是普适固件限制。
8. 每个附件有分片长度、命名冲突、1000 附件总量和完成状态检查。小型索引和文件包都完成且附件集合正确之后，才最后原子生成 `stock-analysis.json` 完成标记。
9. 上传全部原始载荷、派生附件后才发布草稿；不覆盖已有 Release，不标 Latest，不上传编译日志、私密诊断或设备数据。

Stock 仍只由工作流自身改动触发 push/PR；新增 Stock 专属脚本在 Native 完整编译分类中排除。此提交还包含 Native 补丁，因此该次 main push 会依既有规则分别启动一次 Native 和一次 Stock；不额外 dispatch，不监测或轮询。

## 7. 验证与下一轮验收

本地验证入口（仓库根目录）：

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s tests -p 'test_stock_rom*.py' -v
bash -n scripts/build.sh
```

另执行所有 Shell/YAML/actionlint 检查；真实公开 Makefile 严格预检查、实际应用和提取出的原 recipe 执行；旧 Native Artifact 的新属性检查负对照。Stock 真实离线验收复用指定 Release 的 boot/tee/super 附件，未下载完整 ROM 分卷，不上传本地验证产物；它不代替新 Actions 的完整恢复、上传和发布验收。实际结果及初次失败修正记录见 `AUDIT.md`。

下一轮 Native 必须先完成编译、原 AVB/镜像验收及新属性验收。之后的设备测试需独立授权：确认一次全新 Recovery 启动的首次配置版本、原 metadata key BeginOperation、userdata 映射和 `/data` 挂载，再验证原凭据 CE、Gatekeeper、正常 Android 启动和再次重启。若仍为 `-33`，先核对配置实际值，再按 TA/加载闭包、APPLICATION_ID、明确的存储错误逐项研究；若变为 `-62`，先审阅原升级语义，不增加强制升级或无限重试。

不格式化 data、清 metadata、重建/复制 RPMB/persist，不禁用 FBE/Keymaster/keystore2、安全验证或 SELinux，不扩大十项私有输入和源码锁。

## 8. 一手复核入口

- [固定 V14 Stock Release](https://github.com/Grinch27/twrp_builder/releases/tag/selene-stock-V14.0.4.0.TKUCNXM-40760937942-1)
- [实际测试 Native 41374113681](https://github.com/Grinch27/twrp_builder/actions/runs/41374113681)
- [锁定 build/make Recovery 属性生成规则](https://github.com/TeamWin/android_build/blob/1b692e2248609f50a27c48cce53b7445cecdcfc5/core/Makefile)
- [锁定 init 属性加载顺序](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/init/property_service.cpp)
- [锁定 Recovery 启动顺序](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/twrp.cpp)
- [AOSP CheckPatchLevel](https://android.git.googlesource.com/platform/system/keymaster/+/refs/heads/android13-mainline-permission-release/android_keymaster/android_keymaster.cpp)
- [AOSP 版本绑定](https://source.android.com/docs/security/features/keystore/version-binding)
- [AOSP liblp 格式](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/liblp/include/liblp/metadata_format.h)
- [Linux ext4 extent](https://www.kernel.org/doc/html/latest/filesystems/ext4/ifork.html)、[inode](https://www.kernel.org/doc/html/latest/filesystems/ext4/inodes.html)、[directory](https://www.kernel.org/doc/html/latest/filesystems/ext4/directory.html)
- [Multiboot 模块记录](https://www.gnu.org/software/grub/manual/multiboot/html_node/Boot-information-format.html)、[L4Re 32-bit 模块结构](https://www.l4re.org/doc/structl4util__mb__mod__t.html)
- [GitHub Actions 工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
