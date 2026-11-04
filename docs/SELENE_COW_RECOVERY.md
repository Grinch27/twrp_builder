# selene Recovery COW 节点等待与 LOS20 故障恢复

日期：2026-11-04。范围：Native Recovery 的最小源码修正、离线证据结论及人工恢复入口。原始私密报告、日志、设备标识、凭据和 TEE 数据不进入本仓库。

## 1. 已确认事实与未验证项

| 类别 | 结论及边界 |
| --- | --- |
| 安装失败链 | LOS20 sideload 的 COW 分配后，product 的 partition-only COW、system 的 mixed COW 初始化继续；第一个 file-only COW 为 system_ext。其 DM 创建成功，紧接着打开对应 dm 节点返回 ENOENT，零填充及快照创建失败。 |
| 安装终态 | Recovery 安装器明确进入覆盖回退，目标 B 写入校验通过、最终 RC=0。安装成功不证明保留了原 A 系统，也不证明新 B 可以启动。 |
| 原 A 状态 | 前后 super 元数据表明，新 B 的四个逻辑分区共 3,999,805,440 bytes（约 3.73 GiB），物理范围全部处于旧 product_a 范围。仅回刷原 boot_a 不恢复该系统。 |
| 启动失败后 | 已取证状态为 B 尝试次数耗尽、不可启动；A Recovery 可再次进入并完成用户 0 解密。现有记录的 snapshot merge 状态为 NONE。次数耗尽不能换算成相同数量的内核启动。 |
| AVB | 已取证 B 顶层 vbmeta flags=3；A 仍有 stock 校验元数据，后续 A Recovery 记录 veritymode=eio。该状态不能唯一解释 B 最初失败。 |
| 源码缺口 | 锁定源码的 Recovery file-only 映射路径使用零超时，没有保证 ueventd 已建立节点；消费方随后直接打开路径。该缺口可在主机负对照复现。 |
| 置信度 | 对“源码缺少必要的消费前屏障”置信度高；对它解释本次 COW ENOENT 的判断为强候选，实机时序仍待验证。它不是已证明的 B 首次启动根因。 |
| 未取得 | 实际刷入的 LOS ZIP、完整 B boot ramdisk/kernel 与可唯一绑定 B 首次失败的故障轨迹尚未取得，ROM／固件兼容和新系统 FBE 未验证。 |

## 2. 锁定源码证据

基准：`TeamWin/android_system_core@ac4f36c7eb076ea2c582061a21dfc49eaa71e623`。不换分支、不修改 source.lock。

