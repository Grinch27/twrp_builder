# Selene V14 原厂 TEE 客户端

`libTEECommon.so` 是同版本原厂 `vendor_a:/lib64/libTEECommon.so` 的原字节副本，23,696 字节，ELF64 little-endian AArch64 shared object。它只作为 Native 构建中的公开固件输入，不是新增私有归档输入。

- 来源：[本仓库原厂 Release](https://github.com/Grinch27/twrp_builder/releases/tag/selene-stock-V14.0.4.0.TKUCNXM-40760937942-1)。使用其中五个 `super.img.part0001` 至 `super.img.part0005`，按编号拼接至新的临时文件；无需下载原始 ROM 三个归档分卷。
- 官方包：[China V14.0.4.0.TKUCNXM Fastboot ROM](https://bigota.d.miui.com/V14.0.4.0.TKUCNXM/selene_images_V14.0.4.0.TKUCNXM_20231228.0000.00_13.0_cn_cfe62df805.tgz)。
- 提取路径：只读解析 sparse super 和 liblp，将 `vendor_a` 导出至独立临时镜像，再用 `debugfs -R 'dump /lib64/libTEECommon.so <新文件>' vendor_a.img` 读取。不得对原镜像使用可写挂载或 `debugfs -w`。

## 修复依据

锁定设备树 `hasan6034/recovery_device_xiaomi_selene@c77512445ab5be5908ddb3ca9c659e6b149c78de` 的旧库也为 23,696 字节，但协议实现不同。旧 `Common::TEEC_AllocateSharedMemory` 位于 `0x2960`，在 `0x29c4` 调用 `ioctl(contextFd, 0xC010A401, ...)`。V14 原厂 `/dev/isee_tee*` 的请求分派拒绝该请求；旧库把负值统一转换成 `0xFFFF000C`，不能据此认定物理内存耗尽。HAL 分配失败后继续使用空缓冲区，构成崩溃路径。

原厂库对应函数位于 `0x2900`：先在 `0x295c` 调用 `mmap(..., MAP_SHARED, contextFd, 0)`，再以 `0x8010A40D` 查询共享内存 ID，与实际 V14 isee 驱动匹配。两库的五项 `DT_NEEDED`、动态导入和导出集合一致；现有 Native 依赖闭包能提供强导入。这里记录的是静态机制及 ABI 名称相容性，不能替代运行时验证。

## 构建与验收边界

Native 启动器固定 `SELENE_STOCK_TEE_CLIENT=1`。`build.sh` 在 checkout 验证及既有 overlay 之后覆盖 `device/xiaomi/selene/recovery/root/vendor/lib64/libTEECommon.so`，再沿用原有编译流程。最终 `verify_boot.py --tee-common` 从实际 boot ramdisk 逐字节比较该库，拒绝旧的同大小文件、缺失文件和符号链接。暂停的 Docker 默认路线不启用覆盖；该二进制路径单独变更会触发 Native 构建，本文档单独变更不会。

首轮只替换这个共享客户端。它也影响 Gatekeeper 等 TEEC 消费者；TA、daemon、HAL、VINTF、内核、DTB、fstab 和 FBE 开关保持既有输入。新构建仍须通过原有静态验收；启动、Keymaster/Gatekeeper 注册、keystore2 服务和原有凭据的完整 FBE 解密均待后续明确授权的实机验证。若仍有 TA、会话或安全存储错误，先定位新证据，不清除 persist/RPMB 或重建安全存储。
