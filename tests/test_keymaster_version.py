# Requirements: target values before first HAL load, without changing SDK or Android inputs.
# Ambiguity: generated ramdisk properties cannot prove the TA accepts an existing key.
# Research: execute the patched Recovery recipe from locked TeamWin build/make.
# Optimization: miniature Make target with real patch application, no Android sync.
# Risks: duplicate values, late property conflicts, missing input and changed normal boot.
# Validation: recipe output, source immutability, final-default rejection and Native scope.
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_boot import verify_target_keymaster_version

ROOT = Path(__file__).resolve().parents[1]


class KeymasterVersionTests(unittest.TestCase):
    def test_real_patch_recipe_replaces_duplicates_before_packaging(self):
        # Public upstream target structure, reduced to its actual concatenation recipe.
        source = '''INSTALLED_RECOVERY_BUILD_PROP_TARGET := recovery/prop.default
INSTALLED_BUILD_PROP_TARGET := system.prop
INSTALLED_VENDOR_BUILD_PROP_TARGET := vendor.prop
INSTALLED_ODM_BUILD_PROP_TARGET := odm.prop
INSTALLED_PRODUCT_BUILD_PROP_TARGET := product.prop
INSTALLED_SYSTEM_EXT_BUILD_PROP_TARGET := system_ext.prop
all: $(INSTALLED_RECOVERY_BUILD_PROP_TARGET)
define append-recovery-ui-properties
echo ro.recovery.ui.animation_fps=30 >> $(2)
endef
$(INSTALLED_RECOVERY_BUILD_PROP_TARGET): \\
\t    $(INSTALLED_BUILD_PROP_TARGET) \\
\t    $(INSTALLED_VENDOR_BUILD_PROP_TARGET) \\
\t    $(INSTALLED_ODM_BUILD_PROP_TARGET) \\
\t    $(INSTALLED_PRODUCT_BUILD_PROP_TARGET) \\
\t    $(INSTALLED_SYSTEM_EXT_BUILD_PROP_TARGET)
\t@echo "Target recovery buildinfo: $@"
\t$(hide) mkdir -p $(dir $@)
\t$(hide) rm -f $@
\t$(hide) cat $(INSTALLED_BUILD_PROP_TARGET) >> $@
\t$(hide) cat $(INSTALLED_VENDOR_BUILD_PROP_TARGET) >> $@
\t$(hide) cat $(INSTALLED_ODM_BUILD_PROP_TARGET) >> $@
\t$(hide) cat $(INSTALLED_PRODUCT_BUILD_PROP_TARGET) >> $@
\t$(hide) cat $(INSTALLED_SYSTEM_EXT_BUILD_PROP_TARGET) >> $@
\t$(call append-recovery-ui-properties,$(PRIVATE_RECOVERY_UI_PROPERTIES),$@)

# Only install boot/etc/build.prop to recovery image on recovery_as_boot.
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'core').mkdir()
            (root / 'core/Makefile').write_text(source)
            original = {
                'system.prop': 'ro.build.version.release=12\nro.build.version.security_patch=2022-04-05\nro.build.version.sdk=32\n',
                'vendor.prop': 'ro.vendor.build.security_patch=2021-07-01\n',
                'odm.prop': 'ro.build.version.release?=11\n',
                'product.prop': 'ro.build.version.security_patch=2020-01-01\n',
                'system_ext.prop': 'unrelated.property=kept\nroXbuildXversionXrelease=kept\n',
            }
            for path, text in original.items():
                (root / path).write_text(text)
            patch = ROOT / 'patches/recovery-target-keymaster-version.patch'
            subprocess.run(['git', 'apply', '--check', '--whitespace=error-all', str(patch)],
                           cwd=root, check=True, capture_output=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=root, check=True, capture_output=True)
            subprocess.run(['make', '-s', '-f', 'core/Makefile'], cwd=root,
                           check=True, capture_output=True, timeout=10)
            data = (root / 'recovery/prop.default').read_bytes()
            verify_target_keymaster_version({'prop.default': (stat.S_IFREG | 0o644, data)})
            self.assertIn(b'ro.vendor.build.security_patch=2021-07-01\n', data)
            self.assertIn(b'unrelated.property=kept\n', data)
            self.assertIn(b'roXbuildXversionXrelease=kept\n', data)
            self.assertIn(b'ro.recovery.ui.animation_fps=30\n', data)
            for path, text in original.items():
                self.assertEqual((root / path).read_text(), text)

    def test_final_properties_reject_old_missing_duplicate_and_wrong_sdk(self):
        valid = b'ro.build.version.release=13\nro.build.version.security_patch=2023-12-01\nro.build.version.sdk=32\n'
        for data in (valid.replace(b'=13', b'=12'), valid.replace(b'2023-12-01', b'2022-04-05'),
                     valid.replace(b'=32', b'=33'), valid + b'ro.build.version.release=13\n',
                     valid + b'ro.build.version.release?=12\n', valid.replace(b'ro.build.version.release=13\n', b'')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                verify_target_keymaster_version({'prop.default': (stat.S_IFREG | 0o644, data)})
        verify_target_keymaster_version({'prop.default': (stat.S_IFREG | 0o644, valid)})
        with self.assertRaises(ValueError):
            verify_target_keymaster_version({'prop.default': (stat.S_IFLNK | 0o777, valid)})
        with self.assertRaises(ValueError):
            verify_target_keymaster_version({'prop.default': (stat.S_IFREG | 0o644, valid),
                                             'system/build.prop': (stat.S_IFREG | 0o644, b'ro.build.version.release=12\n')})

    def test_native_only_flag_and_final_image_check_are_connected(self):
        source = (ROOT / 'scripts/build.sh').read_text()
        self.assertIn('if [[ "${SELENE_TARGET_KEYMASTER_VERSION:-0}" == 1 ]]; then', source)
        self.assertIn('target_version_args=(--target-keymaster-version)', source)
        self.assertIn('"${target_version_args[@]}"', source.split('trace_public_command boot_static_verify\n')[1])


if __name__ == '__main__':
    unittest.main()
