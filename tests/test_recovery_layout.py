# Requirements: stable logical identity and one nested resolver for Find/Mount/UnMount.
# Ambiguity: synthetic callbacks cannot prove Android compilation, mounts or backups.
# Research: execute complete changed functions from the locked public Recovery patch.
# Optimization: two small C++17 harness builds, no firmware or device access in tests.
# Risks: alias collisions, slot drift, failed remaps, foreign links and write-scope expansion.
# Validation: actual dispatch/identity/failure paths with virtual filesystem/DM callbacks.
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_copylog_errors import function

ROOT = Path(__file__).resolve().parents[1]


def image(path, after=True):
    selected, lines = False, []
    for line in (ROOT / 'patches/recovery-layout-paths.patch').read_text().splitlines(True):
        if line.startswith('diff --git '):
            selected = line.rstrip().endswith(' b/' + path)
        elif selected and not line.startswith(('+++', '---', '@@')):
            if line.startswith((' ', '+' if after else '-')):
                lines.append(line[1:])
    return ''.join(lines)


COMMON = r'''
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
using namespace std;
#define LOGINFO(...) do {} while(0)
namespace msg { enum {kError}; }
struct Msg {
    Msg(int, string) {}
    string operator()(const string& value) {return value;}
};
static vector<string> gui_messages;
static void gui_msg(const string& message) {gui_messages.push_back(message);}
struct TWFunc {
    // Unchanged pinned Get_Root_Path semantics, used only by the compatibility guard.
    static string Get_Root_Path(const string& Path) {
        string result = Path;
        if (result.substr(0, 1) != "/") result = "/" + result;
        size_t position = result.find("/", 2);
        if (position != string::npos) result.resize(position);
        return result;
    }
    static string Get_Filename(const string& path) {return path.substr(path.find_last_of('/') + 1);}
};
struct FstabEntry {
    string blk_device, mount_point, fs_type;
    struct {bool logical = false;} fs_mgr_flags;
};
using Fstab = vector<FstabEntry>;
struct Node {mode_t mode; string target;};
static map<string, Node> nodes;
static vector<string> updates, destroys;
static set<string> fail_updates, fail_destroys;
static bool ready = true, unmount_ok = true;
static int sleeps = 0, unlinks = 0, links = 0, deleted_parts = 0;
static bool fs_mgr_update_logical_partition(FstabEntry* entry) {
    updates.push_back(entry->blk_device);
    if (fail_updates.count(entry->blk_device)) return false;
    entry->blk_device = "/virtual-dm/" + entry->blk_device;
    return true;
}
static bool DestroyLogicalPartition(const string& name) {
    destroys.push_back(name); return !fail_destroys.count(name);
}
static int fake_access(const char* path, int) {
    if (string(path).find("/virtual-dm/") == 0 && ready) return 0;
    errno = ENOENT; return -1;
}
static int fake_usleep(unsigned int) {++sleeps; return 0;}
static int fake_lstat(const char* path, struct stat* out) {
    auto found = nodes.find(path);
    if (found == nodes.end()) {errno = ENOENT; return -1;}
    out->st_mode = found->second.mode; return 0;
}
static ssize_t fake_readlink(const char* path, char* out, size_t limit) {
    auto found = nodes.find(path);
    if (found == nodes.end()) {errno = ENOENT; return -1;}
    if (!S_ISLNK(found->second.mode)) {errno = EINVAL; return -1;}
    size_t count = min(limit, found->second.target.size());
    memcpy(out, found->second.target.data(), count); return count;
}
static int fake_symlink(const char* target, const char* path) {
    if (nodes.count(path)) {errno = EEXIST; return -1;}
    nodes[path] = {S_IFLNK, target}; ++links; return 0;
}
static int fake_unlink(const char* path) {++unlinks; return nodes.erase(path) ? 0 : -1;}
static int property_set(const char*, const char*) {return 0;}
#define access fake_access
#define usleep fake_usleep
#define lstat fake_lstat
#define readlink fake_readlink
#define symlink fake_symlink
#define unlink fake_unlink
struct TWPartition {
    string Mount_Point, Symlink_Mount_Point, SubPartition_Of, Current_File_System = "ext4";
    string Logical_Partition_Source, Mapped_Logical_Partition, Logical_Alias_Target;
    string Primary_Block_Device, Actual_Block_Device, Original_Path = "crypto-origin-untouched";
    bool Is_Super = false, SlotSelect = true, Is_SubPartition = false;
    bool Can_Be_Backed_Up = false, Can_Be_Wiped = false, mounted = false;
    int mounts = 0, unmounts = 0, last_flags = 0;
    ~TWPartition() {++deleted_parts;}
    bool Mount(bool) {++mounts; mounted = true; return true;}
    bool UnMount(bool, int flags = 0) {++unmounts; last_flags = flags; if (!unmount_ok) return false; mounted = false; return true;}
    string Get_Mount_Point() {return Mount_Point;}
    void Set_Block_Device(string value) {Primary_Block_Device = value; Actual_Block_Device = value;}
    void Update_Size(bool) {}
    void Set_Can_Be_Backed_Up(bool value) {Can_Be_Backed_Up = value;}
    void Set_Can_Be_Wiped(bool value) {Can_Be_Wiped = value;}
};
struct TWPartitionManager {
    vector<TWPartition*> Partitions;
    vector<string> Super_Partition_List;
    string slot = "_a";
    string Get_Active_Slot_Suffix() {return slot;}
    string Get_Android_Root_Path() {return "/system_root";}
    void Output_Partition(TWPartition*) {}
    void Update_System_Details() {}
    TWPartition* Resolve_Partition_Path(const string&, string*);
    TWPartition* Find_Partition_By_Path(const string&);
    TWPartition* Find_Partition_By_Root_Path(const string&);
    int Mount_By_Path(string, bool);
    int UnMount_By_Path(string, bool, int = 0);
    string Logical_Partition_Name(const TWPartition*, bool);
    bool Update_Logical_Alias(TWPartition*, const string&);
    bool Prepare_Super_Volume(TWPartition*);
    bool Prepare_All_Super_Volumes();
    bool Unmap_Super_Devices();
} PartitionManager;
static TWPartition* add(const string& path, const string& source = "") {
    auto* part = new TWPartition(); part->Mount_Point = path;
    part->Logical_Partition_Source = source; part->Primary_Block_Device = source;
    part->Is_Super = !source.empty(); PartitionManager.Partitions.push_back(part); return part;
}
static void reset() {
    for (auto* part : PartitionManager.Partitions) delete part;
    PartitionManager.Partitions.clear(); PartitionManager.Super_Partition_List.clear();
    PartitionManager.slot = "_a"; nodes.clear(); updates.clear(); destroys.clear();
    fail_updates.clear(); fail_destroys.clear(); gui_messages.clear();
    ready = unmount_ok = true; sleeps = unlinks = links = deleted_parts = 0;
}
'''

