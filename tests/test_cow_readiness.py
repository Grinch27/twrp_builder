# Requirements: Recovery must await the mapped COW UUID before opening its path.
# Ambiguity: simulated dm/uevent callbacks do not prove Android or ROM boot success.
# Research: execute the complete pinned InitializeUpdateSnapshots pre/post functions.
# Optimization: two bounded C++ builds, real temporary file opens, no real devices.
# Risks: recycled dm paths, absent nodes, blocked first-stage init and cleanup failures.
# Validation: legacy negative control, ten-second bound, all COW types and failures.
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_copylog_errors import function

ROOT = Path(__file__).resolve().parents[1]


def patch_image(after):
    lines = []
    for line in (ROOT / 'patches/recovery-cow-device-ready.patch').read_text().splitlines(True):
        if line.startswith(('+++', '---', '@@', 'diff --git')):
            continue
        if line.startswith((' ', '+' if after else '-')):
            lines.append(line[1:])
    return ''.join(lines)


COMMON = r'''
#include <cassert>
#include <cerrno>
#include <chrono>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <unistd.h>
#include <vector>
using namespace std;
using namespace std::chrono_literals;
static string host_root, scenario, current_name;
static int wait_calls = 0, consumers = 0, cleanups = 0, cleanup_errors = 0;
static int map_calls = 0, writer_inits = 0, writer_finishes = 0;
static bool recovery = true, first_stage = false;
static set<string> active;
struct Mapping { string path, uuid_path; };
static map<string, Mapping> mappings;
struct Sink { template<class T> Sink& operator<<(const T&) { return *this; } };
#define LOG(level) Sink()
#define PLOG(level) Sink()
#define CHECK(value) assert(value)
struct Return {
    bool ok;
    static Return Ok() { return {true}; }
    static Return Error() { return {false}; }
    bool is_ok() const { return ok; }
};
struct LockedFile {};
struct LpMetadata {};
struct IPartitionOpener {};
struct Partition {
    string value;
    const string& name() const { return value; }
};
struct MetadataBuilder { vector<Partition> partitions; };
static vector<Partition*> ListPartitionsWithSuffix(MetadataBuilder* metadata, const string&) {
    vector<Partition*> result;
    for (auto& part : metadata->partitions) result.push_back(&part);
    return result;
}
struct SnapshotStatus {
    bool compressed = false;
    int cow_kind = 0; // 0=file-only, 1=partition, 2=mixed; mapping is a callback.
    bool compression_enabled() const { return compressed; }
    string compression_algorithm() const { return "synthetic"; }
};
struct CreateLogicalPartitionParams {
    string block_device;
    const LpMetadata* metadata;
    chrono::milliseconds timeout_ms;
    const IPartitionOpener* partition_opener;
    string partition_name = "";
};
static const string LP_METADATA_DEFAULT_PARTITION_NAME = "super";
static void create_node(const Mapping& mapping) {
    filesystem::remove(mapping.path);
    ofstream(mapping.path).put('n');
    assert(::symlink(mapping.path.c_str(), mapping.uuid_path.c_str()) == 0);
}
namespace android {
namespace base {
struct unique_fd {
    int value;
    explicit unique_fd(int fd) : value(fd) {}
    ~unique_fd() { if (value >= 0) ::close(value); }
    operator int() const { return value; }
};
}
namespace fs_mgr {
[[maybe_unused]] static bool WaitForFile(const string& path, chrono::milliseconds budget) {
    ++wait_calls;
    assert(budget == 10000ms);
    const auto& mapping = mappings.at(current_name);
    assert(path == mapping.uuid_path && path != mapping.path);
    if (scenario == "timeout" || scenario == "cleanup_failure") {
        errno = ETIMEDOUT; return false;
    }
    if (!filesystem::exists(path)) create_node(mapping);
    return filesystem::exists(path);
}
}
}
using android::base::unique_fd;
struct DeviceMapper {
    static DeviceMapper& Instance() { static DeviceMapper instance; return instance; }
    bool GetDeviceUniquePath(const string& name, string* path) {
        if (scenario == "uuid_failure") return false;
        *path = mappings.at(name).uuid_path; return true;
    }
};
struct AutoDeviceList {
    string owned;
    ~AutoDeviceList() {
        if (owned.empty()) return;
        ++cleanups;
        if (scenario == "cleanup_failure") ++cleanup_errors;
        else active.erase(owned);
    }
};
struct DeviceInfo {
    bool IsRecovery() const { return recovery; }
    bool IsFirstStageInit() const { return first_stage; }
    bool IsTestDevice() const { return false; }
    const IPartitionOpener& GetPartitionOpener() const {
        static IPartitionOpener opener; return opener;
    }
};
struct Images {
    bool GetMappedImageDevice(const string& name, string* path) {
        if (scenario == "path_failure") return false;
        *path = mappings.at(name).path; return true;
    }
};
struct CowOptions { bool scratch_space = true; string compression; };
struct CowWriter {
    explicit CowWriter(const CowOptions&) {}
    bool Initialize(int fd) {
        ++writer_inits; assert(fd >= 0);
        return scenario != "writer_init_failure";
    }
    bool Finalize() { ++writer_finishes; return scenario != "writer_finalize_failure"; }
};
static Return InitializeKernelCow(const string& path) {
    ++consumers;
    if (scenario == "consumer_failure") { errno = EIO; return Return::Error(); }
    unique_fd fd(::open(path.c_str(), O_WRONLY | O_CLOEXEC));
    if (fd < 0) return Return::Error();
    char zeros[32] = {};
    return ::write(fd, zeros, sizeof(zeros)) == sizeof(zeros) ? Return::Ok() : Return::Error();
}
static Return AddRequiredSpace(Return result, const map<string, SnapshotStatus>&) { return result; }
struct SnapshotManager {
    DeviceInfo info;
    Images images;
    DeviceInfo* device_ = &info;
    Images* images_ = &images;
    DeviceInfo* device() { return device_; }
    bool UnmapPartitionWithSnapshot(LockedFile*, const string&) { return scenario != "unmap_failure"; }
    bool MapCowDevices(LockedFile*, const CreateLogicalPartitionParams& params,
                       const SnapshotStatus& status, AutoDeviceList* devices, string* cow_name) {
        ++map_calls;
        *cow_name = params.partition_name + (status.cow_kind ? "-cow" : "-cow-img");
        current_name = *cow_name;
        string folder = host_root + "/" + to_string(map_calls);
        filesystem::create_directories(folder);
        Mapping mapping{folder + "/recycled-dm", folder + "/uuid-of-new-mapping"};
        mappings[*cow_name] = mapping;
        active.insert(*cow_name); devices->owned = *cow_name;
        if (scenario == "map_failure") return false;
        if (!recovery || first_stage || status.cow_kind || scenario == "already_ready") create_node(mapping);
        else if (scenario == "recycled_path") ofstream(mapping.path) << "stale-node";
        return true;
    }
    Return InitializeUpdateSnapshots(LockedFile*, MetadataBuilder*, const LpMetadata*,
                                     const string&, const map<string, SnapshotStatus>&);
};
'''

