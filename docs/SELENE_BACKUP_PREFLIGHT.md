# Selene：41549550320 构建诊断与备份还原预检

日期：2026-11-03（Asia/Shanghai）。实施基线：`95e4f8def46f24aff270a6e671d5c51037d92156`。适用：China MIUI V14.0.4.0.TKUCNXM、Native、锁定 Recovery 12.1。本轮由用户明确授权分析失败 Run、继续修正并 commit main；随后补充 Chat 分析报告，按当前源码重新核验。报告中的其他会话操作记录不自动扩展本轮设备权限。

## 1. 已确认的失败范围

[Native 41549550320](https://github.com/Grinch27/twrp_builder/actions/runs/41549550320) attempt 1，对应上述基线，2026-11-03 07:59:35 北京时间开始，最终 failure。runner-image 的测试、语法及公开同步 smoke 成功；Native Job `125633628686` 在 `public_resources` 退出 1，镜像上传跳过。

[受限诊断](https://github.com/Grinch27/twrp_builder/blob/build-progress/runs/41549550320.json) 与固定命令标记一致：repo sync、checkout 校验已完成，最后命令是 `restore_public_testdata.py`；尚未进入补丁预检或 Android 编译。不能将这次失败解释为布局补丁 C++ 编译错误。失败时磁盘约 38 GiB，未达到外层六分钟超时；这些数字不能唯一确定异常原因。

原脚本把具体异常留在 Runner 私有日志，公开记录只有阶段和退出码。因此历史异常到底是 HTTP、内容、路径冲突或 I/O，仍未确认。没有下载或公开私有日志，没有凭空指定 HTTP 状态。旧逻辑的本地完整复现成功恢复 26 个锁定资源；新逻辑的完整 CLI 也退出 0，生成正常资源模块与 SUCCESS 分类。这证明测试时原源可用，不能倒推失败当时的网络状况。

## 2. 资源恢复的最小修正

| 部分 | 行为 |
| --- | --- |
| 来源 | 保留唯一已锁定的 AOSP Gitiles revision、26 个文件及原有身份验证，不增加未经确认的镜像站 |
| 网络 | 四个并发读取者；每文件最多三次；1s、2s 退避；单请求最多 20s；共享 240s 时间预算，外层六分钟保持 |
| 可重试 | HTTP 408/429/500/502/503/504、连接中断及超时 |
| 直接失败 | 404 等确定性 HTTP 错误、重定向、TLS 证书／协议错误、非法载荷、身份不符、目标冲突 |
| 成品条件 | 下载全部验证后才开始写入，最后创建 Android.bp；保留 new-only 写入及真实失败退出 |
| 公开诊断 | 仅锁定 revision、固定错误枚举、HTTP 数字和尝试次数，写入受限进度及 Summary |
| 隐私 | 不公开异常全文、URL、路径、响应体、凭据或源文件；无效或不匹配的诊断不发布 |

这项变更改善可恢复性及可观测性，没有声称历史失败的确切根因已经证明。部分写入仍可能留下不完整临时目录；不生成空占位模块，也不自动删除冲突目录继续构建。

## 3. 对补充 Chat 报告的逐项复核

| 报告观点 | 独立核验 | 本轮处理 |
| --- | --- | --- |
| 失败在 public_resources | Run、受限 JSON 与公开固定标记一致 | 采纳；不推翻此前单次 FBE 成功 |
| Digest 条件可能反向 | 变量名含 skip，但 portrait/watch 界面明确写“Enable Digest Verification”；`>0` 与界面一致 | 不翻转条件、不更改默认值；用组合源码证据约束语义 |
| 子分区校验误用父归档 | 锁定 Run_Restore 的子循环复用父 Full_Filename | 修正为每个子分区实际 Backup_FileName |
| 已有目录提前返回 | mkdir EEXIST 后原返回 1，跳过策略和 xattr | 校验真实目录类型及既有／继承策略；拒绝符号链接占位 |
| 空间无符号减法 | 先减 32MiB，低空间时可能下溢 | 先比较保留空间，再进行减法 |
| metadata 使用 md_udc | 固定 V14 原厂 fstab 与现有成功解密一致 | 保留；不改为其他分区号 |
| PBRP 的远未来版本输入 | 当前公开 BoardConfig 确有 2127-12-31 和 99.87.36 | 仅作反例，不替换当前原厂 OS/SPL 方案 |
| Qin F25 Pro 借鉴价值 | README 自述往返通过，BoardConfig 请求 policy v2；vendor_boot 与 software Keymaster 路线不同 | 仅参考方法；维护者自述不能代替 selene 验收 |
| 独立只读 MIUI 视图 | 原厂 19 条 fstab overlay 及 pangu 内容证据成立 | 保留后续设计，本轮不激活新视图或改备份语义 |

读取的参考：[PBRP selene BoardConfig](https://github.com/PitchBlackRecoveryProject/android_device_xiaomi_selene-pbrp/blob/android-12.1/BoardConfig.mk)、[Qin 配置](https://github.com/xerootg/device_qin_F25Pro-TWRP/blob/TWRP/BoardConfig.mk)、[Qin README](https://github.com/xerootg/device_qin_F25Pro-TWRP/blob/TWRP/README.md)。这些是读取时的公开参考，不进入源码锁，不复制其镜像、版本、TEE、安全绕过或槽位策略。

## 4. P0：完整目标清单及归档预检

布局补丁保留原先根路径写入边界，新增操作局部 selection map：一次读取用户清单，全部解析成功后使用同一组对象执行。不能把查询支持扩展误认为嵌套分区备份已全面支持。

预检在存储准备、备份目录创建和任何还原 Wipe 前完成目标检查：

- 拒绝空／不完整清单、无法解析或非分区子路径、不支持的方法、不可用块节点、备份禁用目标和只读还原目标。
- 按对象和内核块设备身份拒绝重复选择；android_secure 保留其既有独立文件子树语义。隐式子分区同样验证，不跳过缺失必需项。
- FBE Data 要求已解密且用户清单有用户 0，所有列出用户均已解密；不再把未解密用户的跳过提示当作完整 Data 备份。
- 还原时，全部父／子分区的归档入口必须存在、非空、类型受支持；符号链接归档入口拒绝。保留已有 `.win000` 分卷入口格式。
- 子分区使用已识别并预检过的真实归档名，不再按当前文件系统重造名字，也不以父归档替代其校验。

文件级归档另作只读流预检：复用现有压缩、加密和分卷读取路径，读取头及文件载荷、解析策略引用并比较当前可查询的目标策略；不创建目标文件、目录或设置策略。任何一份预检失败，整组还原都不会进入清理。归档路径按所选分区边界检查，拒绝 `.`／`..` 等越界路径。

完整读取归档会增加一次 I/O；启用既有 Digest 时该检查仍单独执行。本轮没有新增 SHA256 扫描或改变 Digest 默认／用户开关。原始镜像仍保留既有独立方法，不能把文件级 tar 预检宣传为全部镜像恢复能力验证。

## 5. P0：策略、二进制扩展头与真实错误传播

### 策略分类

| 情况 | 处理 |
| --- | --- |
| ENODATA | 合法无策略目录，包括 FBE 中未加密的父容器；允许 |
| ENOTTY / EOPNOTSUPP | 普通非 FBE 归档可接受不支持查询；必需的 FBE Data 归档失败 |
| EACCES / EINVAL / EOVERFLOW 等 | 不等价于“没有策略”；失败 |
| 实际有 policy，但引用无法解析 | 备份／预检失败，不丢弃记录继续 |
| 既有／继承策略与预期一致 | 接受，不重复设置 |
| 既有策略冲突 | 失败，不强制覆盖 |
| 新目录设置策略 | 只在实际无策略时设置，并读回比较；失败真实返回 |
| 归档缺策略但当前目标已加密 | 失败，不将加密目录内容按无策略还原 |

锁定 Vold helper 的失败 errno 原可能受日志或 close 影响；新补丁保存 syscall errno 后再清理，保留原布尔 API、v1/v2 查询选择及协议。没有更换 Keymaster、密钥、算法或安全存储。合法无策略与查询失败的区分因此具备稳定依据。

### 新确认的扩展头缺陷

原 libtar 对含二进制 policy／capabilities 的扩展头使用 strlen/strstr，NUL 会截断扫描；policy 分支还在读入版本前使用未初始化 union，可能产生错误长度或空指针。新实现按现有 PAX 记录长度逐项解析：先确认版本及结构长度，拒绝截断、畸形、重复策略／标签等记录，然后复制数据。合法 v1/v2 的原归档编码不改变；NUL 后的 capabilities 也能继续读取。

备份不再遇 ENOKEY 就跳过文件并返回成功；实际文件读取失败沿原 writer 传播。已有目录不再跳过策略处理；SELinux／capabilities 的实际恢复失败会返回失败。必要元数据获取失败也不会静默丢弃。

操作失败可能留下部分已经写入的文件。这里的“成功判断修正”不是事务、原子回滚或全机恢复保证；不增加自动重试写入，不把中途失败显示为整体成功。取消及真实写入中断的完整设备行为仍待专项验收。

## 6. 补丁与构建关系

| 文件 | 内容 |
| --- | --- |
| `patches/recovery-layout-paths.patch` | 保留原布局修正；新增清单／归档预检、固定对象选择、子归档名与空间保护 |
| `patches/recovery-backup-integrity.patch` | libtar 元数据及只读流预检、Tar 前端模式传递、Partition 的预检入口 |
| `patches/vold-fscrypt-policy-errno.patch` | fscrypt 查询／设置错误 errno 保留；原 C API 不变 |
| `scripts/restore_public_testdata.py` / `report_progress.py` | 有界重试与受限资源错误分类 |
| `tests/host_libtar_integration.py` | 完整公开 libtar 的可重复主机归档往返测试，无设备或网络操作 |

Native 的既有 `SELENE_RECOVERY_LAYOUT_FIXES=1` 同时供给本组依赖补丁，不设置可以产生半套实现的新开关。全部十二项补丁预检查成功后才开始任何应用；默认共享脚本／暂停的 Docker 不启用。随后增加三分钟有界的公开 libtar 主机检查，失败则不进入 Android 编译。原厂 TEE 客户端、首次 OS/SPL、SDK32、FBE、fstab、TA/HAL、AVB、源码锁、615 项与十项私有输入保持。

## 7. 实际验证结果

| 验证 | 结果及边界 |
| --- | --- |
| 标准库全套 | 260 项完成，256 通过、4 项既有环境限制跳过；没有新增跳过或绕过 |
| 目标计划 | 实际 C++ 预检函数覆盖目标缺失、重复对象／块设备、长路径边界、只读／禁用目标、未解密用户、隐式子分区、归档入口及失败回调；源码顺序检查清理前预检和固定 selection |
| 元数据 | 实际 C 函数覆盖 v1/v2 二进制头、合法无策略、查询失败、缺密钥、既有／冲突策略、设置／读回失败、标签／capabilities 失败、符号链接目录与 ENOKEY 内容错误 |
| errno | 实际 Vold C++ helper，在故意破坏 errno 的日志／close 回调后仍保留原始错误；新旧查询分支均覆盖 |
| 完整 libtar | 全部 15 个 C 源文件主机编译；真实临时文件二进制内容、UID/GID、权限往返通过；安全接口使用模拟回调 |
| 编码兼容 | 原锁定 writer 与新 writer，v1/v2 合成归档逐字节一致 |
| 清理前失败 | 实际截断文件载荷由流预检拒绝，目标目录保持未创建内容 |
| 补丁 | 五份 Recovery 严格空白独立预检查及组合应用通过；十个候选源文件一致；Vold 新 helper 补丁在原锁定文件应用一致 |
| 资源恢复 | 原逻辑与新 CLI 均完整恢复 26 个真实锁定资源；新 CLI 输出 SUCCESS；合成重试／确定性失败／隐私过滤测试通过 |
| 静态 | 三份 YAML、四份独立和 38 段内联 Shell 语法、actionlint 1.7.7 通过；patch 上下文空白与真实新增源码分别检查 |

四项环境跳过仍为两个 `/proc` 命名空间限制、Go 和 aria2 缺失。主机 C/C++ 函数测试使用严格警告检查；完整 C 库使用 host 兼容头，不代表 Android 头文件／链接已验收。没有完整 Android 编译或新镜像／设备结果。

可重复验证：

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/build.sh
python3 tests/host_libtar_integration.py --source /absolute/path/to/patched/bootable/recovery
```

最后一项需锁定公开 Recovery `5c3d206a5eeb3d446bcda8248a405a4b278bab5c`，依次预检查后应用 required-modules、startup-diagnostics、copylog-errors、layout-paths、backup-integrity 五份补丁；仅在临时目录生成 host shim 和合成归档。脚本不下载源码、不挂载镜像、不连接手机。Native 将在补丁应用后自动执行同一检查。

## 8. 未验证与下一步

P1：在新候选完整 Native 编译及既有 boot 验收通过后，另获设备授权，再逐次记录 Android 解锁后进入 Recovery、Recovery→Recovery、完整关机直入 Recovery、Recovery→Android→Recovery 四类会话。每会话独立关联 HAL、metadata、dm／挂载、用户 DE／CE 及经授权测试文件读取，不累计旧快照，不改凭据或已成功的 TEE 环境。

P2：MIUI bind／overlay 继续明确跳过；19 条只读 fstab 行与 pangu 层需要独立视图模型、依赖、重复挂载检测和逆序卸载。只有具体消费者确有需要时才增加只读视图，不把合并目录还原进某个底层分区，不启用 upperdir/workdir 或可写 overlay。

仍需明确的限制：

- 预检不能冻结介质或保证后续写入成功，备份／还原不是事务。
- 没有完整期望分卷清单的历史归档，某些整卷缺失未必能仅凭剩余卷发现；不声称已提供完整缺卷证明。新增版本化清单需独立兼容设计。
- 未经证明的历史缺 policy 归档不会被自动“补齐”或升级；恢复兼容性需逐案测试。
- Data 备份仍不包含常规内部存储 media；导出的备份是否加密与手机 FBE 是不同条件。
- host 安全回调不能证明 selene 的硬件密钥、SELinux、跨重启或应用 Keystore 在真实还原后可用。
- 可复用的原厂固件不等于设备当前数据／安全状态备份，不能因此保证任意回退可解密。

## 9. 授权与交付边界

本轮 main 提交及既有 push 自动 Native 已获当前明确授权。只更新公开 builder，保留所有正常退出和交付检查；不新建分支／PR、不强推、不手动 dispatch 或监测新运行、不修改 Stock/Docker 工作流，不发布镜像或私密资料。

设备重启／新解密测试属于后续独立授权；生产 userdata 的正式还原为 HIGH 风险，应先有独立备份和可恢复的测试环境，再明确批准具体目标。没有执行刷写、重启、切槽、格式化、清除凭据或访问安全存储。

当前最大不确定性：新候选的 Android 完整编译，以及真实还原后的 fscrypt／应用密钥／安全状态一致性。

用户可能遗漏：既有合法归档编码兼容，不等于任意历史归档都完整可恢复；只读预检也不提供事务回滚。

Q1：本轮修正资源恢复及备份还原 P0。Q2：跨重启 FBE 仍待新镜像和独立设备验收。Q3：MIUI 合成视图保持后置，不扩大当前备份写入范围。
