# Requirements: alias failures must retain syscall errno and protect foreign entries.
# Ambiguity: host filesystems cannot establish device boot or third-party compatibility.
# Research: execute the complete logical-name and alias helpers from the pinned patch.
# Optimization: one bounded C++ build, temporary host paths, no firmware or devices.
# Risks: missing parents, hidden I/O errors, lost ownership and partial remap failures.
# Validation: real filesystem behavior, injected errors, errno-clobbering diagnostics.
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_copylog_errors import function
from test_recovery_layout import image


COMMON = r'''
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
using namespace std;
static string host_root;
static string fail_operation;
static int fail_errno = 0, properties = 0;
static bool create_racing_link = false;
static map<string, int> calls;
static vector<string> diagnostics;
static string host_path(const char* path) {
    assert(string(path).rfind("/dev/block/", 0) == 0);
    return host_root + path;
}
static bool fail(const string& operation) {
    ++calls[operation];
    if (fail_operation != operation) return false;
    errno = fail_errno; return true;
}
static int host_lstat(const char* path, struct stat* result) {
    if (fail("lstat")) return -1;
    return ::lstat(host_path(path).c_str(), result);
}
static ssize_t host_readlink(const char* path, char* buffer, size_t bytes) {
    if (fail("readlink")) return -1;
    return ::readlink(host_path(path).c_str(), buffer, bytes);
}
static int host_unlink(const char* path) {
    if (fail("unlink")) return -1;
    return ::unlink(host_path(path).c_str());
}
static int host_symlink(const char* target, const char* path) {
    if (create_racing_link) {
        assert(::symlink("/foreign/device", host_path(path).c_str()) == 0);
        create_racing_link = false;
    }
    if (fail("symlink")) return -1;
    return ::symlink(target, host_path(path).c_str());
}
static void log_info(const char* format, ...) {
    char buffer[256]; va_list args;
    va_start(args, format);
    int bytes = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    assert(bytes >= 0 && static_cast<size_t>(bytes) < sizeof(buffer));
    diagnostics.emplace_back(buffer);
    errno = EINTR; // Logging may change errno; the caller must restore it.
}
static int property_set(const char*, const char*) { ++properties; return 0; }
struct TWFunc {
    static string Get_Filename(const string& path) {
        return path.substr(path.find_last_of('/') + 1);
    }
};
struct TWPartition {
    string Logical_Partition_Source = "mi_ext", Logical_Alias_Target;
    bool SlotSelect = true;
};
struct TWPartitionManager {
    string Get_Active_Slot_Suffix() { return "_a"; }
    string Logical_Partition_Name(const TWPartition*, bool);
    bool Update_Logical_Alias(TWPartition*, const string&);
};
#define LOGINFO(...) log_info(__VA_ARGS__)
#define lstat host_lstat
#define readlink host_readlink
#define unlink host_unlink
#define symlink host_symlink
'''