MAIN = r'''
int main(int argc, char** argv) {
    assert(argc == 3); scenario = argv[1]; host_root = argv[2];
    recovery = scenario != "android" && scenario != "first_stage";
    first_stage = scenario == "first_stage" || scenario == "recovery_first_stage";
    MetadataBuilder metadata{{{"system_ext_b"}}};
    map<string, SnapshotStatus> statuses{{"system_ext_b", {}}};
    if (scenario == "types") {
        metadata.partitions = {{"product_b"}, {"system_b"}, {"system_ext_b"}, {"vendor_b"}};
        statuses = {{"product_b", {false, 1}}, {"system_b", {false, 2}},
                    {"system_ext_b", {false, 0}}, {"vendor_b", {false, 0}}};
    }
    if (scenario.find("compressed") == 0 || scenario.find("writer_") == 0)
        statuses.at("system_ext_b").compressed = true;
    if (scenario == "missing_status") statuses.clear();
    SnapshotManager manager; LockedFile lock; LpMetadata exported;
    Return result = manager.InitializeUpdateSnapshots(&lock, &metadata, &exported, "_b", statuses);
    bool failed = scenario == "timeout" || scenario == "cleanup_failure" || scenario == "uuid_failure" ||
                  scenario == "unmap_failure" || scenario == "map_failure" || scenario == "path_failure" ||
                  scenario == "consumer_failure" || scenario == "writer_init_failure" ||
                  scenario == "writer_finalize_failure";
#ifdef LEGACY_SOURCE
    assert(scenario == "gap");
    assert(!result.is_ok() && wait_calls == 0 && consumers == 1 && cleanups == 1);
#else
    assert(result.is_ok() == !failed);
    if (scenario == "timeout" || scenario == "cleanup_failure" || scenario == "uuid_failure") {
        assert(consumers == 0 && writer_inits == 0 && cleanups == 1);
        assert(wait_calls == (scenario == "uuid_failure" ? 0 : 1));
    } else if (scenario == "unmap_failure" || scenario == "missing_status") {
        assert(map_calls == 0 && wait_calls == 0 && consumers == 0 && cleanups == 0);
    } else if (scenario == "map_failure" || scenario == "path_failure") {
        assert(wait_calls == 0 && consumers == 0 && cleanups == 1);
    } else if (!recovery || first_stage) {
        assert(wait_calls == 0 && consumers == 1 && cleanups == 1);
    } else if (scenario == "types") {
        assert(wait_calls == 4 && consumers == 4 && cleanups == 4);
    } else if (statuses.at("system_ext_b").compressed) {
        assert(wait_calls == 1 && consumers == 0 && writer_inits == 1);
        assert(writer_finishes == (scenario == "writer_init_failure" ? 0 : 1));
    } else {
        assert(wait_calls == 1 && consumers == 1 && cleanups == 1);
    }
#endif
    if (scenario == "cleanup_failure") assert(cleanup_errors == 1 && active.size() == 1);
    else assert(active.empty());
    if (scenario == "recycled_path") {
        ifstream file(mappings.at(current_name).path, ios::binary);
        char c = 'x'; file.get(c); assert(c == 0); // The consumer ran after the fresh UUID appeared.
    }
    (void)failed;
    cout << "PASS " << scenario << '\n';
}
'''


class CowReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('g++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable; COW host behavior NOT_TESTED')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        signature = 'Return SnapshotManager::InitializeUpdateSnapshots('
        for name, after in [('current', True), ('legacy', False)]:
            cpp = cls.root / (name + '.cpp')
            cpp.write_text(COMMON + function(patch_image(after), signature) + MAIN)
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror']
            if not after:
                command.append('-DLEGACY_SOURCE')
            result = subprocess.run([*command, str(cpp), '-o', str(cls.root / name)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scenario(self, name, binary='current'):
        path = self.root / (binary + '-' + name)
        result = subprocess.run([str(self.root / binary), name, str(path)], check=True,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout.strip(), 'PASS ' + name)

    def test_delayed_file_only_cow_has_a_legacy_failure_negative_control(self):
        self.scenario('gap', 'legacy')
        self.scenario('gap')

    def test_recycled_canonical_path_still_waits_for_the_new_mapping_uuid(self):
        self.scenario('recycled_path')

    def test_partition_mixed_and_file_only_cows_follow_the_same_recovery_barrier(self):
        self.scenario('types')

    def test_already_ready_node_remains_successful(self):
        self.scenario('already_ready')

    def test_timeout_never_opens_cow_and_runs_existing_cleanup(self):
        self.scenario('timeout')

    def test_uuid_failure_stops_before_wait_and_consumer(self):
        self.scenario('uuid_failure')

    def test_cleanup_failure_does_not_turn_wait_failure_into_success(self):
        self.scenario('cleanup_failure')

    def test_android_and_first_stage_keep_nonblocking_behavior(self):
        for name in ('android', 'first_stage', 'recovery_first_stage'):
            self.scenario(name)

    def test_compressed_cow_initialization_also_waits(self):
        for name in ('compressed', 'writer_init_failure', 'writer_finalize_failure'):
            self.scenario(name)

    def test_mapping_path_and_unmap_failures_propagate(self):
        for name in ('map_failure', 'path_failure', 'unmap_failure'):
            self.scenario(name)

    def test_missing_snapshot_status_does_not_create_or_wait_for_a_cow(self):
        self.scenario('missing_status')

    def test_real_consumer_error_is_not_hidden(self):
        self.scenario('consumer_failure')


if __name__ == '__main__':
    unittest.main()
