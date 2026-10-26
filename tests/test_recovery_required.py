# Requirements: preserve valid relink inputs and require real module owners.
# Ambiguity: fixture Make evaluation does not prove the full Android build.
# Research: pinned Recovery CLI stem and init/ziptool recovery symlink owners.
# Optimization: tiny public Make fixtures; no Android downloads or binaries.
# Risks: applying a patch to different source or changing runtime file lists.
# Validation: Git precheck failure is atomic; GNU Make resolves exact owners.
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/recovery-required-modules.patch'
ROOT_SOURCE = r"""TWRP_REQUIRED_MODULES += \
    pigz \
    teamwin \
    twrp \
    fsck.fat \
    fatlabel \
    mkfs.fat \
    permissive.sh \
    simg2img_twrp \
    libbootloader_message
ifneq ($(TW_INCLUDE_CRYPTO),)
TWRP_REQUIRED_MODULES += \
    vold_prepare_subdirs \
    task_recovery_profiles.json \
    fscryptpolicyget.recovery \
    keystore_auth \
    keystore2 \
    android.system.keystore2-service.xml
endif
ifeq ($(TWRP_INCLUDE_LOGCAT), true)
    TWRP_REQUIRED_MODULES += logcat event-log-tags
    ifeq ($(TARGET_USES_LOGD), true)
    endif
endif
ifeq ($(TARGET_USERIMAGES_USE_F2FS), true)
    TWRP_REQUIRED_MODULES += sload_f2fs \
        libfs_mgr \
        fs_mgr \
        liblz4 \
        libinit
endif
"""
PREBUILT_SOURCE = r"""RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libminijail.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libunwindstack.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libbinderthreadstate.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libmdnssd.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/android.hardware.boot@1.0.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/libevent.so
RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/keystore
RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/keystore_auth
RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/keystore_cli_v2
        RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/avbctl
        RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/keystore
        RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/keystore2
        RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/keystore_cli
        RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/android.system.wifi.keystore@1.0.so
        RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/android.system.suspend@1.0.so
        RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/fscryptpolicyget
        ifneq ($(TW_EXCLUDE_LIBXML2), true)
endif
ifeq ($(TW_INCLUDE_NTFS_3G),true)
    RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/mount.ntfs
    RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/fsck.ntfs
    RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/mkfs.ntfs
else
    RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/ntfs-3g
    RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/ntfsfix
    RECOVERY_BINARY_SOURCE_FILES += $(TARGET_OUT_EXECUTABLES)/mkntfs
endif
RECOVERY_BINARY_SOURCE_FILES := /out/bin/bu /recovery/bin/twrp /recovery/bin/ueventd /recovery/bin/unzip /out/bin/bc
TARGET_BINARY_RELINK_FILES := $(filter-out bu, $(notdir $(RECOVERY_BINARY_SOURCE_FILES)))
LOCAL_REQUIRED_MODULES += $(TARGET_BINARY_RELINK_FILES)
include $(BUILD_PHONY_PACKAGE)
LOCAL_REQUIRED_MODULES += plat_service_contexts \
    plat_hwservice_contexts \
    plat_hardware_contexts \
    vndservice_contexts \
    plat_keystore2_key_contexts
"""


