# Requirements: guard the locked real vold function without persistent key writes.
# Ambiguity: host mocks cannot verify a vendor Keymaster or resolve device error -33.
# Research: keep successful non-upgrade operations out of the optional upgrade branch.
# Optimization: compile only the pinned public function with filesystem boundaries.
# Risks: fixed /tmp paths are redirected into the test sandbox; no device access.
# Validation: begin failure, no-upgrade success, upgrade success, write failure and negative control.
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Public upstream fixture: TeamWin/android_system_vold@a164ba05c5fef288059774a776b2e6e1119957cf
# KeyStorage.cpp BeginKeymasterOp; one whitespace-only line normalized before patching.
PINNED_FUNCTION = r'''static KeymasterOperation BeginKeymasterOp(Keymaster& keymaster, const std::string& dir,
                                           const km::AuthorizationSet& keyParams,
                                           const km::AuthorizationSet& opParams,
                                           km::AuthorizationSet* outParams) {
    km::AuthorizationSet inParams(keyParams);
    inParams.append(opParams.begin(), opParams.end());

    auto blob_file = dir + "/" + kFn_keymaster_key_blob;
    LOG(INFO) << "reading blob_file: " << blob_file;
    std::string blob_dir(kFn_keymaster_key_blob);
    std::string temp_dir = "/tmp/" + blob_dir + "/";
    if (TEMP_FAILURE_RETRY(mkdir(temp_dir.c_str(), 0700)) == -1) {
        PLOG(ERROR) << "key mkdir " << temp_dir;
    }
    auto upgraded_blob_file = temp_dir + kFn_keymaster_key_blob;
    // auto upgraded_blob_file = dir + "/" + kFn_keymaster_key_blob_upgraded;
    std::lock_guard<std::mutex> lock(key_upgrade_lock);

    std::string blob;
    // bool already_upgraded = IsKeyCommitPending(dir);
    // if (already_upgraded) {
    //     LOG(INFO)
    //             << blob_file
    //             << " was already upgraded and is waiting to be committed; using the upgraded blob";
    //     if (!readFileToString(upgraded_blob_file, &blob)) return KeymasterOperation();
    // } else {
        // DeleteUpgradedKey(keymaster, upgraded_blob_file);
    if (!readFileToString(blob_file, &blob)) return KeymasterOperation();
    // }
    auto opHandle = keymaster.begin(blob, inParams, outParams);
    if (!opHandle) return opHandle;

    // If key blob wasn't upgraded, nothing left to do.
    // if (!opHandle.getUpgradedBlob()) return opHandle;

    // if (already_upgraded) {
    //     LOG(ERROR) << "Unexpected case; already-upgraded key " << upgraded_blob_file
    //                << " still requires upgrade";
    //     return KeymasterOperation();
    // }
    LOG(INFO) << "Upgrading key: " << blob_file;

    if (!writeStringToFile(*opHandle.getUpgradedBlob(), upgraded_blob_file))
        return KeymasterOperation();
    // if (cp_needsCheckpoint()) {
    //     LOG(INFO) << "Wrote upgraded key to " << upgraded_blob_file
    //               << "; delaying commit due to checkpoint";
    //     ScheduleKeyCommit(dir);
    // } else {
    //     if (!CommitUpgradedKey(keymaster, dir)) return KeymasterOperation();
    //     LOG(INFO) << "Key upgraded: " << blob_file;
    // }
    return opHandle;
}
'''

HARNESS = r'''
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace km {
struct AuthorizationSet {
    std::vector<int> values;
    auto begin() const { return values.begin(); }
    auto end() const { return values.end(); }
    template<class Iterator> void append(Iterator first, Iterator last) {
        values.insert(values.end(), first, last);
    }
};
}
struct KeymasterOperation {
    bool valid = false;
    std::optional<std::string> upgraded;
    explicit operator bool() const { return valid; }
    const std::optional<std::string>& getUpgradedBlob() const { return upgraded; }
};
static int scenario;
static int begins = 0;
static int writes = 0;
static std::string sandbox;
static std::string last_write;
static const char* kFn_keymaster_key_blob = "keymaster_key_blob";
static std::mutex key_upgrade_lock;

struct Keymaster {
    KeymasterOperation begin(const std::string& blob, const km::AuthorizationSet& params,
                             km::AuthorizationSet*) {
        ++begins;
        assert(blob == "original persistent blob");
        assert((params.values == std::vector<int>{7, 11}));
        if (scenario == 0) return {};
        if (scenario == 1) return {true, std::nullopt};
        return {true, "ephemeral upgraded blob"};
    }
};
static bool readFileToString(const std::string& path, std::string* value) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return false;
    value->assign(std::istreambuf_iterator<char>(input), {});
    return true;
}
static int fakeMkdir(const char* path, unsigned) {
    assert(std::string(path) == "/tmp/keymaster_key_blob/");
    std::filesystem::create_directories(sandbox + path);
    return 0;
}
static bool writeStringToFile(const std::string& value, const std::string& path) {
    ++writes;
    last_write = path;
    assert(path == "/tmp/keymaster_key_blob/keymaster_key_blob");
    if (scenario == 3) return false;
    std::ofstream output(sandbox + path, std::ios::binary);
    output << value;
    return output.good();
}
#define mkdir fakeMkdir
#define TEMP_FAILURE_RETRY(expression) (expression)
#define LOG(level) std::cerr
#define PLOG(level) std::cerr

__PINNED_FUNCTION__

int main(int argc, char** argv) {
    assert(argc == 4);
    scenario = std::stoi(argv[1]);
    sandbox = argv[2];
    const std::string original_dir = argv[3];
    Keymaster keymaster;
    km::AuthorizationSet key_params{{7}};
    km::AuthorizationSet op_params{{11}};
    auto result = BeginKeymasterOp(keymaster, original_dir, key_params, op_params, nullptr);
    std::cout << "valid=" << bool(result) << " begins=" << begins
              << " writes=" << writes << " path=" << last_write << '\n';
    return 0;
}
'''


class KeyStorageGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('host C++ compiler unavailable; Android/device test not inferred')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        upstream = cls.root / 'KeyStorage.cpp'
        upstream.write_text(PINNED_FUNCTION)
        patch = ROOT / 'patches/vold-key-storage-guard.patch'
        check = subprocess.run(['git', 'apply', '--check', str(patch)], cwd=cls.root,
                               capture_output=True, text=True, timeout=5)
        if check.returncode:
            cls.temporary.cleanup()
            raise AssertionError(check.stderr)
        applied = subprocess.run(['git', 'apply', str(patch)], cwd=cls.root,
                                 capture_output=True, text=True, timeout=5)
        if applied.returncode:
            cls.temporary.cleanup()
            raise AssertionError(applied.stderr)
        cls.binaries = {}
        for name, body in [('patched', upstream.read_text()), ('unpatched', PINNED_FUNCTION)]:
            source = cls.root / (name + '.cpp')
            source.write_text(HARNESS.replace('__PINNED_FUNCTION__', body))
            binary = cls.root / name
            result = subprocess.run([compiler, '-std=c++17', '-D_GLIBCXX_ASSERTIONS',
                                     '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                cls.temporary.cleanup()
                raise AssertionError(result.stderr)
            cls.binaries[name] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self, scenario, variant='patched'):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root = Path(directory)
            original = root / 'metadata' / 'vold' / 'metadata_encryption' / 'key'
            original.mkdir(parents=True)
            key = original / 'keymaster_key_blob'
            key.write_bytes(b'original persistent blob')
            before = {str(f.relative_to(original)): f.read_bytes()
                      for f in original.rglob('*') if f.is_file()}
            # The negative control aborts on an empty optional; suppress any core file.
            environment = dict(os.environ)
            program = 'ulimit -c 0; exec "$@"'
            result = subprocess.run(['bash', '-c', program, 'guard-harness',
                                     str(self.binaries[variant]), str(scenario),
                                     str(root / 'sandbox'), str(original)],
                                    capture_output=True, text=True, timeout=5, env=environment)
            after = {str(f.relative_to(original)): f.read_bytes()
                     for f in original.rglob('*') if f.is_file()}
            self.assertEqual(before, after, 'persistent metadata fixture changed')
            temporary_key = root / 'sandbox/tmp/keymaster_key_blob/keymaster_key_blob'
            payload = temporary_key.read_bytes() if temporary_key.exists() else None
            return result, payload

    def test_begin_failure_returns_without_upgrade_or_write(self):
        result, payload = self.run_case(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'valid=0 begins=1 writes=0 path=\n')
        self.assertIsNone(payload)

    def test_success_without_upgrade_preserves_operation_and_original_key(self):
        result, payload = self.run_case(1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'valid=1 begins=1 writes=0 path=\n')
        self.assertIsNone(payload)

    def test_real_upgrade_writes_only_existing_temporary_destination(self):
        result, payload = self.run_case(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'valid=1 begins=1 writes=1 '
                         'path=/tmp/keymaster_key_blob/keymaster_key_blob\n')
        self.assertEqual(payload, b'ephemeral upgraded blob')

    def test_upgrade_write_failure_returns_failure_and_preserves_original(self):
        result, payload = self.run_case(3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'valid=0 begins=1 writes=1 '
                         'path=/tmp/keymaster_key_blob/keymaster_key_blob\n')
        self.assertIsNone(payload)

    def test_unpatched_locked_function_fails_the_nonupgrade_case(self):
        result, payload = self.run_case(1, 'unpatched')
        self.assertNotEqual(result.returncode, 0,
                            'negative control must exercise the empty optional dereference')
        self.assertIsNone(payload)


if __name__ == '__main__':
    unittest.main()