1. [snapshot.cpp](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/fs_mgr/libsnapshot/snapshot.cpp)：`MapCowImage()` 的 Recovery／FirstStageInit 分支调用 `MapImageWithDeviceMapper()`；`MapCowDevices()` 的 file-only 分支直接返回 image 映射名，mixed 分支另建组合映射。`InitializeUpdateSnapshots()` 取得路径后立即初始化压缩或非压缩 COW。
2. [image_manager.cpp](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/fs_mgr/libfiemap/image_manager.cpp)：`MapImageWithDeviceMapper()` 给 `MapWithDmLinear()` 传递空超时，继续传至逻辑分区及 DM 创建。`GetMappedImageDevice()` 可从内核 DM 状态获得路径，不证明用户空间节点已经出现。
3. [fs_mgr_dm_linear.cpp](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/fs_mgr/fs_mgr_dm_linear.cpp) 和 [dm.cpp](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/fs_mgr/libdm/dm.cpp)：超时为零的 `WaitForDevice()` 不等待文件。新建映射具有独立 UUID；该函数本来就以 UUID 路径判断新映射就绪，再允许使用 dm-N。
4. [dm.h](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/fs_mgr/libdm/include/libdm/dm.h)：明确提示 dm-N 可复用，仅等待此名字可能误认尚未删除的旧节点。
5. [init/devices.cpp](https://github.com/TeamWin/android_system_core/blob/ac4f36c7eb076ea2c582061a21dfc49eaa71e623/init/devices.cpp)：ueventd 建立 `/dev/block/mapper/by-uuid/<uuid>` 链接。其语义与 `GetDeviceUniquePath()` 一致。此候选针对 selene 的 A/B／SDK32 Recovery，不增加旧版 non-A/B ueventd 兼容回退。
6. [AOSP update_engine 覆盖回退](https://android.googlesource.com/platform/system/update_engine/+/132ef1cadb2c6c45ee630f921657ce0172d04a5e/aosp/dynamic_partition_control_android.cc)：Recovery 的 snapshot 准备失败可进入 overwrite 路径；这与本次安装日志相符。该上游源码提供机制依据，不代表已取得实际 LOS ZIP 的完整源码身份。

这里的 ENOENT 是打开 COW 节点失败；不能改写为 userdata 空间不足、TEE 内存不足或 Keymaster 故障。已有 FBE 成功会话也不能用于证明 LOS 可启动。

## 3. 最小修正与保留的限制

新增 `patches/recovery-cow-device-ready.patch`，只在一个生产函数 `SnapshotManager::InitializeUpdateSnapshots()` 内插入 13 行：

- 保留原映射与路径查询；仅在 `IsRecovery() && !IsFirstStageInit()` 时取得本次映射的 UUID 路径。
- 对 UUID 路径调用现有 `android::fs_mgr::WaitForFile(..., 10s)`，成功后按原路径打开 COW；压缩 CowWriter 和非压缩零填充共用该屏障。
- UUID 查询或等待失败立即返回 Error，不调用消费方；现有 `AutoDeviceList` 析构继续负责清理。屏障不额外删除 DM，避免与已有清理所有权冲突。清理失败不保证资源已释放。
- 十秒为单个 COW 上限，多分区总时间可累积；已就绪节点立即通过。FirstStageInit 保留原非阻塞／uevent 回调契约，普通 Android 更新路径不增加等待。
- 不全局改变 ImageManager 的零超时契约，不修改 TEE／Keymaster／keystore2、初始 OS/SPL、SDK32、FBE、fstab、AVB、SELinux、正常 boot 选择或原厂二进制。

Native 通过既有固定 `SELENE_RECOVERY_LAYOUT_FIXES=1` 启用此补丁；共享脚本／Docker 默认关闭。十三项补丁全部先 `apply --check`，任何失败均不进入应用。只新增两个固定公开阶段名，不扩展日志上传。

**保留的风险：**此修正没有取消安装器的 overwrite fallback。若空间、映射或其他快照初始化仍失败，安装器仍可能覆盖旧槽内容。不能据此承诺下一次 sideload 可安全保留 A 回退；改变该策略需要单独验证实际安装器源码和失败语义。

## 4. 验证方法与验收边界

永久测试：

```bash
python3 -m unittest discover -s tests -p 'test_cow_readiness.py' -v
python3 -m unittest discover -s tests -p 'test_startup_diagnostics.py' -v
python3 -m unittest discover -s tests -v
```

`test_cow_readiness.py` 从实际补丁提取完整修改前／后函数，以 C++17、`-Wall -Wextra -Werror` 编译。主机真实临时文件验证打开和写入；DM、uevent、CowWriter 及清理接口为受控回调，无真实块设备访问。

| 验证 | 判据 |
| --- | --- |
| 旧版负对照 | 相同 file-only 节点延迟场景：旧函数 ENOENT 失败，新函数等待后成功。 |
| 节点复用 | 旧 canonical 路径存在仍等待新的 UUID；消费方只在新节点出现后执行。 |
| 各 COW 类型 | partition-only、mixed、file-only 及已就绪节点均保持成功；压缩／非压缩都经过屏障。 |
| 有界与失败 | 回调核实十秒参数；超时、UUID 查询、映射、路径、原 unmap、消费方、CowWriter 初始化／完成失败均真实返回失败。 |
| 生命周期 | 等待失败触发现有清理，部分映射失败同样清理；注入清理失败不能使操作变成功，不声称原子回滚。 |
| 正常启动 | 普通 Android、FirstStageInit、同时声明 Recovery／FirstStageInit 均不新增等待。 |
| 构建编排 | 统一十三项检查先于任何补丁应用；新增检查失败时无应用动作。 |

提交前还在完整锁定 snapshot.cpp 上严格预检查、实际应用并逐字节比对候选；确认与既有 core task-profiles 补丁修改的文件不相交。标准库测试、三份 YAML、独立／内联 Shell 语法和 actionlint 作为提交前检查，实际结果记入 AUDIT.md。

本次实际结果：12 项 COW 定向行为测试通过；标准库共 286 项，282 通过、4 项既有环境限制跳过（两个进程命名空间、Go、aria2）。完整锁定 snapshot.cpp 的严格空白预检查、应用、反向检查及候选／受测函数逐字节比对通过；三份 YAML、四份独立及 38 段内联 Shell 语法、actionlint 1.7.7 通过。

主机测试不模拟真实 uevent 投递时延、内核 DM 或硬件安全环境；完整 Android 编译、新镜像实机 sideload 及跨重启解密均未在本轮执行。后续安装验收必须同时核对快照创建结果、是否发生 overwrite、实际逻辑分区范围、目标首次启动及解密，不能只看安装 RC=0。

## 5. device corrupt 的恢复入口

本节是待人工核对的步骤，未执行手机操作。当前屏幕描述无法替代实时槽位、解锁及分区读取。默认保留个人数据。

[AOSP boot flow](https://source.android.com/docs/security/features/verifiedboot/boot-flow) 将 `eio` 对应到 dm-verity corruption 警告，参考界面可按电源继续；OEM 实现和实际状态需现场核实。消除或跳过警告不恢复已经损坏的系统。

1. 保持 USB 连接，按音量下＋电源进入 Bootloader Fastboot，松开按键。不要重复尝试启动已失败的系统。
2. 在持有镜像的 Ubuntu USB 主机逐条只读核对：

```bash
fastboot devices
fastboot getvar product
fastboot getvar current-slot
fastboot getvar is-userspace
fastboot getvar unlocked
stat -c '%n | %s bytes' /home/user/github/aosp-builder/tmp/test/boot.img
```

预期：仅一个设备、`product=selene`、`is-userspace=no`、`unlocked=yes`。上次取证槽位为 a；若现状不同、镜像缺失或身份无法确认，停止并先保存实际输出。该路径在上次取证时指向成功临时启动过的 67,108,864-byte TWRP；**必须确认文件仍是那份已验证镜像，没有被本次新候选替换。大小相同不足以确认身份。**

3. 确认后，只临时启动该已验证镜像一次：

```bash
fastboot boot /home/user/github/aosp-builder/tmp/test/boot.img
```

命令返回 USB 状态读取错误时，不立即重发。上次曾在传输完成后因断连返回错误，但实际进入 Recovery；必须结合屏幕及 `adb devices`、Recovery 启动日志确认。此步骤只恢复取证／备份入口，不代表正常系统已恢复。

4. 进入 Recovery 后先复制必须保留的个人数据到电脑，并实际检查备份可读。已有日志包不是个人数据备份，Data 备份也不能默认包含 `/data/media`。不要 Wipe、Restore、切槽、强制 snapshot merge、运行 copy-partitions 或重锁 Bootloader。

## 6. 恢复可启动系统的后续决策

| 目标 | 必要输入与停止条件 |
| --- | --- |
| 保留数据后恢复匹配原厂系统 | 复用 [V14.0.4.0.TKUCNXM 原厂 Release](https://github.com/Grinch27/twrp_builder/releases/tag/selene-stock-V14.0.4.0.TKUCNXM-40760937942-1) 的现有附件，先核对当前 super 布局、槽位和对应 boot／DTBO／AVB／固件的一致性，形成逐分区写入及失败停止计划。旧 product_a 已被覆盖，单独 boot_a 回写不够。完整系统写回也不保证现有 FBE 数据与安全状态兼容。 |
| 继续修复当前 LOS20 | 先取得实际刷入的 ZIP 和完整 B boot，分析 ramdisk/fstab、AVB 请求链及固件兼容，补足唯一绑定 B 的失败轨迹。不能用同名下载替代实际包，不能假定本次 COW 修正解决已发生的 B 启动失败。 |

**设备写入 Approval Gate：HIGH。**批准前须完成可读个人数据备份、展示精确镜像来源／分区／槽位和数据保留边界、说明失败后的可用入口，并明确批准该计划。当前 main 提交授权不包含手机刷写、切槽、格式化、还原或修改校验。本轮停在代码提交及恢复建议，不执行手机操作。

不使用空 vbmeta、`--disable-verity`／`--disable-verification`、擦除 metadata/userdata 或 flash_all/lock 脚本作为通用补救。B 已有 flags=3 仍失败，进一步关闭校验既无充分根因证据，也违背本项目保留安全验证与 FBE 的约束。