class RecoveryRequiredModulesTests(unittest.TestCase):
    def test_device_required_name_uses_module_without_altering_library_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ('# Vibrator modules\nTARGET_RECOVERY_DEVICE_MODULES += \\\n'
                      '    android.hardware.vibrator-V2-ndk.so\n\n'
                      'RECOVERY_LIBRARY_SOURCE_FILES += \\\n'
                      '    $(TARGET_OUT_SHARED_LIBRARIES)/android.hardware.vibrator-V2-ndk.so\n')
            (root / 'device.mk').write_text(source)
            patch = ROOT / 'patches/selene-module-names.patch'
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            for flags in [['--check'], []]:
                subprocess.run(['git', '-C', str(root), 'apply', *flags, str(patch)],
                               check=True, capture_output=True)
            (root / 'fixture.mk').write_text('TARGET_OUT_SHARED_LIBRARIES := /system/lib64\n'
                'include device.mk\n$(info MODULES=$(TARGET_RECOVERY_DEVICE_MODULES))\n'
                '$(info FILES=$(RECOVERY_LIBRARY_SOURCE_FILES))\nall:\n\t@:\n')
            output = subprocess.check_output(['make', '-s', '-f', 'fixture.mk'],
                                             cwd=root, text=True)
            self.assertIn('MODULES=android.hardware.vibrator-V2-ndk\n', output)
            self.assertIn('FILES=/system/lib64/android.hardware.vibrator-V2-ndk.so\n', output)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        (self.tree / 'prebuilt').mkdir()
        (self.tree / 'Android.mk').write_text(ROOT_SOURCE)
        (self.tree / 'prebuilt/Android.mk').write_text(PREBUILT_SOURCE)
        subprocess.run(['git', '-C', str(self.tree), 'init', '--quiet'], check=True)

    def git_apply(self, check=False):
        command = ['git', '-C', str(self.tree), 'apply']
        if check:
            command.append('--check')
        return subprocess.run(command + [str(PATCH)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)

    def test_patch_preserves_binary_names_and_valid_library_inputs(self):
        self.assertEqual(self.git_apply(check=True).returncode, 0)
        self.assertEqual(self.git_apply().returncode, 0)
        (self.tree / 'empty.mk').write_text('')
        (self.tree / 'fixture.mk').write_text(
            'BUILD_PHONY_PACKAGE := empty.mk\n'
            'TARGET_RECOVERY_ROOT_OUT := /recovery\n'
            'TARGET_OUT_SHARED_LIBRARIES := /system/lib64\n'
            'TW_INCLUDE_CRYPTO := true\n'
            'TWRP_INCLUDE_LOGCAT := true\n'
            'TARGET_USERIMAGES_USE_F2FS := true\n'
            'include Android.mk\n'
            'include prebuilt/Android.mk\n'
            'KNOWN_MODULES := pigz teamwin orscmd fsck.fat fatlabel mkfs.fat '
            'init_second_stage.recovery ziptool.recovery bc simg2img_twrp '
            'vold_prepare_subdirs task_recovery_profiles.json keystore2 '
            'android.system.keystore2-service.xml logcat sload_f2fs libfs_mgr '
            'liblz4 libinit plat_hwservice_contexts vndservice_contexts '
            'libbootloader_message plat_service_contexts plat_keystore2_key_contexts\n'
            'REQUIRED := $(sort $(TWRP_REQUIRED_MODULES) $(LOCAL_REQUIRED_MODULES))\n'
            'ifneq ($(filter-out $(KNOWN_MODULES),$(REQUIRED)),)\n'
            '$(error non-existent required module)\n'
            'endif\n'
            '$(info FILES=$(TARGET_BINARY_RELINK_FILES))\n'
            '$(info LIBRARIES=$(RECOVERY_LIBRARY_SOURCE_FILES))\n'
            '$(info OWNERS=$(REQUIRED))\n'
            '.PHONY: all\nall:\n\t@:\n')
        result = subprocess.check_output(['make', '--no-print-directory', '-s',
                                          '-f', 'fixture.mk'], cwd=self.tree, text=True)
        fields = dict(line.split('=', 1) for line in result.splitlines() if '=' in line)
        self.assertEqual(fields['FILES'].split(), ['twrp', 'ueventd', 'unzip', 'bc'])
        self.assertEqual(fields['LIBRARIES'].split(), [
            '/recovery/system/lib64/libminijail.so',
            '/recovery/system/lib64/libunwindstack.so',
            '/recovery/system/lib64/libmdnssd.so',
            '/system/lib64/android.hardware.boot@1.0.so',
            '/system/lib64/libevent.so',
            '/system/lib64/android.system.wifi.keystore@1.0.so',
            '/system/lib64/android.system.suspend@1.0.so',
        ])
        owners = set(fields['OWNERS'].split())
        self.assertTrue({'orscmd', 'init_second_stage.recovery', 'ziptool.recovery'} <= owners)
        self.assertFalse({'twrp', 'ueventd', 'unzip'} & owners)
        self.assertTrue({'keystore2', 'libfs_mgr', 'logcat', 'task_recovery_profiles.json'} <= owners)
        self.assertFalse({'teamwin', 'permissive.sh', 'fscryptpolicyget.recovery',
                          'keystore_auth', 'event-log-tags', 'fs_mgr', 'plat_hardware_contexts'} & owners)
        prebuilt = (self.tree / 'prebuilt/Android.mk').read_text()
        self.assertNotIn('/keystore_auth', prebuilt)
        self.assertNotIn('/fscryptpolicyget', prebuilt)
        self.assertNotIn('/keystore\n', prebuilt)
        self.assertNotIn('/keystore_cli\n', prebuilt)
        self.assertIn('/keystore2\n', prebuilt)
        self.assertIn('/keystore_cli_v2\n', prebuilt)

    def test_ntfs_provider_detection_preserves_mount_repair_and_format(self):
        self.assertEqual(self.git_apply(check=True).returncode, 0)
        self.assertEqual(self.git_apply().returncode, 0)
        text = (self.tree / 'prebuilt/Android.mk').read_text()
        start = text.index('ifneq ($(filter true,$(TW_INCLUDE_NTFS_3G))')
        block = text[start:text.index('endif', start)] + 'endif\n'
        (self.tree / 'ntfs.mk').write_text('TARGET_OUT_EXECUTABLES := /bin\n' + block
            + '$(info FILES=$(notdir $(RECOVERY_BINARY_SOURCE_FILES)))\nall:\n\t@:\n')
        blueprint = self.tree / 'external/ntfs-3g/Android.bp'
        blueprint.parent.mkdir(parents=True)
        blueprint.write_text('cc_binary { name: "mount.ntfs" }\n')
        for flag in ['', 'true']:
            output = subprocess.check_output(['make', '-s', '-f', 'ntfs.mk',
                'TW_INCLUDE_NTFS_3G=' + flag], cwd=self.tree, text=True)
            self.assertEqual(output.strip(), 'FILES=mount.ntfs fsck.ntfs mkfs.ntfs')

    def test_oem_mode_keeps_the_existing_cli_exclusion(self):
        self.assertEqual(self.git_apply(check=True).returncode, 0)
        self.assertEqual(self.git_apply().returncode, 0)
        (self.tree / 'oem.mk').write_text(
            'TW_OEM_BUILD := true\n'
            'include Android.mk\n'
            '$(info REQUIRED=$(TWRP_REQUIRED_MODULES))\n'
            '.PHONY: all\nall:\n\t@:\n')
        result = subprocess.check_output(['make', '--no-print-directory', '-s',
                                          '-f', 'oem.mk'], cwd=self.tree, text=True)
        required = result.strip().split('=', 1)[1].split()
        self.assertNotIn('twrp', required)
        self.assertNotIn('orscmd', required)

    def test_different_source_is_rejected_before_any_file_is_changed(self):
        root = self.tree / 'Android.mk'
        root.write_text(ROOT_SOURCE.replace('teamwin', 'different_source'))
        before = {p: p.read_bytes() for p in (root, self.tree / 'prebuilt/Android.mk')}
        self.assertNotEqual(self.git_apply(check=True).returncode, 0)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
