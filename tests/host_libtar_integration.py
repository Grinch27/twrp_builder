# Requirements: full pinned libtar with synthetic security callbacks and real temporary I/O.
# Ambiguity: host libc and callback policies do not prove Android or hardware behavior.
# Research: compile actual combined C sources, preserving the existing archive writer.
# Optimization: local public checkout only; no source downloads or device access.
# Risks: host headers differ; shims and fixtures are generated only in temporary dirs.
# Validation: full-library create/read-only-preflight/extract and v1/v2 byte round trips.
from pathlib import Path
import argparse
import subprocess
import sys
import tempfile
parser = argparse.ArgumentParser(description='Verify patched public libtar with synthetic security callbacks.')
parser.add_argument('--source', type=Path, required=True, help='Pinned bootable/recovery checkout after patches')
args = parser.parse_args()
source = args.source.resolve()
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if revision != '5c3d206a5eeb3d446bcda8248a405a4b278bab5c':
    raise SystemExit('Unsupported public Recovery revision')
workspace = tempfile.TemporaryDirectory(prefix='selene-libtar-')
base = Path(workspace.name)
root = source / 'libtar'
out = base / 'host'
out.mkdir()
for name in ['sys','selinux']:(out/name).mkdir(exist_ok=True)
(out/'sys/capability.h').write_text('#include <linux/capability.h>\n')
(out/'selinux/selinux.h').write_text('''#pragma once
#include <stddef.h>
typedef char* security_context_t;
int lgetfilecon(const char*, char**);
int lsetfilecon(const char*, const char*);
void freecon(char*);
''')
(out/'fscrypt_policy.h').write_text('''#pragma once
#include <linux/fscrypt.h>
#undef fscrypt_policy
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef union fscrypt_policy {uint8_t version;struct fscrypt_policy_v1 v1;struct fscrypt_policy_v2 v2;} fscrypt_policy;
#define USER_CE_FSCRYPT_POLICY "CE"
#define USER_DE_FSCRYPT_POLICY "DE"
#define SYSTEM_DE_FSCRYPT_POLICY "DK"
bool fscrypt_policy_get_struct(const char*,fscrypt_policy*);
bool fscrypt_policy_set_struct(const char*,fscrypt_policy*);
bool lookup_ref_key(fscrypt_policy*,uint8_t*);
bool lookup_ref_tar(fscrypt_policy*,uint8_t*);
uint8_t* get_policy_descriptor(fscrypt_policy*);
uint8_t get_policy_size(fscrypt_policy*,bool);
void* get_policy(const fscrypt_policy*);
int fscrypt_policy_size(const fscrypt_policy*);
void get_policy_content(fscrypt_policy*,char*);
void bytes_to_hex(const uint8_t*,size_t,char*);
''')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_backup_metadata import COMMON
start=COMMON.index('static int query_error');end=COMMON.index('static char* th_get_pathname')
snippet=COMMON[start:end]
for name in ['get_policy_descriptor','fscrypt_policy_size','get_policy','get_policy_size','bytes_to_hex','fscrypt_policy_get_struct','fscrypt_policy_set_struct','lookup_ref_key','lookup_ref_tar']:
 import re
 snippet=re.sub(r'static ([^\n]+?\b'+name+r'\()',r'\1',snippet)
