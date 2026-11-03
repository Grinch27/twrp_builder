# Requirements: all selected backup/restore targets must pass before writes or wipe.
# Ambiguity: virtual block nodes and archive callbacks do not prove device restore.
# Research: compile the actual operation preflight functions from the pinned patch.
# Optimization: reuse the existing layout harness; no devices, mounts or network.
# Risks: aliases, hidden children, missing user keys, invalid archive entries and scope drift.
# Validation: failure propagation, immutable selections, metadata callbacks and ordering.
from pathlib import Path
import shutil
import re
import subprocess
import tempfile
import unittest

from test_copylog_errors import function
from test_recovery_layout import COMMON, image

ROOT = Path(__file__).resolve().parents[1]


def source():
    common = COMMON.replace('struct Node {mode_t mode; string target;};',
                            'struct Node {mode_t mode; string target; dev_t device = 1; off_t bytes = 32;};')
    common = common.replace('out->st_mode = found->second.mode; return 0;',
                            'out->st_mode = found->second.mode; out->st_rdev = found->second.device; '
                            'out->st_size = found->second.bytes; return 0;')
    common = common.replace('struct TWPartition {', '''
#define stat(path, result) fake_lstat(path, result)
static int fbe = 1, archive_calls = 0;
static bool archive_ok = true;
#define TW_IS_FBE "fbe"
struct DataManager {static int GetIntValue(const string&) {return fbe;}};
static void gui_err(const string& value) {gui_msg(value);}
enum {BM_NONE, BM_FILES, BM_DD, BM_FLASH_UTILS};
struct users_struct {string userId; bool isDecrypted;};
struct PartitionSettings {string Backup_Folder;};
struct TWPartition {''')
    common = common.replace('bool Is_Super = false,', '''
    string Backup_Path, Backup_FileName;
    int Backup_Method = BM_FILES;
    bool Is_Present = true, Mount_Read_Only = false, Is_Decrypted = true;
    bool Has_Android_Secure = false, Has_SubPartition = false;
    string Get_Restore_File_System(PartitionSettings*) {
        size_t first = Backup_FileName.find('.'), last = Backup_FileName.find('.', first + 1);
        if (first == string::npos || last == string::npos) return "";
        return Backup_FileName.substr(first + 1, last - first - 1);
    }
    bool Is_File_System(const string& value) {return value == "f2fs" || value == "ext4";}
    bool Is_Image(const string& value) {return value == "emmc";}
    bool Validate_Restore_Archive(const string&) {++archive_calls; return archive_ok;}
    bool Is_Super = false,''')
    common = common.replace('vector<TWPartition*> Partitions;', '''
    vector<users_struct> Users_List = {{"0", true}};
    bool Validate_Backup_Restore_List(const string&, bool, map<string, TWPartition*>*);
    bool Validate_Restore_Files(const map<string, TWPartition*>&, const string&);
    vector<TWPartition*> Partitions;''')
    # Other layout functions referenced by the shared fixture remain link-complete.
    pm = image('partitionmanager.cpp')
    signatures = ['TWPartition* TWPartitionManager::Resolve_Partition_Path(',
                  'TWPartition* TWPartitionManager::Find_Partition_By_Path(',
                  'TWPartition* TWPartitionManager::Find_Partition_By_Root_Path(',
                  'bool TWPartitionManager::Validate_Backup_Restore_List(',
                  'bool TWPartitionManager::Validate_Restore_Files(']
    common = re.sub(r'(?m)^static ', '[[maybe_unused]] static ', common)
    body = function(pm, 'int TWPartitionManager::Run_Backup(')
    start = body.index('if (free_space < (32ULL')
    brace = body.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (body[end] == '{') - (body[end] == '}')
        end += 1
    space = ('bool backup_space(unsigned long long free_space, unsigned long long total_bytes) {'
             + body[start:end] + 'return true;}\n')
    return common + ''.join(function(pm, sig) for sig in signatures) + space


