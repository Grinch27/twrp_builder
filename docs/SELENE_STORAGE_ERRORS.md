# Native Recovery 存储错误处理

基线：`main@c99bfb52cdcc76568d59696d1d48982814dd2f0b`，Native [41374113681](https://github.com/Grinch27/twrp_builder/actions/runs/41374113681)。用户确认 Android 启动及再次正常重启通过，TWRP metadata 解密仍失败；本轮没有操作设备。

## 确定的源码缺陷与修正

- Recovery 的 CopyLog 忽略当前存储挂载、Recovery 文件复制和可选日志导出的失败，随后报告成功。修正使这些失败传播到操作状态，只在实际成功后显示相应的导出成功提示；不新建未挂载的 `/data/media` 来伪造持久存储。
- Vold `BeginKeymasterOp` 在 `begin()` 成功后，原本判断升级 blob 是否存在的 guard 被注释。无需升级的成功操作可能访问空 optional。修正恢复这一行 guard，不改变 Keymaster 的输入、失败返回、重试或原有临时升级写入路径；不写回、删除或重建原 metadata key。
- Native 固定启用 `SELENE_RECOVERY_FIXES=1`，调用方不能关闭。所有原有和新增补丁先全部 `git apply --check` 再应用；任一失败都停止编译。共享构建脚本未设置该值时不应用这两份新补丁，暂停的 Docker 路线不变。

## `-33` 的边界

本轮错误发生在 `keymaster.begin()`，函数在升级 guard 之前已返回失败。因此恢复 guard **没有修复本轮 `-33`**；CopyLog 修正同样不能使 `/data` 解密成功。

[Keymaster 接口](https://github.com/LineageOS/android_hardware_interfaces/blob/ae469cee0dce6d71489588126a15da8e67a50102/keymaster/4.0/types.hal)将 `-33` 定义为 `INVALID_KEY_BLOB`。锁定 Vold 的 APPLICATION_ID 来源包括 secdiscardable hash、认证 secret 和可选 binding seed；当前没有足够的同版本原厂调用环境证据来更改它们。wrapped-key 导出和 device-mapper 创建位于 key 读取成功之后，不能按本次失败码直接修改这些分支。

不改变 fstab/分区映射、FBE/AVB/SELinux、版本属性、TA/HAL/daemon、内核或私有输入白名单；不为 `-33` 新增自动升级、降级、重试或绕过。原始诊断、标识、凭据及 key blob 不进入公开源码、测试或 Actions 日志。

## 锁定公开源码

- [Recovery CopyLog](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/gui/action.cpp)
- [Recovery 日志与文件复制函数](https://github.com/TeamWin/android_bootable_recovery/blob/5c3d206a5eeb3d446bcda8248a405a4b278bab5c/twrp-functions.cpp)
- [Vold KeyStorage](https://github.com/TeamWin/android_system_vold/blob/a164ba05c5fef288059774a776b2e6e1119957cf/KeyStorage.cpp)
- [Vold MetadataCrypt](https://github.com/TeamWin/android_system_vold/blob/a164ba05c5fef288059774a776b2e6e1119957cf/MetadataCrypt.cpp)

## 验证与下一轮验收

本地测试对锁定公开函数实际打补丁并用主机 C++ 编译执行；覆盖挂载/复制/命令/写入失败、成功、未启用的可选导出、无需升级和升级失败。KeyStorage 测试比较原 metadata 合成文件集合与字节，包含未修正版本的失败负对照。构建 Shell 测试验证全部预检查早于任意应用、新补丁失败停止及 Native 环境固定值。

以上证明受测函数及编排行为，不证明 Android 完整编译、设备解密或刷写安全。下一轮须分别验证正常 Android/重启、Recovery、metadata/data 解密、凭据 CE 解密、导出文件实际存在与失败提示。提交后由现有 main push 规则验收，不额外 dispatch、轮询或自动重试；设备动作另需当次具体授权。
