# Requirements: propagate real CopyLog export failures without creating fallback storage.
# Ambiguity: host execution does not establish Android compilation or device FBE success.
# Research: exercise functions from the patch against the locked public Recovery API.
# Optimization: compile two small harnesses once, using actual streams for I/O failures.
# Risks: missing storage, command failure, buffered disk errors and stale success gui_messages.
# Validation: GUI status, skipped downstream actions, empty logs and /dev/full failures.
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def patched_file(path):
    """Read the resulting changed functions, including context, from the real patch."""
    lines = (ROOT / 'patches/recovery-copylog-errors.patch').read_text().splitlines(True)
    selected = False
    result = []
    for line in lines:
        if line.startswith('diff --git '):
            selected = line.rstrip().endswith(' b/' + path)
        elif selected and not line.startswith(('+++', '---', '@@')):
            if line.startswith((' ', '+')):
                result.append(line[1:])
    return ''.join(result)


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1] + '\n'
    raise AssertionError('Incomplete patched function: ' + signature)


COMMON = r'''
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <vector>
using namespace std;
#define __unused __attribute__((unused))
#define LOGERR(...) do {} while (0)
#define LOGINFO(...) do {} while (0)
static vector<string> gui_messages;
static int metadata_calls = 0;
struct Msg {
    string text;
    explicit Msg(string value): text(value) {}
    string operator()(string value) const { return text + value; }
};
static void gui_msg(const string& text) { gui_messages.push_back(text); }
static void tw_set_default_metadata(const char*) { ++metadata_calls; }
'''

ACTION_STUBS = r'''
static bool mount_ok = true, path_exists = true, kernel_ok = true, logcat_ok = true;
static int copy_result = 0, kernel_option = 1, logcat_option = 1;
static int copy_calls = 0, kernel_calls = 0, logcat_calls = 0, status = -1;
static string storage = "/selected/storage";
struct PartitionManagerStub {
    bool Mount_Current_Storage(bool) { return mount_ok; }
} PartitionManager;
struct DataManager {
    static void GetValue(string name, int& value) {
        value = name == "tw_include_kernel_log" ? kernel_option : logcat_option;
    }
    static string GetCurrentStoragePath() { return storage; }
};
struct TWFunc {
    static bool Path_Exists(string) { return path_exists; }
    static int copy_file(string, string, int, bool) { ++copy_calls; return copy_result; }
    static bool copy_kernel_log(string) { ++kernel_calls; return kernel_ok; }
    static bool copy_logcat(string) { ++logcat_calls; return logcat_ok; }
};
static void sync() {}
class GUIAction {
public:
    bool simulate = false;
    void operation_start(string) {}
    void operation_end(int value) { status = value; }
    void simulate_progress_bar() {}
    int copylog(string);
};
'''
ACTION_MAIN = r'''
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    string scenario = argv[1];
    GUIAction action;
    if (scenario == "mount_fail") mount_ok = false;
    if (scenario == "missing_storage") path_exists = false;
    if (scenario == "empty_storage") storage.clear();
    if (scenario == "copy_fail") copy_result = -1;
    if (scenario == "kernel_fail") kernel_ok = false;
    if (scenario == "logcat_fail") logcat_ok = false;
    if (scenario == "disabled") { kernel_option = 0; logcat_option = 0; }
    if (scenario == "simulate") action.simulate = true;
    int result = action.copylog("");
    int recovery_success = 0;
    for (auto& text: gui_messages) if (text.find("copy_log=") == 0) ++recovery_success;
    cout << result << ' ' << status << ' ' << copy_calls << ' ' << kernel_calls
         << ' ' << logcat_calls << ' ' << recovery_success << ' ' << metadata_calls;
}
'''
IO_STUBS = r'''
static int command_result = 0;
static string command_output = "complete captured log\n";
struct PartitionManagerStub {
    bool Mount_By_Path(string, bool) { return true; }
} PartitionManager;
struct TWFunc {
    static bool Path_Exists(string path) { struct stat st; return stat(path.c_str(), &st) == 0; }
    static int Exec_Cmd(const string&, string& result, bool) { result = command_output; return command_result; }
    static int copy_file(string, string, int, bool);
    static bool copy_kernel_log(string);
    static bool copy_logcat(string);
};
'''
IO_MAIN = r'''
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    string scenario = argv[1], src = argv[2], dst = argv[3];
    int result = -99;
    if (scenario == "copy") result = TWFunc::copy_file(src, dst, 0600, false);
    if (scenario == "write") result = write_log_file(dst, src) ? 0 : -1;
    if (scenario == "kernel_fail" || scenario == "logcat_fail") command_result = 1;
    if (scenario == "kernel_fail" || scenario == "kernel" || scenario == "kernel_empty") {
        if (scenario == "kernel_empty") command_output.clear();
        result = TWFunc::copy_kernel_log(dst) ? 0 : -1;
    }
    if (scenario == "logcat_fail" || scenario == "logcat") result = TWFunc::copy_logcat(dst) ? 0 : -1;
    cout << result << ' ' << gui_messages.size() << ' ' << metadata_calls;
}
'''


class CopyLogErrorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('g++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable; host behavior NOT_TESTED')
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        action = function(patched_file('gui/action.cpp'), 'int GUIAction::copylog(')
        cpp = patched_file('twrp-functions.cpp')
        io_functions = ''.join(function(cpp, signature) for signature in [
            'int TWFunc::copy_file(', 'static bool write_log_file(',
            'bool TWFunc::copy_kernel_log(', 'bool TWFunc::copy_logcat('])
        for name, source in [('action', COMMON + ACTION_STUBS + action + ACTION_MAIN),
                             ('io', COMMON + IO_STUBS + io_functions + IO_MAIN)]:
            path = cls.directory / (name + '.cpp')
            path.write_text(source)
            result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra',
                                     '-Werror', str(path), '-o', str(cls.directory / name)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def action(self, scenario):
        result = subprocess.run([str(self.directory / 'action'), scenario],
                                capture_output=True, text=True, timeout=5, check=True)
        return tuple(map(int, result.stdout.split()))

    def io(self, scenario, src, dst):
        result = subprocess.run([str(self.directory / 'io'), scenario, str(src), str(dst)],
                                capture_output=True, text=True, timeout=5, check=True)
        return tuple(map(int, result.stdout.split()))

    def test_unavailable_mount_stops_before_export_and_reports_failure(self):
        self.assertEqual(self.action('mount_fail'), (0, 1, 0, 0, 0, 0, 0))

    def test_missing_or_empty_storage_stops_without_fallback_directory(self):
        for scenario in ['missing_storage', 'empty_storage']:
            with self.subTest(scenario=scenario):
                self.assertEqual(self.action(scenario), (0, 1, 0, 0, 0, 0, 0))

    def test_recovery_copy_failure_stops_captures_and_success_gui_messages(self):
        self.assertEqual(self.action('copy_fail'), (0, 1, 1, 0, 0, 0, 0))

    def test_each_requested_capture_failure_marks_operation_failed(self):
        for scenario in ['kernel_fail', 'logcat_fail']:
            with self.subTest(scenario=scenario):
                self.assertEqual(self.action(scenario), (0, 1, 1, 1, 1, 1, 1))

    def test_success_and_disabled_options_preserve_gui_action_convention(self):
        self.assertEqual(self.action('success'), (0, 0, 1, 1, 1, 1, 1))
        self.assertEqual(self.action('disabled'), (0, 0, 1, 0, 0, 1, 1))
        self.assertEqual(self.action('simulate'), (0, 0, 0, 0, 0, 0, 0))

    def test_copy_preserves_bytes_and_accepts_empty_source(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = Path(temp) / 'src', Path(temp) / 'dst'
            for data in [b'complete recovery log\x00\xff\n', b'']:
                src.write_bytes(data)
                self.assertEqual(self.io('copy', src, dst), (0, 0, 0))
                self.assertEqual(dst.read_bytes(), data)
                self.assertEqual(dst.stat().st_mode & 0o777, 0o600)

    def test_missing_source_and_unopenable_destination_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(self.io('copy', root / 'missing', root / 'out')[0], -1)
            src = root / 'src'; src.write_text('recovery log')
            self.assertEqual(self.io('copy', src, root / 'missing' / 'out')[0], -1)

    def test_buffered_copy_and_log_write_errors_are_reported(self):
        if not Path('/dev/full').exists():
            self.skipTest('/dev/full unavailable')
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'src'; src.write_text('small buffered recovery log')
            self.assertEqual(self.io('copy', src, '/dev/full')[0], -1)
            self.assertEqual(self.io('write', 'small buffered capture', '/dev/full')[0], -1)

    def test_capture_command_failure_does_not_create_file_or_success_message(self):
        with tempfile.TemporaryDirectory() as temp:
            for scenario, filename in [('kernel_fail', 'dmesg.log'), ('logcat_fail', 'logcat.txt')]:
                with self.subTest(scenario=scenario):
                    self.assertEqual(self.io(scenario, '', temp), (-1, 0, 0))
                    self.assertFalse((Path(temp) / filename).exists())

    def test_capture_write_failure_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.io('kernel', '', Path(temp) / 'missing'), (-1, 0, 0))
            if Path('/dev/full').exists():
                (Path(temp) / 'logcat.txt').symlink_to('/dev/full')
                self.assertEqual(self.io('logcat', '', temp), (-1, 0, 0))

    def test_capture_success_reports_only_completed_files_and_allows_empty_buffer(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.io('kernel', '', temp), (0, 1, 1))
            self.assertEqual((Path(temp) / 'dmesg.log').read_text(), 'complete captured log\n')
            self.assertEqual(self.io('logcat', '', temp), (0, 1, 1))
            self.assertEqual((Path(temp) / 'logcat.txt').read_text(), 'complete captured log\n')
            self.assertEqual(self.io('kernel_empty', '', temp), (0, 1, 1))
            self.assertEqual((Path(temp) / 'dmesg.log').read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()