MAIN = r'''
int main(int argc, char** argv) {
    assert(argc == 2); string scenario = argv[1]; auto& pm = PartitionManager;
    if (scenario == "paths" || scenario == "dispatch" || scenario == "guard") {
        auto* data = add("/data"); data->Symlink_Mount_Point = "/sdcard";
        auto* metadata = add("/metadata"); auto* system = add("/system_root");
        auto* mi = add("/mnt/vendor/mi_ext");
        for (const string name : {"protect_f", "protect_s", "nvdata", "nvcfg", "persist", "persistbak"}) {
            auto* part = add("/mnt/vendor/" + name);
            assert(pm.Find_Partition_By_Path(part->Mount_Point) == part);
            assert(pm.Find_Partition_By_Path(part->Mount_Point + "/child/file") == part);
        }
        for (const string name : {"protect_f", "protect_s", "nvdata", "persist"}) {
            auto* short_part = add("/" + name); short_part->Can_Be_Backed_Up = true;
            assert(pm.Find_Partition_By_Path("/" + name) == short_part);
            assert(pm.Find_Partition_By_Path("/mnt/vendor/" + name) != short_part);
        }
        assert(pm.Find_Partition_By_Path("/data/media/0") == data);
        assert(pm.Find_Partition_By_Path("metadata/vold/metadata_encryption") == metadata);
        assert(pm.Find_Partition_By_Path("/system") == system);
        assert(pm.Find_Partition_By_Path("/system/build.prop") == system);
        assert(pm.Find_Partition_By_Path("/sdcard/folder") == data);
        assert(pm.Find_Partition_By_Path("/mnt/vendor/mi_ext/") == mi);
        for (const string path : {"", "/mnt/vendor/persist_extra", "/mnt/vendor/nvdata2", "/data/../vendor", "/data/./media"})
            assert(pm.Find_Partition_By_Path(path) == nullptr);
        if (scenario == "paths") {
            auto* nested = add("/data/nested");
            assert(pm.Find_Partition_By_Path("/data/nested/file") == nested);
            auto* alias = add("/other"); alias->Symlink_Mount_Point = "/data/nested";
            assert(pm.Find_Partition_By_Path("/data/nested") == nested);
        } else if (scenario == "dispatch") {
            auto* child = add("/child"); child->Is_SubPartition = true; child->SubPartition_Of = mi->Mount_Point;
            assert(pm.Mount_By_Path("/mnt/vendor/mi_ext/content", true));
            assert(mi->mounts == 1 && child->mounts == 1 && data->mounts == 0);
            assert(pm.UnMount_By_Path("/mnt/vendor/mi_ext/content", true, 7));
            assert(mi->unmounts == 1 && child->unmounts == 1 && mi->last_flags == 7);
            // Canonical mount wins an alias collision in all three APIs.
            auto* collision = add("/other"); collision->Symlink_Mount_Point = mi->Mount_Point;
            assert(pm.Mount_By_Path(mi->Mount_Point, true));
            assert(pm.UnMount_By_Path(mi->Mount_Point, true));
            assert(collision->mounts == 0 && collision->unmounts == 0);
            mi->Symlink_Mount_Point = "/mi_view";
            assert(pm.Find_Partition_By_Path("/mi_view/file") == mi);
            assert(pm.Mount_By_Path("/mi_view/file", true));
            assert(pm.UnMount_By_Path("/mi_view/file", true));
            assert(mi->mounts == 3 && mi->unmounts == 3);
            assert(child->mounts == 3 && child->unmounts == 3);
            assert(pm.Mount_By_Path("/system", true) && system->mounts == 1);
            assert(pm.Mount_By_Path("/sdcard/folder", true) && data->mounts == 1);
            assert(!pm.Mount_By_Path("/mnt/vendor/persist_extra", true));
            assert(!pm.UnMount_By_Path("/mnt/vendor/persist_extra", true));
            assert(!pm.Mount_By_Path("", false));
            assert(pm.Mount_By_Path("/tmp/logs", false));
            assert(!mi->Can_Be_Backed_Up && !mi->Can_Be_Wiped);
        } else {
            assert(pm.Find_Partition_By_Root_Path("/mnt/vendor/nvdata") == nullptr);
            assert(pm.Find_Partition_By_Root_Path("/mnt/vendor/mi_ext") == nullptr);
            assert(pm.Find_Partition_By_Root_Path("/nvdata") == pm.Find_Partition_By_Path("/nvdata"));
            assert(pm.Find_Partition_By_Root_Path("/data/media/0") == data);
            assert(pm.Find_Partition_By_Root_Path("/system/build.prop") == system);
            assert(pm.Find_Partition_By_Root_Path("/data/nested") == data);
        }
    } else if (scenario == "names") {
        auto* part = add("/mnt/vendor/mi_ext", "mi_ext");
        string expected = "mi_ext";
#ifdef AB_OTA_UPDATER
        expected += "_a";
#endif
        assert(pm.Logical_Partition_Name(part, true) == expected);
        assert(pm.Logical_Partition_Name(part, false) == "mi_ext");
        pm.slot = "_b";
#ifdef AB_OTA_UPDATER
        assert(pm.Logical_Partition_Name(part, true) == "mi_ext_b");
#endif
        part->Logical_Partition_Source = "mi_ext_a";
        assert(pm.Logical_Partition_Name(part, true) == "mi_ext_a");
        part->Logical_Partition_Source = "/dev/block/mapper/mi_ext_b";
        assert(pm.Logical_Partition_Name(part, true) == "mi_ext_b");
        part->Logical_Partition_Source = "mi_ext"; part->SlotSelect = false;
        assert(pm.Logical_Partition_Name(part, true) == "mi_ext");
        for (const string& bad : vector<string>{"", "..", "bad:name", string(37, 'x')}) {
            part->Logical_Partition_Source = bad; assert(pm.Logical_Partition_Name(part, true).empty());
        }
    } else if (scenario == "mapping" || scenario == "map_fail" || scenario == "timeout") {
        auto* part = add("/mnt/vendor/mi_ext", "mi_ext");
        if (scenario == "map_fail") fail_updates.insert("mi_ext_a");
        if (scenario == "timeout") ready = false;
        bool ok = pm.Prepare_Super_Volume(part);
        assert(part->Logical_Partition_Source == "mi_ext" && part->Original_Path == "crypto-origin-untouched");
        if (scenario != "mapping") {
            assert(!ok && pm.Super_Partition_List.empty() && part->Mapped_Logical_Partition.empty());
            assert(part->Primary_Block_Device == "mi_ext");
            if (scenario == "timeout") assert(sleeps == 49);
        } else {
            assert(ok && updates.back() == "mi_ext_a" && part->Mapped_Logical_Partition == "mi_ext_a");
            assert(pm.Prepare_Super_Volume(part));
            assert(pm.Super_Partition_List.size() == 1 && links == 1 && unlinks == 0);
            pm.slot = "_b"; assert(pm.Prepare_Super_Volume(part));
            assert(updates.back() == "mi_ext_b" && part->Mapped_Logical_Partition == "mi_ext_b");
            assert(part->Primary_Block_Device == "/virtual-dm/mi_ext_b");
            assert(nodes.at("/dev/block/bootdevice/by-name/mi_ext").target == "/virtual-dm/mi_ext_b");
        }
    } else if (scenario == "unmap" || scenario == "unmount_fail" || scenario == "destroy_fail" || scenario == "cow_fail" || scenario == "foreign_alias") {
        auto* part = add("/mnt/vendor/mi_ext", "mi_ext"); assert(pm.Prepare_Super_Volume(part));
        nodes["/dev/block/mapper/mi_ext_a-cow"] = {S_IFBLK, ""}; pm.slot = "_b";
        if (scenario == "unmount_fail") unmount_ok = false;
        if (scenario == "destroy_fail") fail_destroys.insert("mi_ext_a");
        if (scenario == "cow_fail") fail_destroys.insert("mi_ext_a-cow");
        if (scenario == "foreign_alias") nodes["/dev/block/bootdevice/by-name/mi_ext"] = {S_IFBLK, ""};
        bool ok = pm.Unmap_Super_Devices();
        if (scenario == "unmap" || scenario == "foreign_alias") {
            assert(ok && pm.Partitions.empty() && pm.Super_Partition_List.empty() && deleted_parts == 1);
            assert((destroys == vector<string>{"mi_ext_a", "mi_ext_a-cow"}));
            if (scenario == "unmap") assert(!nodes.count("/dev/block/bootdevice/by-name/mi_ext"));
            else assert(S_ISBLK(nodes.at("/dev/block/bootdevice/by-name/mi_ext").mode));
        } else {
            assert(!ok && pm.Partitions.size() == 1 && deleted_parts == 0);
            assert(part->Logical_Partition_Source == "mi_ext" && part->Mapped_Logical_Partition == "mi_ext_a");
            if (scenario == "unmount_fail") assert(destroys.empty());
            if (scenario == "destroy_fail") assert(destroys == vector<string>{"mi_ext_a"});
        }
    } else if (scenario == "prepare_all") {
        auto* first = add("/mnt/vendor/mi_ext", "mi_ext"); add("/vendor", "vendor"); add("/data");
        fail_updates.insert("mi_ext_a"); assert(!pm.Prepare_All_Super_Volumes());
        assert(pm.Partitions.size() == 3 && pm.Partitions.front() == first && deleted_parts == 0);
        assert(pm.Super_Partition_List == vector<string>{"vendor"});
    } else if (scenario == "views") {
        assert(Recovery_Fstab_View("/mnt/vendor/mi_ext /mi_ext none ro,bind wait,nofail"));
        assert(Recovery_Fstab_View("overlay /product/app overlay ro,lowerdir=/example check,nofail"));
        assert(!Recovery_Fstab_View("mi_ext /mnt/vendor/mi_ext ext4 ro wait,logical,slotselect"));
        assert(!Recovery_Fstab_View("/data f2fs /dev/block/by-name/userdata flags=backup=1"));
        assert(!Recovery_Fstab_View("/dev/block/data /data f2fs noatime wait"));
        assert(!Recovery_Fstab_View("/source /target none ro,rebind wait"));
        assert(!Recovery_Fstab_View("# comment"));
    } else {return 2;}
    reset(); cout << "PASS " << scenario << '\n';
}
'''


class RecoveryLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('g++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable; layout host behavior NOT_TESTED')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        pm, part = image('partitionmanager.cpp'), image('partition.cpp')
        signatures = [
            'TWPartition* TWPartitionManager::Resolve_Partition_Path(',
            'TWPartition* TWPartitionManager::Find_Partition_By_Path(',
            'TWPartition* TWPartitionManager::Find_Partition_By_Root_Path(',
            'int TWPartitionManager::Mount_By_Path(', 'int TWPartitionManager::UnMount_By_Path(',
            'string TWPartitionManager::Logical_Partition_Name(',
            'bool TWPartitionManager::Update_Logical_Alias(',
            'bool TWPartitionManager::Prepare_Super_Volume(',
            'bool TWPartitionManager::Prepare_All_Super_Volumes(',
            'bool TWPartitionManager::Unmap_Super_Devices(',
        ]
        source = COMMON + function(part, 'static bool Recovery_Fstab_View(')
        source += ''.join(function(pm, signature) for signature in signatures) + MAIN
        cpp = cls.root / 'layout.cpp'
        cpp.write_text(source)
        for name, defines in [('ab', ['-DAB_OTA_UPDATER']), ('single', [])]:
            result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                     '-DTW_EXCLUDE_APEX', *defines, str(cpp), '-o', str(cls.root / name)],
                                    capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scenario(self, name, build='ab'):
        result = subprocess.run([str(self.root / build), name], capture_output=True,
                                text=True, check=True, timeout=5)
        self.assertEqual(result.stdout.strip(), 'PASS ' + name)

    def test_exact_and_nested_paths(self):
        self.scenario('paths')

    def test_mount_unmount_dispatch_and_child_behavior(self):
        self.scenario('dispatch')

    def test_storage_operations_keep_legacy_root_boundary(self):
        self.scenario('guard')

    def test_source_slot_and_explicit_suffix(self):
        self.scenario('names')
        self.scenario('names', 'single')

    def test_mapping_remapping_and_owned_alias(self):
        self.scenario('mapping')

    def test_map_error_and_delayed_node_are_not_success(self):
        self.scenario('map_fail')
        self.scenario('timeout')

    def test_unmap_uses_recorded_mapping_not_new_active_slot(self):
        self.scenario('unmap')

    def test_unmap_failures_preserve_identity_and_object(self):
        for scenario in ('unmount_fail', 'destroy_fail', 'cow_fail'):
            self.scenario(scenario)

    def test_foreign_alias_is_preserved(self):
        self.scenario('foreign_alias')

    def test_first_remap_failure_keeps_valid_iterators(self):
        self.scenario('prepare_all')

    def test_android_views_are_classified_not_block_registered(self):
        self.scenario('views')

    def test_source_capture_and_storage_callsite_guards(self):
        part = image('partition.cpp')
        self.assertIn('Primary_Block_Device = ptr;\n\t\t\t\tLogical_Partition_Source = ptr;', part)
        self.assertLess(part.index('if (Recovery_Fstab_View(fstab_line))'), part.index('char full_line['))
        pm = image('partitionmanager.cpp')
        self.assertGreaterEqual(pm.count('Find_Partition_By_Root_Path('), 11)
        self.assertNotIn('Get_Bare_Partition_Name(twrpPart->Get_Mount_Point())', pm)


if __name__ == '__main__':
    unittest.main()
