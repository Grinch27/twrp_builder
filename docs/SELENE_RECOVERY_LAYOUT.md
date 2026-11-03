# Selene Recovery：mi_ext 逻辑身份与路径解析修正

适用固件：China MIUI `V14.0.4.0.TKUCNXM`。分析与修正基线：builder `92ee1b879899c61e30640a5c1f6184ce84454927`，Native [41452626126](https://github.com/Grinch27/twrp_builder/actions/runs/41452626126)，attempt 1。本报告区分用户提供的单次启动诊断、公开锁定源码证据、主机测试和仍待进行的实机验收。私人原始报告、日志、标识和归档不进入本仓库。

后续更新：41549550320 失败于公开测试资源恢复，未进入 Android 编译；新的资源失败分类、十二补丁编排及备份还原 P0 见[备份预检报告](SELENE_BACKUP_PREFLIGHT.md)。以下保留首次布局修正时的证据与验收边界。

## 1. 结论与证据边界

本轮现场已经形成 metadata 解密、用户 0 的 DE/CE 密钥安装、`/data` 的 F2FS 挂载及三份非空日志实际导出的成功链；没有复现旧 `-33`、TEE 共享内存分配失败或 Keymaster SIGSEGV。当前 `mi_ext` 告警属于 Recovery 的逻辑名推导、Android 视图行解析和嵌套路径匹配问题，不能据此认定逻辑分区缺失或 FBE 仍失败。

三项缺陷的源码根因置信度高。修正的 Android 完整编译、下一轮设备表现、跨重启解密及备份恢复均未验证。成功现场支持保留上一轮 TEE 客户端和首次 Keymaster OS/SPL 输入；它不能唯一证明闭源 TA 旧 `-33` 的内部拒绝分支。

### 资料读取与去重

用户提供的完整私密归档包含 69 个常规文件，全部读取；28 组命令资料共 6,617,464 字节，采集状态完整、无截断，命令长度与清单一致。报告后续单独上传的副本与归档内副本逐字节一致。另读取定位报告和 8 组纯函数复现记录。

当前启动的 Recovery、logcat、dmesg 按同一启动身份关联；导出的 Recovery 文件是主日志的较早前缀快照，不重新累计。logcat 与 dmesg 中重复的内核消息也不按两个事件计数。pstore/last_kmsg 缺少可靠的当前启动归属，单列为历史候选，不加入当前故障次数。命令退出 0 不自动证明其中每个可选命令或路径成功，实际导出由文件存在、非空和内容读取共同确认。

构建 Run 与源码关联来自 GitHub Run 元数据；用户将现场关联到这个镜像，本轮没有重新下载 Native Artifact 或读回手机分区建立镜像字节绑定。没有连接、挂载或操作手机，也没有读取个人密钥或安全存储。

## 2. 当前启动的事件链

| 顺序 | 进程／线程角色 | 已观察结果 | 解释 |
| --- | --- | --- | --- |
| 1 | init、Recovery 启动主线程 | 初始 release=13、SPL=2023-12-01，框架 SDK32；原 vendor SPL 保留 | 首次 Keymaster 输入已进入本轮现场 |
| 2 | Beanpod HAL 主线程；keystore2 启动与等待线程 | HAL 注册成功，keystore2 获得 HIDL 服务，等待线程随后退出 | 没有证据支持持续注册等待或 mutex 死锁 |
| 3 | Recovery metadata 解密线程 | metadata key 读取及解密均成功，userdata 建立 dm-default-key 映射 | 早先直接探测加密 userdata 的 F2FS magic 错误不能当作解密后损坏 |
| 4 | Recovery 解密工作线程 | 用户 0 的 DE、CE 密钥安装成功，解密状态成功 | 仅证明这个用户、这个启动会话 |
| 5 | Recovery 挂载及导出线程 | `/data` 从解密映射以 F2FS 挂载；导出总体成功且三份文件确实非空 | 旧的“提示导出成功但没有文件”本轮未复现 |
| 6 | Recovery 分区登记与 GUI 查询 | `mi_ext` 查错逻辑名；bind 行解析失败；六条嵌套路径重复查询失败 | 是本次补丁目标，不与已成功的解密链混为一谈 |

三个当前核心日志中，旧 `-33`、共享内存分配失败及 Fatal signal/SIGSEGV 的匹配数均为 0。它们与较早失败会话不合并。进程和线程已在私密资料中分别关联；公开报告只保留角色及必要聚合结论。

## 3. 原厂与 Recovery 差异矩阵

| 对象 | 同版本原厂／公开索引 | 修正前 Recovery | 本次处理 |
| --- | --- | --- | --- |
| 逻辑块源 | fstab 源 `mi_ext`，挂载点 `/mnt/vendor/mi_ext`，带 logical、slotselect | 从挂载点去掉首 `/`，得到 `mnt/vendor/mi_ext_a` | 保存原始块源，按 slotselect 生成 `mi_ext_a` |
| dm 存在性 | 原厂索引有非空 `mi_ext_a`；现场同名 dm 设备也存在 | 名称查错后登记失败并丢弃对象 | 成功映射后才登记 Super 成功列表 |
| 挂载后的设备名 | 原始逻辑身份与运行时 dm 路径含义不同 | `Set_Block_Device()` 覆盖主块源，后续重映射没有稳定来源 | 分开保存原始源、最后成功映射名和本对象创建的别名目标 |
| Android bind 行 | `/mnt/vendor/mi_ext /mi_ext none ro,bind wait,nofail` | `/mnt` 开头被当作 TWRP v1，`/mi_ext` 被误读为文件系统 | 在旧分词前明确识别为非块设备视图并跳过 |
| Android overlay 行 | 描述 Android 的 lowerdir 视图 | 可能被当作父对象的附加文件系统参数，并未建立完整 overlay | 明确识别并跳过；不宣称实现了 MIUI overlay |
| 长路径对象 | 六条 `/mnt/vendor/*` 挂载点 | 对象存在，但 Find/状态查询先截成 `/mnt` | 统一按完整路径及最长组件前缀匹配 |
| 短路径对象 | 四条既有 twrp.flags 对象 | 与长路径同时存在，各有原 flags | 保留；不合并、不扩充备份或擦除标志 |
| Find／Mount／UnMount | 应选中同一拥有者 | 根路径截断；别名碰撞可产生分派歧义 | 共用解析器，以选中对象分派，子分区按正式挂载点关联 |
| 日志动画 | 公共主题有 indeterminate001–012 | 加载器继续探测 013，失败后结束序列 | 正常结束探测，不补造资源、不压制相关日志 |
| FBE、TEE、系统输入 | 上轮修正后的现场已单次成功 | 与路径告警同时出现，但无失败因果链 | 保留 SDK、TEE、HAL、TA、fstab、FBE 和安全验证配置 |

本轮只复用已发布的同版本 [Stock 分析 Release](https://github.com/Grinch27/twrp_builder/releases/tag/selene-stock-V14.0.4.0.TKUCNXM-41452626083-1) 中 5,792,873 字节的 `stock-analysis-index.tar.gz`，没有重下 boot、super 或三个原 ROM 分卷。其来源仍是用户指定的固定 V14 原厂包，提取流程见[Stock 设计](SELENE_TARGET_VERSION_AND_STOCK_ANALYSIS.md)。

该索引的 `mi_ext_a` 常规文件如下；这是原厂目录事实，不是手机运行时 overlay 已正确建立的证明。

| 路径 | 字节 |
| --- | ---: |
| `etc/NOTICE.xml.gz` | 4227 |
| `etc/build.prop` | 53 |
| `etc/init/init.miui.mi_ext.rc` | 230 |
| `product/etc/permissions/privapp-permissions-product-miext.xml` | 68 |
| `system/etc/permissions/privapp-permissions-system-miext.xml` | 68 |

## 4. 源码因果链

### 4.1 挂载点不能充当逻辑块源

锁定 `Prepare_Super_Volume()` 使用 `Get_Bare_Partition_Name(Get_Mount_Point())`。后者只为 `/system_root` 特判 system，其余仅去掉首个斜杠。于是 `/mnt/vendor/mi_ext` 被转换为不存在的 `mnt/vendor/mi_ext_a`。

锁定 `fs_mgr_update_logical_partition()` 对名称调用 `GetDmDevicePathByName()`，成功后把 `FstabEntry.blk_device` 换成运行时设备路径。它不把挂载点转换为逻辑名。现场已经存在的 `mi_ext_a` 与错误查询名并不相同；原厂索引也独立确认该分区非空。因此“super 没有 mi_ext”已排除，“Recovery 登记失败”有直接代码与现场证据。

旧实现还在真正映射前就追加 `Super_Partition_List`，让界面成功列表不可靠。后续 `Set_Block_Device()` 又覆盖原始主块源；仅修正第一次查询仍不足以修复重映射、切槽后的卸载或旧别名。

### 4.2 bind／overlay 是视图，不是额外块分区

旧解析器按源字符串开头判断 Android v2 或 TWRP v1。bind 行源以 `/mnt/` 开头，落入 v1，导致文件系统位置被错误读取。overlay 行即使通过旧分词，也可能进入 `Save_FS_Flags()` 的附加条目分支；这不等于实现 mount overlay。

本次在旧分词前精确匹配 `none` + 独立 `bind` 选项 + 绝对源／目标，以及 `overlay` 源和类型 + 绝对目标。明确记录“跳过 Android 视图”，不加入普通分区，不把 `rebind` 误认为 `bind`，不放宽文件系统白名单。原厂 first-stage fstab 原字节及其 ro、AVB、logical、slotselect、挂载顺序不修改。

选择跳过的依据是：本轮 FBE 已在这两个 mi_ext 视图未挂载的情况下成功，原厂目录也未提供新的当前 FBE 失败依赖证据。本修正只纠正 Recovery 登记；若后续功能需要 MIUI 合成视图，必须独立验证 bind／overlay 的完整语义、卸载顺序及备份视角，不能声称已修复该功能。

### 4.3 长路径与别名需统一解析及分派

`Get_Root_Path()` 将嵌套路径截为第一层，不能用于查找 `/mnt/vendor/persist` 等完整挂载点。现场六个长对象均已登记；四个短对象另由 twrp.flags 增加，二者同时存在。288 条提示是六个长路径各出现 48 次；GUI 分区列表会重复调用状态查询，不是 288 次实际 mount，也不是备份损坏证据。

新解析器先规范 `/system` 到既有 Android root，匹配正式挂载点和 `Symlink_Mount_Point`，选择最长、完整路径组件边界的拥有者；长度相同时正式挂载点优先于别名。拒绝空路径、`.`／`..` 组件，不把 `/persist_extra` 误配给 `/persist`，不调用 realpath 或跟随文件系统链接。

Find 返回该对象；Mount 和 UnMount 使用同一对象指针分派，避免两个对象拥有相同文本别名时同时操作。子分区关联使用选中对象的正式挂载点。原有 `/tmp`、根路径挂载约定和 unmount flags 保留。

## 5. 最小实现与生命周期

`patches/recovery-layout-paths.patch` 仅修改锁定 Recovery 的 `partition.cpp`、`partitionmanager.cpp`、`partitions.hpp`。

| 字段／阶段 | 新约束 |
| --- | --- |
| `Logical_Partition_Source` | 在路径解析或 dm 替换前保存 fstab 源；不挪用用于加密的 `Original_Path` |
| `Logical_Partition_Name()` | 从稳定源取最后路径分量；非空、字符和长度有界；按 SlotSelect 追加当前 `_a`／`_b`；显式后缀不重复追加 |
| `Mapped_Logical_Partition` | 仅在节点可用后保存实际成功的带槽名；卸载不重新推导当前槽 |
| 节点等待 | 最多 50 次检查、49 次 100ms 等待，避免原无界循环；超时真实失败 |
| Super 列表 | 映射成功后去重追加；失败不产生成功项 |
| 重映射失败 | `Prepare_All_Super_Volumes()` 保留对象及既有身份并返回失败，不再执行 `erase(iter--)` 的无效迭代器操作 |
| by-name 别名 | 只清理／刷新本对象创建且目标仍匹配的链接；外部链接和真实节点保留；同目标不反复删除重建 |
| unmap | 检查卸载、已记录名称的 dm 销毁、同名 COW 销毁与本对象链接清理；失败不把对象删除并谎报成功 |

卸载失败不是原子回滚：若主 dm 已删除而 COW 或链接清理随后失败，对象仍保留错误上下文，但映射可能只完成了部分销毁。没有增加自动重试；真实 snapshot、fastbootd、OTA 及这类部分失败后的恢复能力仍待专项验收。主机测试只验证返回值、调用名和对象生命周期。

嵌套查找不自动放大存储写入范围。备份／还原目标、备份文件识别、镜像刷写目标、USB LUN 和 SD 卡分区目标继续经过 `Find_Partition_By_Root_Path()` 保留原先根路径边界。Wipe／Repair／Resize 原有根路径分派不改。六个长对象与四个短对象保留原 flags；本次没有让长路径直接参与此前不支持的备份恢复或刷写。这些功能仍需独立设计与实测。

Native 启动器固定 `SELENE_RECOVERY_LAYOUT_FIXES=1`，调用环境不能关闭；共享脚本及暂停的 Docker 默认 0。新补丁与原九份补丁全部预检查成功后才开始任何应用，失败立即退出；只增加两个固定公开阶段名称，不输出私有参数。Stock 工作流、本次其余源码锁、私有输入白名单和原厂二进制保持。

## 6. 假设排序与处理优先级

| 级别／假设 | 证据强度 | 范围与风险 | 处理 |
| --- | --- | --- | --- |
| P0：逻辑名来自错误挂载点 | 高；锁定源码、同名 dm 和原厂索引一致 | 影响登记、重映射和卸载身份 | 本次修正稳定源及全生命周期 |
| P0：嵌套路径被截断 | 高；源码、对象清单和重复查询吻合 | 影响查找、状态和挂载；需防别名越界 | 本次统一解析、分派并保留写入边界 |
| P1：Android bind／overlay 误登记 | 高；精确原厂行可复现 | 影响 Recovery 分区模型；完整 overlay 支持风险更大 | 本次明确跳过非块视图，不伪造完整支持 |
| 已排除：mi_ext 物理／逻辑载荷不存在 | 与现场 dm 和原厂目录矛盾 | 无需重建 super 或修改分区 | 不实施 |
| 已排除：当前 288 次真实挂载失败 | 是重复查询计数 | 压制日志不能修好模型 | 不实施日志掩盖 |
| 已排除：013 动画缺图需要补齐 | 锁定加载器正常序列结束探测 | 与 FBE、分区无关 | 不改资源 |
| 未证实：当前 TEE/Keymaster 再次阻塞解密 | 当前成功链及三份核心日志无相应旧错误 | 不应因此替换 TA、daemon 或清除安全存储 | 保留已有修正，后续观察 |
| P2：MIUI overlay 影响备份／还原内容视角 | 当前没有实测 | 可能影响导出、恢复语义，不能由目录存在推出正确性 | 另行验收，不在本次扩大能力 |
| P2：跨重启、多用户 FBE 稳定性 | 本轮只有一会话、用户 0 | 单次成功不足以外推 | 下一轮验收 |

首次原始 userdata 的 F2FS 探测、尚未解密时的用户状态、初始 super 容量暂为 0 等提示均需按后续成功事件解读。可选外置存储缺失不构成本次主阻塞证据。大量 SELinux 信息也不能只按数量认定致命；没有新的相关拒绝与当前失败链支持本次修改策略。

## 7. 主机验证

| 检查 | 结果与边界 |
| --- | --- |
| 标准库全套 | 240 项完成，236 通过、4 项既有环境限制跳过 |
| 新布局行为集 | 12 项通过；编译并执行补丁中的实际函数，虚拟文件系统／dm 回调，不进行真实 mount 或设备写入 |
| C++ 构建 | g++，C++17、`-Wall -Wextra -Werror`；AB／非 AB 两套 harness，含槽名测试 |
| 行为覆盖 | 六长／四短路径、最长边界、别名碰撞、system／sdcard、子分区、挂载及卸载、空路径／遍历拒绝、稳定源、显式槽、反复映射、超时／失败、活动槽变化后按记录卸载、外部节点保护、COW 失败、首对象重映射失败、bind／overlay 分类 |
| 构建编排 | 十项预检查在全部应用前；新预检失败时没有任何 patch apply；Native 固定 flag，默认共享路线不启用 |
| 锁定公开源码 | 四份 Recovery 补丁严格空白预检查、组合应用及 diff 空白通过；11 个受测函数与组合后的实际源码一致 |
| 静态检查 | 三份 YAML、4 份 Shell 文件、38 段内联 Shell 语法、actionlint 1.7.7 通过 |

四项跳过分别是两个执行器 `/proc` 命名空间限制、Go 缺失、aria2 缺失；没有新增跳过、禁用测试或缺依赖绕过。没有进行完整 Android 编译，不把 host harness 的简化 FstabEntry／dm 回调当作 Android 头文件、链接或内核行为证明。

## 8. 下一轮验收条件

1. Native 正常完成十项补丁预检查、完整 Android 编译及全部既有 boot 验收，仍仅交付 `boot.img`、保留三天、`publish=false`。不能仅凭本报告将新候选认定为可用。
2. 在另获授权的设备验收中，Recovery 正式登记 `/mnt/vendor/mi_ext`，逻辑名是实际槽对应的 `mi_ext_a`／`mi_ext_b`，不再出现含 `mnt/vendor/` 的逻辑查询名；成功列表与实际成功对象一致。
3. 六个长路径的 Find／状态查询／Mount／UnMount 选中同一对象；短路径和原 flags 保留；组件边界、system 和存储别名没有回归。分区页重复查询不再产生这六条无法找到分区提示，不能以全局关闭日志代替验收。
4. bind／overlay 行明确记录为跳过，不能再报 `/mi_ext` 为未知文件系统；不将缺少 `/mi_ext` 合成视图标成已实现功能。
5. 原有 metadata、用户 0 DE/CE、F2FS `/data` 及三份非空导出全部继续通过，Keymaster／keystore2 不出现旧分配失败、崩溃或 `-33`。跨重启和其他用户分别记录，不能累计旧日志充数。
6. 正常 Android 启动选择保持。备份恢复、OTA/snapshot、fastbootd、切槽后的真实 unmap/remap 及 MIUI overlay 内容视角单列未验收；任何相关写入／重启仍需具体设备授权，本次不自动执行。

## 9. 公开源码与复核入口

- [锁定 Recovery partitionmanager.cpp](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/partitionmanager.cpp)：原逻辑名、Find／Mount／UnMount、Prepare／Unmap 与存储操作调用点。
- [锁定 Recovery partition.cpp](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/partition.cpp)：fstab 格式判别、附加文件系统行与原块源处理。
- [锁定 Get_Root_Path／Set_Block_Device 等辅助源码](https://github.com/TeamWin/android_bootable_recovery/tree/5c3d206a5eeb3d446bcda8248a405a4b278bab5c)：twrp-functions.cpp、partition.cpp、partitions.hpp。
- [锁定 fs_mgr.cpp](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/fs_mgr/fs_mgr.cpp)：`fs_mgr_update_logical_partition()` 按块源名查 dm，并替换为运行时设备路径。
- [AOSP 动态分区说明](https://source.android.com/docs/core/ota/dynamic_partitions/implement)：fstab 的逻辑源名、logical／slotselect 与 first-stage 语义；该通用文档不是 MIUI 专有 overlay 的实现证明。
- [本次补丁](../patches/recovery-layout-paths.patch)、[实际函数行为测试](../tests/test_recovery_layout.py)、[先前存储错误修正](SELENE_STORAGE_ERRORS.md)、[先前 TEE 客户端证据](../public-prebuilts/selene-stock-v14/README.md)。

当前最大不确定性：备份恢复、MIUI overlay 内容视角和跨重启 FBE 稳定性尚未实测。

用户可能遗漏：本次明确跳过 Android 合成视图，并不等于 Recovery 已支持完整 MIUI overlay；单次解密成功也不证明还原安全。

Q1：源码原因和主机修正已有证据。Q2：新候选仍须完整 Native 与设备验收。Q3：本次仅交付 main 修正，不连接手机、不额外 dispatch 或监测新构建。