snippet+='''
int lgetfilecon(const char* path,char** out) {(void)path;*out=strdup("u:object_r:fixture:s0");return strlen(*out);}
int lsetfilecon(const char* path,const char* value) {(void)path;(void)value;return 0;}
void freecon(char* path) {free(path);}
void get_policy_content(fscrypt_policy* p,char* out) {(void)p;strcpy(out,"fixture");}
size_t strlcpy(char* dst,const char* src,size_t size) {size_t n=strlen(src);if(size){size_t c=n>=size?size-1:n;memcpy(dst,src,c);dst[c]=0;}return n;}
size_t strlcat(char* dst,const char* src,size_t size) {size_t n=strnlen(dst,size);if(n==size)return size+strlen(src);return n+strlcpy(dst+n,src,size-n);}
'''
header='''#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include "fscrypt_policy.h"
#include "libtar.h"
'''
main=r'''
int main(int argc,char**argv) {
 if(argc==6){TAR* check=NULL;assert(tar_open(&check,argv[1],NULL,O_RDONLY,0,TAR_GNU|TAR_STORE_FSCRYPT_POL|TAR_REQUIRE_FSCRYPT_POL)==0);int result=tar_validate_all(check,argv[3],argv[3]);tar_close(check);return result==0?0:1;}
 assert(argc==5);int version=atoi(argv[4]);TAR* t=NULL;
 present=true;current=make_policy(version);
 assert(tar_open(&t,argv[1],NULL,O_WRONLY|O_CREAT|O_EXCL,0600,TAR_GNU|TAR_STORE_FSCRYPT_POL|TAR_STORE_SELINUX)==0);
 char source[4096];snprintf(source,sizeof(source),"%s/dir",argv[2]);
 assert(tar_append_file(t,source,"dir")==0);
 snprintf(source,sizeof(source),"%s/dir/file",argv[2]);assert(tar_append_file(t,source,"dir/file")==0);
 assert(tar_append_eof(t)==0);assert(tar_close(t)==0);
 present=false;query_error=ENODATA;
 assert(tar_open(&t,argv[1],NULL,O_RDONLY,0,TAR_GNU|TAR_STORE_FSCRYPT_POL|TAR_REQUIRE_FSCRYPT_POL)==0);
 assert(tar_validate_all(t,argv[3],argv[3])==0);assert(policy_writes==0);assert(tar_close(t)==0);
 struct stat st;char dest[4096];snprintf(dest,sizeof(dest),"%s/dir",argv[3]);assert(lstat(dest,&st)==-1 && errno==ENOENT);
 assert(tar_open(&t,argv[1],NULL,O_RDONLY,0,TAR_GNU|TAR_STORE_FSCRYPT_POL|TAR_REQUIRE_FSCRYPT_POL)==0);
 int progress=open("/dev/null",O_WRONLY);assert(progress>=0);
 assert(tar_extract_all(t,argv[3],&progress)==0);close(progress);assert(tar_close(t)==0);
 snprintf(dest,sizeof(dest),"%s/dir/file",argv[3]);assert(stat(dest,&st)==0);assert((st.st_mode&0777)==0640);
 puts("HOST_LIBTAR_ROUNDTRIP_PASS");return 0;
}
'''
(out/'host.c').write_text(header+snippet+main)
files=['append.c','block.c','decode.c','encode.c','extract.c','handle.c','output.c','util.c','wrapper.c','basename.c','strmode.c','libtar_hash.c','libtar_list.c','dirname.c','android_utils.c']
cmd=['gcc','-std=gnu11','-D_GNU_SOURCE','-DUSE_FSCRYPT','-D__unused=__attribute__((unused))','-I'+str(out),'-I'+str(root),*[str(root/x) for x in files],str(out/'host.c'),'-o',str(out/'roundtrip')]
r=subprocess.run(cmd,text=True,capture_output=True,timeout=40)
(out/'compile.log').write_text(r.stdout+r.stderr)
if r.returncode:print((r.stderr)[-6500:]);raise SystemExit(r.returncode)
print('Full libtar host build passed')

old = base / 'legacy'
old.mkdir()
for path in root.iterdir():
    if path.is_file() and path.suffix in ('.c', '.h'):
        data = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:libtar/' + path.name])
        (old / path.name).write_bytes(data)
legacy = (out / 'host.c').read_text()
legacy = legacy.replace('#include "libtar.h"', '#include "libtar.h"\n#define TAR_REQUIRE_FSCRYPT_POL 4096\n#define tar_validate_all(a,b,c) 0')
legacy = legacy.replace(' present=false;query_error=ENODATA;', ' return 0;\n present=false;query_error=ENODATA;')
(out / 'legacy.c').write_text(legacy)
command = ['gcc', '-std=gnu11', '-D_GNU_SOURCE', '-DUSE_FSCRYPT',
           '-D__unused=__attribute__((unused))', '-include', 'stdio.h',
           '-I' + str(out), '-I' + str(old), *[str(old / name) for name in files],
           str(out / 'legacy.c'), '-o', str(out / 'legacy-writer')]
result = subprocess.run(command, capture_output=True, text=True, timeout=40)
if result.returncode:
    print(result.stderr[-6500:])
    raise SystemExit(result.returncode)
for version in (0, 2):
    directory = base / ('policy-' + str(version))
    original, restored, untouched = directory / 'src', directory / 'dst', directory / 'untouched'
    (original / 'dir').mkdir(parents=True)
    restored.mkdir()
    untouched.mkdir()
    payload = original / 'dir/file'
    payload.write_bytes(bytes(range(256)) * 200)
    payload.chmod(0o640)
    archive = directory / 'archive.tar'
    for program, destination in [('legacy-writer', directory / 'legacy.tar'), ('roundtrip', archive)]:
        result = subprocess.run([str(out / program), str(destination), str(original), str(restored), str(version)],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            print(result.stdout[-2000:], result.stderr[-2000:])
            raise SystemExit(result.returncode)
    actual = restored / 'dir/file'
    assert payload.read_bytes() == actual.read_bytes()
    assert payload.stat().st_uid == actual.stat().st_uid
    assert payload.stat().st_gid == actual.stat().st_gid
    assert payload.stat().st_mode == actual.stat().st_mode
    assert archive.read_bytes() == (directory / 'legacy.tar').read_bytes()
    broken = directory / 'broken.tar'
    data = archive.read_bytes()
    broken.write_bytes(data[:len(data) // 2])
    result = subprocess.run([str(out / 'roundtrip'), str(broken), str(original), str(untouched), str(version), 'validate'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and not list(untouched.iterdir())
    print('LIBTAR_POLICY_VERSION=' + str(version) + ' ROUNDTRIP=PASS LEGACY_BYTES=PASS TRUNCATION_NO_WRITE=PASS')
workspace.cleanup()
