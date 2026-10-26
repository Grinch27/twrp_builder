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
    mkfs.fat
"""
PREBUILT_SOURCE = r"""RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libminijail.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libunwindstack.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libbinderthreadstate.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_RECOVERY_ROOT_OUT)/system/lib64/libmdnssd.so
RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/android.hardware.boot@1.0.so
RECOVERY_BINARY_SOURCE_FILES := /out/bin/bu /recovery/bin/twrp /recovery/bin/ueventd /recovery/bin/unzip /out/bin/bc
TARGET_BINARY_RELINK_FILES := $(filter-out bu, $(notdir $(RECOVERY_BINARY_SOURCE_FILES)))
LOCAL_REQUIRED_MODULES += $(TARGET_BINARY_RELINK_FILES)
include $(BUILD_PHONY_PACKAGE)
"""


class RecoveryRequiredModulesTests(unittest.TestCase):
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
            'include Android.mk\n'
            'include prebuilt/Android.mk\n'
            'KNOWN_MODULES := pigz teamwin orscmd fsck.fat fatlabel mkfs.fat '
            'init_second_stage.recovery ziptool.recovery bc\n'
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
        ])
        owners = set(fields['OWNERS'].split())
        self.assertTrue({'orscmd', 'init_second_stage.recovery', 'ziptool.recovery'} <= owners)
        self.assertFalse({'twrp', 'ueventd', 'unzip'} & owners)

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