MAIN = r'''
#undef lstat
#undef readlink
#undef unlink
#undef symlink
static string target_of(const string& path) {
    char buffer[4096]; ssize_t bytes = ::readlink(path.c_str(), buffer, sizeof(buffer));
    return bytes < 0 ? "" : string(buffer, static_cast<size_t>(bytes));
}
static void expect_failure(TWPartitionManager& pm, TWPartition& part,
                           const string& device, const string& operation, int error) {
    bool result = pm.Update_Logical_Alias(&part, device);
    int observed_errno = errno;
    assert(!result && observed_errno == error);
    assert(!diagnostics.empty());
    assert(diagnostics.back() == "Logical alias failed: op=" + operation +
           " errno=" + to_string(error) + "\n");
    assert(diagnostics.back().find(host_root) == string::npos);
    assert(diagnostics.back().find(device) == string::npos || device.empty());
}
int main(int argc, char** argv) {
    assert(argc == 3); string scenario = argv[1]; host_root = argv[2];
    namespace fs = std::filesystem;
    fs::create_directories(host_root + "/dev/block/platform/bootdevice/by-name");
    string parent = host_root + "/dev/block/bootdevice/by-name";
    string leaf = parent + "/mi_ext";
    const string device = "/dev/block/dm-5", changed = "/dev/block/dm-7";
    TWPartitionManager pm; TWPartition part;
    if (scenario == "missing_parent") {
        for (const string source : {"system", "vendor", "product", "mi_ext"}) {
            part.Logical_Partition_Source = source;
            expect_failure(pm, part, device, "symlink", ENOENT);
            assert(part.Logical_Alias_Target.empty());
        }
        assert(!fs::exists(host_root + "/dev/block/bootdevice"));
        assert(calls["unlink"] == 0 && properties == 0);
    } else if (scenario == "parent_not_directory") {
        fs::create_directories(host_root + "/dev/block/bootdevice");
        ofstream(parent).put('x');
        expect_failure(pm, part, device, "lstat", ENOTDIR);
        assert(calls["symlink"] == 0 && properties == 0);
        assert(fs::is_regular_file(parent) && part.Logical_Alias_Target.empty());
    } else {
        fs::create_directories(parent);
        if (scenario == "lifecycle") {
            assert(pm.Update_Logical_Alias(&part, device));
            assert(target_of(leaf) == device && part.Logical_Alias_Target == device);
            assert(pm.Update_Logical_Alias(&part, device));
            assert(calls["symlink"] == 1 && calls["unlink"] == 0);
            assert(pm.Update_Logical_Alias(&part, changed));
            assert(target_of(leaf) == changed && part.Logical_Alias_Target == changed);
            assert(pm.Update_Logical_Alias(&part, ""));
            assert(!fs::is_symlink(leaf) && part.Logical_Alias_Target.empty());
            assert(properties == 2 && diagnostics.empty());
        } else if (scenario == "foreign_link" || scenario == "foreign_file" || scenario == "foreign_same_target") {
            if (scenario == "foreign_file") ofstream(leaf).put('x');
            else assert(::symlink((scenario == "foreign_same_target" ? device : "/foreign/device").c_str(), leaf.c_str()) == 0);
            assert(pm.Update_Logical_Alias(&part, device));
            assert(part.Logical_Alias_Target.empty() && calls["unlink"] == 0 && calls["symlink"] == 0);
            if (scenario == "foreign_file") assert(fs::is_regular_file(leaf));
            else assert(target_of(leaf) == (scenario == "foreign_same_target" ? device : "/foreign/device"));
        } else if (scenario == "replaced_link" || scenario == "replaced_file") {
            assert(pm.Update_Logical_Alias(&part, device));
            assert(::unlink(leaf.c_str()) == 0);
            if (scenario == "replaced_file") ofstream(leaf).put('x');
            else assert(::symlink("/foreign/device", leaf.c_str()) == 0);
            assert(pm.Update_Logical_Alias(&part, changed));
            assert(part.Logical_Alias_Target.empty() && calls["unlink"] == 0);
            if (scenario == "replaced_file") assert(fs::is_regular_file(leaf));
            else assert(target_of(leaf) == "/foreign/device");
        } else if (scenario == "missing_owned" || scenario == "cleanup_missing_owned") {
            assert(pm.Update_Logical_Alias(&part, device));
            assert(::unlink(leaf.c_str()) == 0);
            assert(pm.Update_Logical_Alias(&part, scenario == "missing_owned" ? changed : ""));
            if (scenario == "missing_owned") assert(target_of(leaf) == changed && part.Logical_Alias_Target == changed);
            else assert(!fs::is_symlink(leaf) && part.Logical_Alias_Target.empty());
        } else if (scenario == "lstat_error" || scenario == "readlink_error" || scenario == "unlink_error" || scenario == "symlink_error") {
            string operation = scenario.substr(0, scenario.find('_'));
            bool owned = operation == "readlink" || operation == "unlink";
            if (owned) assert(pm.Update_Logical_Alias(&part, device));
            for (int error : {EACCES, EIO}) {
                fail_operation = operation; fail_errno = error;
                expect_failure(pm, part, owned ? changed : device, operation, error);
                assert(part.Logical_Alias_Target == (owned ? device : ""));
                if (owned) assert(target_of(leaf) == device);
                else assert(!fs::is_symlink(leaf));
            }
            assert(calls["symlink"] == (owned ? 1 : operation == "symlink" ? 2 : 0));
            assert(calls["unlink"] == (operation == "unlink" ? 2 : 0));
        } else if (scenario == "create_race") {
            create_racing_link = true;
            expect_failure(pm, part, device, "symlink", EEXIST);
            assert(target_of(leaf) == "/foreign/device" && part.Logical_Alias_Target.empty());
            assert(calls["unlink"] == 0 && properties == 0);
        } else if (scenario == "partial_remap") {
            assert(pm.Update_Logical_Alias(&part, device));
            fail_operation = "symlink"; fail_errno = EIO;
            expect_failure(pm, part, changed, "symlink", EIO);
            assert(!fs::is_symlink(leaf) && part.Logical_Alias_Target.empty());
            assert(calls["unlink"] == 1 && calls["symlink"] == 2 && properties == 1);
        } else if (scenario == "empty_cleanup") {
            assert(pm.Update_Logical_Alias(&part, ""));
            assert(calls.empty() && properties == 0 && diagnostics.empty());
        } else if (scenario == "invalid_source") {
            for (const string source : {"", "..", "invalid:name"}) {
                part.Logical_Partition_Source = source;
                expect_failure(pm, part, device, "source", EINVAL);
            }
            assert(calls.empty() && properties == 0);
        } else {return 2;}
    }
    cout << "PASS " << scenario << '\n';
}
'''


class LogicalAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('g++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable; alias host behavior NOT_TESTED')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        source = image('partitionmanager.cpp')
        signatures = ['string TWPartitionManager::Logical_Partition_Name(',
                      'bool TWPartitionManager::Update_Logical_Alias(']
        cpp = cls.root / 'alias.cpp'
        cpp.write_text(COMMON + ''.join(function(source, sig) for sig in signatures) + MAIN)
        cls.binary = cls.root / 'alias'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-DAB_OTA_UPDATER', str(cpp), '-o', str(cls.binary)], check=True,
                       capture_output=True, text=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scenario(self, name):
        result = subprocess.run([str(self.binary), name, str(self.root / name)],
                                check=True, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout.strip(), 'PASS ' + name)

    def test_missing_legacy_parent_reports_real_enoent_without_creating_it(self):
        self.scenario('missing_parent')

    def test_non_directory_parent_is_an_error(self):
        self.scenario('parent_not_directory')

    def test_owned_alias_create_repeat_remap_and_cleanup(self):
        self.scenario('lifecycle')

    def test_existing_foreign_entries_are_preserved_without_taking_ownership(self):
        for name in ('foreign_link', 'foreign_file', 'foreign_same_target'):
            self.scenario(name)

    def test_external_replacements_are_preserved_and_release_ownership(self):
        self.scenario('replaced_link')
        self.scenario('replaced_file')

    def test_missing_owned_link_can_be_recreated_or_cleaned_up(self):
        self.scenario('missing_owned')
        self.scenario('cleanup_missing_owned')

    def test_lstat_errors_are_not_success_and_errno_survives_logging(self):
        self.scenario('lstat_error')

    def test_readlink_errors_preserve_ownership_and_errno(self):
        self.scenario('readlink_error')

    def test_unlink_errors_preserve_owned_link_and_errno(self):
        self.scenario('unlink_error')

    def test_symlink_errors_do_not_claim_ownership_or_set_property(self):
        self.scenario('symlink_error')

    def test_eexist_race_never_overwrites_foreign_link(self):
        self.scenario('create_race')

    def test_partial_remap_failure_is_not_reported_as_atomic_rollback(self):
        self.scenario('partial_remap')

    def test_unowned_cleanup_does_not_probe_or_create_alias(self):
        self.scenario('empty_cleanup')

    def test_invalid_source_stops_before_filesystem_calls(self):
        self.scenario('invalid_source')


if __name__ == '__main__':
    unittest.main()