MAIN = r'''
int main(int argc, char** argv) {
    assert(argc == 2); string scenario = argv[1]; auto& pm = PartitionManager;
    auto target = [&](const string& path, dev_t device) {
        auto* part = add(path); part->Backup_Path = path;
        part->Can_Be_Backed_Up = true; part->Actual_Block_Device = "/node" + path;
        part->Backup_FileName = path.substr(1) + ".f2fs.win";
        nodes[part->Actual_Block_Device] = {S_IFBLK, "", device, 4096};
        nodes["/backup/" + part->Backup_FileName] = {S_IFREG, "", 0, 128};
        return part;
    };
    auto* data = target("/data", 1); data->Symlink_Mount_Point = "/sdcard";
    auto* metadata = target("/metadata", 2);
    map<string, TWPartition*> plan;
    string selected = "/data;/metadata;";
    if (scenario == "valid") {
        assert(pm.Validate_Backup_Restore_List(selected, false, &plan));
        assert(plan.size() == 2 && plan.at("/data") == data && plan.at("/metadata") == metadata);
    } else if (scenario == "bad_selection") {
        for (const string list : {"", ";", "/data", "/data;;", "/data;/missing;",
                                 "/data;/sdcard;", "/data/private;", "/data/../metadata;"}) {
            assert(!pm.Validate_Backup_Restore_List(list, false, &plan));
            assert(plan.empty());
        }
    } else if (scenario == "same_device") {
        nodes[metadata->Actual_Block_Device].device = 1;
        assert(!pm.Validate_Backup_Restore_List(selected, false, &plan));
    } else if (scenario == "unavailable") {
        metadata->Is_Present = false;
        assert(!pm.Validate_Backup_Restore_List(selected, false, &plan));
        metadata->Is_Present = true; nodes.erase(metadata->Actual_Block_Device);
        assert(!pm.Validate_Backup_Restore_List(selected, false, &plan));
    } else if (scenario == "capabilities") {
        metadata->Can_Be_Backed_Up = false;
        assert(!pm.Validate_Backup_Restore_List(selected, false, &plan));
        assert(pm.Validate_Backup_Restore_List(selected, true, &plan));
        metadata->Mount_Read_Only = true;
        assert(!pm.Validate_Backup_Restore_List(selected, true, &plan));
    } else if (scenario == "users") {
        data->Is_Decrypted = false;
        assert(!pm.Validate_Backup_Restore_List(selected, false, &plan));
        data->Is_Decrypted = true; pm.Users_List.push_back({"10", false});
        assert(!pm.Validate_Backup_Restore_List(selected, false, &plan));
        pm.Users_List.back().isDecrypted = true;
        assert(pm.Validate_Backup_Restore_List(selected, false, &plan));
        pm.Users_List.clear(); assert(!pm.Validate_Backup_Restore_List(selected, true, &plan));
    } else if (scenario == "children") {
        data->Has_SubPartition = true;
        auto* child = target("/child", 3); child->Is_SubPartition = true; child->SubPartition_Of = "/data";
        assert(pm.Validate_Backup_Restore_List(selected, false, &plan));
        assert(pm.Validate_Restore_Files(plan, "/backup") && archive_calls == 3);
        child->Is_Present = false;
        assert(!pm.Validate_Backup_Restore_List(selected, true, &plan));
    } else if (scenario == "nested_boundary") {
        auto* part = target("/mnt/vendor/nvdata", 3);
        assert(!pm.Validate_Backup_Restore_List(part->Mount_Point + ";", false, &plan));
        target("/nvdata", 3);
        assert(pm.Validate_Backup_Restore_List("/nvdata;", false, &plan));
    } else if (scenario == "archives") {
        assert(pm.Validate_Backup_Restore_List(selected, true, &plan));
        assert(pm.Validate_Restore_Files(plan, "/backup") && archive_calls == 2);
        nodes.erase("/backup/metadata.f2fs.win");
        assert(!pm.Validate_Restore_Files(plan, "/backup"));
        nodes["/backup/metadata.f2fs.win000"] = {S_IFREG, "", 0, 128};
        assert(pm.Validate_Restore_Files(plan, "/backup"));
        nodes["/backup/metadata.f2fs.win000"].bytes = 0;
        assert(!pm.Validate_Restore_Files(plan, "/backup"));
        nodes["/backup/metadata.f2fs.win000"] = {S_IFLNK, "outside", 0, 128};
        assert(!pm.Validate_Restore_Files(plan, "/backup"));
    } else if (scenario == "space") {
        unsigned long long reserve = 32ULL * 1024 * 1024;
        assert(!backup_space(0, 1));
        assert(!backup_space(reserve - 1, 1));
        assert(!backup_space(reserve, 1));
        assert(backup_space(reserve + 100, 100));
        assert(!backup_space(reserve + 100, 101));
    } else if (scenario == "archive_error") {
        assert(pm.Validate_Backup_Restore_List(selected, true, &plan)); archive_ok = false;
        assert(!pm.Validate_Restore_Files(plan, "/backup"));
        archive_ok = true; data->Backup_FileName = "../outside";
        assert(!pm.Validate_Restore_Files(plan, "/backup"));
    } else return 2;
    assert(data->mounts == 0 && data->unmounts == 0 && metadata->mounts == 0);
    reset(); cout << "PASS " << scenario << '\n';
}
'''


class BackupPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('g++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable; backup plan NOT_TESTED')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        path = cls.root / 'plan.cpp'
        path.write_text(source() + MAIN)
        result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra',
                                 '-Werror', str(path), '-o', str(cls.root / 'plan')],
                                capture_output=True, text=True, timeout=40)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name):
        result = subprocess.run([str(self.root / 'plan'), name], text=True,
                                capture_output=True, check=True, timeout=5)
        self.assertEqual(result.stdout.strip(), 'PASS ' + name)

    def test_selection_and_no_write_side_effects(self):
        for name in ('valid', 'bad_selection', 'same_device', 'unavailable', 'capabilities'):
            self.run_case(name)

    def test_fbe_users_and_implicit_children(self):
        for name in ('users', 'children'):
            self.run_case(name)

    def test_nested_write_boundary_remains(self):
        self.run_case('nested_boundary')

    def test_all_archive_entries_and_callback_failures(self):
        for name in ('archives', 'archive_error'):
            self.run_case(name)

    def test_real_space_branch_has_no_unsigned_underflow(self):
        self.run_case('space')

    def test_preflight_precedes_storage_and_execution_uses_fixed_plan(self):
        pm = image('partitionmanager.cpp')
        for signature, operation in [('int TWPartitionManager::Run_Backup(', 'Backup_Partition('),
                                     ('int TWPartitionManager::Run_Restore(', 'Restore_Partition(')]:
            body = function(pm, signature)
            self.assertLess(body.index('Validate_Backup_Restore_List('), body.index('Mount_Current_Storage('))
            self.assertLess(body.index('Validate_Backup_Restore_List('), body.index(operation))
            self.assertEqual(body.count('selection.at('), 2)
        restore = function(pm, 'int TWPartitionManager::Run_Restore(')
        self.assertLess(restore.index('Validate_Restore_Files('), restore.index('Restore_Partition('))
        self.assertIn('check_digest > 0 && !twrpDigestDriver::Check_Digest(Child_Filename)', restore)
        self.assertIn('(*subpart)->Backup_FileName', restore)
        self.assertIn('free_space < (32ULL * 1024 * 1024)', function(pm, 'int TWPartitionManager::Run_Backup('))


if __name__ == '__main__':
    unittest.main()
