# Requirements: preserve archive policies and propagate required metadata failures.
# Ambiguity: simulated fscrypt/SELinux callbacks do not validate the phone kernel or keys.
# Research: execute actual changed C functions with the locked policy union ABI.
# Optimization: one C harness with real temporary directories; no mounts or network.
# Risks: binary PAX, unknown policies, existing directories, missing keys and false success.
# Validation: v1/v2, legitimate ENODATA, error classes, read-only preflight and I/O failures.
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_copylog_errors import function

ROOT = Path(__file__).resolve().parents[1]


def postimage(path, patch='recovery-backup-integrity.patch'):
    selected, lines = False, []
    for line in (ROOT / 'patches' / patch).read_text().splitlines(True):
        if line.startswith('diff --git '):
            selected = line.rstrip().endswith(' b/' + path)
        elif selected and not line.startswith(('+++', '---', '@@')):
            if line.startswith((' ', '+')):
                lines.append(line[1:])
    return ''.join(lines)


COMMON = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/fscrypt.h>
#undef fscrypt_policy
#include <linux/capability.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#define USE_FSCRYPT 1
#define MAXPATHLEN 4096
#define LOG(...) do {} while(0)
#define TAR_GNU 1
#define TAR_VERBOSE 2
#define TAR_NOOVERWRITE 4
#define TAR_STORE_SELINUX 128
#define TAR_STORE_FSCRYPT_POL 512
#define TAR_STORE_POSIX_CAP 1024
#define TAR_STORE_ANDROID_USER_XATTR 2048
#define TAR_REQUIRE_FSCRYPT_POL 4096
#define LNKTYPE '1'
#define USER_CE_FSCRYPT_POLICY "CE"
#define USER_DE_FSCRYPT_POLICY "DE"
#define SYSTEM_DE_FSCRYPT_POLICY "DK"
#define FSCRYPT_TAG "TWRP.security.fscrypt="
#define FSCRYPT_TAG_LEN strlen(FSCRYPT_TAG)
#define CAPABILITIES_TAG "SCHILY.xattr.security.capability="
#define CAPABILITIES_TAG_LEN strlen(CAPABILITIES_TAG)
#define SELINUX_TAG "RHT.security.selinux="
#define SELINUX_TAG_LEN strlen(SELINUX_TAG)
#define ANDROID_USER_DEFAULT_TAG "ANDROID.user.default"
#define ANDROID_USER_DEFAULT_TAG_LEN strlen(ANDROID_USER_DEFAULT_TAG)
#define ANDROID_USER_CACHE_TAG "ANDROID.user.inode_cache"
#define ANDROID_USER_CACHE_TAG_LEN strlen(ANDROID_USER_CACHE_TAG)
#define ANDROID_USER_CODE_CACHE_TAG "ANDROID.user.inode_code_cache"
#define ANDROID_USER_CODE_CACHE_TAG_LEN strlen(ANDROID_USER_CODE_CACHE_TAG)
typedef union fscrypt_policy {uint8_t version; struct fscrypt_policy_v1 v1; struct fscrypt_policy_v2 v2;} fscrypt_policy;
struct tar_header {
    char typeflag, name[4096]; mode_t mode; fscrypt_policy* fep;
    char* selinux_context; int has_cap_data; struct vfs_cap_data cap_data;
    int has_user_default, has_user_cache, has_user_code_cache;
};
typedef struct {int options; struct tar_header th_buf; void* h;} TAR;
#define TH_ISDIR(t) ((t)->th_buf.typeflag == '5')
#define TH_ISREG(t) ((t)->th_buf.typeflag == '0')
#define TH_ISSYM(t) ((t)->th_buf.typeflag == '2')
#define TH_ISLNK(t) ((t)->th_buf.typeflag == '1')
#define TH_ISCHR(t) ((t)->th_buf.typeflag == '3')
#define TH_ISBLK(t) ((t)->th_buf.typeflag == '4')
#define TH_ISFIFO(t) ((t)->th_buf.typeflag == '6')
static int query_error = ENODATA, lookup_error, key_prefix_error, set_policy_error;
static int label_get_error, label_set_error, cap_set_error, append_error;
static int writes, policy_writes, file_writes, mismatch_readback;
static bool present;
static fscrypt_policy current;
static fscrypt_policy make_policy(int version) {
    fscrypt_policy p = {0}; p.version = version;
    if(version == FSCRYPT_POLICY_V1) {p.v1.contents_encryption_mode=1; p.v1.filenames_encryption_mode=4; memset(p.v1.master_key_descriptor, 7, 8);}
    else {p.v2.contents_encryption_mode=1; p.v2.filenames_encryption_mode=4; memset(p.v2.master_key_identifier, 7, 16);}
    return p;
}
static uint8_t* get_policy_descriptor(fscrypt_policy* p) {return p->version==0?p->v1.master_key_descriptor:p->version==2?p->v2.master_key_identifier:NULL;}
static int fscrypt_policy_size(const fscrypt_policy* p) {return p->version==0?(int)sizeof(p->v1):p->version==2?(int)sizeof(p->v2):0;}
static void* get_policy(const fscrypt_policy* p) {return p->version==0?(void*)&p->v1:p->version==2?(void*)&p->v2:NULL;}
static uint8_t get_policy_size(fscrypt_policy* p, bool hex) {int size=p->version==0?8:p->version==2?16:0; return hex?2*size+1:size;}
static void bytes_to_hex(const uint8_t* p,size_t n,char* out) {for(size_t i=0;i<n;i++)sprintf(out+2*i,"%02x",p[i]);}
static bool fscrypt_policy_get_struct(const char* path,fscrypt_policy* p) {(void)path; if(present){*p=current; if(mismatch_readback && policy_writes)p->v2.flags^=1; return true;} errno=query_error; return false;}
static bool fscrypt_policy_set_struct(const char* path,fscrypt_policy* p) {(void)path; ++policy_writes; if(set_policy_error){errno=set_policy_error;return false;}current=*p;present=true;return true;}
static bool lookup_ref_key(fscrypt_policy* p,uint8_t* out) {if(lookup_error)return false;memset(out,0,get_policy_size(p,false));sprintf((char*)out,"%u%s0",p->version,key_prefix_error?"XX":"CE");return true;}
static bool lookup_ref_tar(fscrypt_policy* p,uint8_t* out) {if(lookup_error)return false;memset(out,7,get_policy_size(p,false));return true;}
static char* th_get_pathname(TAR* t) {return t->th_buf.name;}
static mode_t th_get_mode(TAR* t) {return t->th_buf.mode;}
static char* path_dirname(const char* p) {(void)p;return ".";}
#define dirname path_dirname
static int mkdirhier(const char* p) {(void)p;return 0;}
static int write_path_inode(const char*a,const char*b,const char*c) {(void)a;(void)b;(void)c;return 0;}
static int fake_getxattr(const char*a,const char*b,void*c,size_t d) {(void)a;(void)b;(void)c;(void)d;errno=ENODATA;return -1;}
static int fake_setxattr(const char*a,const char*b,const void*c,size_t d,int e) {(void)a;(void)b;(void)c;(void)d;(void)e;if(cap_set_error){errno=cap_set_error;return -1;}return 0;}
#define getxattr fake_getxattr
#define setxattr fake_setxattr
#define XATTR_NAME_CAPS "security.capability"
typedef char* security_context_t;
static int lgetfilecon(const char*a,char** b) {(void)a;if(label_get_error){errno=label_get_error;return -1;}*b=strdup("u:object_r:test_file:s0");return (int)strlen(*b);}
static int lsetfilecon(const char*a,const char*b) {(void)a;(void)b;if(label_set_error){errno=label_set_error;return -1;}return 0;}
static void freecon(char* p) {free(p);}
static void print_caps(struct vfs_cap_data* p) {(void)p;}
typedef int libtar_hashptr_t;
typedef void libtar_hash_t;
typedef int (*libtar_matchfunc_t)(void);
typedef int (*libtar_hashfunc_t)(void);
typedef struct {dev_t td_dev;libtar_hash_t* td_h;} tar_dev_t;
typedef struct {ino_t ti_ino;char ti_name[4096];} tar_ino_t;
static int dev_match(void){return 0;} static int ino_match(void){return 0;} static int ino_hash(void){return 0;}
static void libtar_hashptr_reset(void* p){(void)p;}
static int libtar_hash_getkey(void*a,void*b,void*c,libtar_matchfunc_t d){(void)a;(void)b;(void)c;(void)d;return 0;}
static void* libtar_hashptr_data(void* p){return p;}
static void* libtar_hash_new(int n,libtar_hashfunc_t f){(void)n;(void)f;return (void*)1;}
static int libtar_hash_add(void*a,void*b){(void)a;(void)b;return 0;}
static void th_set_from_stat(TAR*t,struct stat*s){t->th_buf.typeflag=S_ISDIR(s->st_mode)?'5':S_ISLNK(s->st_mode)?'2':'0';t->th_buf.mode=s->st_mode;}
static void th_set_path(TAR*t,const char*p){snprintf(t->th_buf.name,sizeof(t->th_buf.name),"%s",p);}
static void th_set_link(TAR*t,const char*p){(void)t;(void)p;}
static int th_write(TAR*t){(void)t;++writes;return 0;}
static int tar_append_regfile(TAR*t,const char*p){(void)t;(void)p;if(append_error){errno=append_error;return -1;}return 0;}
static int tar_set_file_perms(TAR*t,const char*p){(void)t;(void)p;return 0;}
static int tar_extract_dir(TAR*,const char*);
static int tar_extract_regfile(TAR*t,const char*p,const int*fd){(void)t;(void)p;(void)fd;++file_writes;return 0;}
static int tar_extract_hardlink(TAR*t,const char*p,const char*r){(void)t;(void)p;(void)r;return 0;}
static int tar_extract_symlink(TAR*t,const char*p){(void)t;(void)p;return 0;}
static int tar_extract_chardev(TAR*t,const char*p){(void)t;(void)p;return 0;}
static int tar_extract_blockdev(TAR*t,const char*p){(void)t;(void)p;return 0;}
static int tar_extract_fifo(TAR*t,const char*p){(void)t;(void)p;return 0;}
static int header_index, header_total, payload_error;
static int th_read(TAR*t){(void)t;return header_index++<header_total?0:1;}
static int tar_skip_regfile(TAR*t){(void)t;if(payload_error){errno=EINVAL;return -1;}return 0;}
static void clear_header(TAR* t) {free(t->th_buf.fep);free(t->th_buf.selinux_context);memset(&t->th_buf,0,sizeof(t->th_buf));}
static size_t record(char* out,const char* tag,const void* value,size_t size) {
    size_t total=strlen(tag)+size+4,previous;
    do {previous=total;int digits=snprintf(NULL,0,"%zu",total);total=(size_t)digits+1+strlen(tag)+size+1;}while(previous!=total);
    int prefix=sprintf(out,"%zu %s",total,tag);memcpy(out+prefix,value,size);out[total-1]='\n';return total;
}
'''

MAIN = r'''
int main(int argc,char**argv) {
    assert(argc==4); const char* scenario=argv[1]; const char* path=argv[2]; int version=atoi(argv[3]);
    TAR t={0};t.options=TAR_STORE_FSCRYPT_POL|TAR_STORE_SELINUX|TAR_STORE_POSIX_CAP|TAR_REQUIRE_FSCRYPT_POL;
    t.th_buf.typeflag='5';t.th_buf.mode=0700;snprintf(t.th_buf.name,sizeof(t.th_buf.name),"%s",path);
    if(!strcmp(scenario,"pax") || !strcmp(scenario,"bad_pax")) {
        char buf[512], payload[128];fscrypt_policy p=make_policy(version);memcpy(payload,"0",1);memcpy(payload+1,get_policy(&p),fscrypt_policy_size(&p));
        size_t n=record(buf,"other.binary=","\0\n",2);
        n+=record(buf+n,FSCRYPT_TAG,payload,1+fscrypt_policy_size(&p));
        struct vfs_cap_data caps={0};caps.magic_etc=1;
        n+=record(buf+n,CAPABILITIES_TAG,&caps,sizeof(caps));
        if(!strcmp(scenario,"bad_pax")) {assert(th_read_metadata(&t,buf,n-1)<0);clear_header(&t);buf[0]='0';assert(th_read_metadata(&t,buf,n)<0);}
        else {assert(th_read_metadata(&t,buf,n)==0);assert(t.th_buf.fep && t.th_buf.fep->version==version);assert(memcmp(get_policy(t.th_buf.fep),get_policy(&p),fscrypt_policy_size(&p))==0);assert(t.th_buf.has_cap_data && t.th_buf.cap_data.magic_etc==1);}
    } else if(!strcmp(scenario,"backup_plain") || !strcmp(scenario,"backup_error")) {
        assert(mkdir(path,0700)==0);query_error=ENODATA;
        assert(tar_append_file(&t,path,"directory")==0 && t.th_buf.fep==NULL);
        if(!strcmp(scenario,"backup_error")) {
            for(int i=0;i<3;i++){query_error=i==0?EACCES:i==1?EINVAL:ENOTTY;assert(tar_append_file(&t,path,"directory")<0);}
            present=true;current=make_policy(version);lookup_error=1;assert(tar_append_file(&t,path,"directory")<0);
            lookup_error=0;key_prefix_error=1;assert(tar_append_file(&t,path,"directory")<0);
        }
    } else if(!strcmp(scenario,"content_error")) {
        FILE* file=fopen(path,"wb");assert(file);fputs("fixture",file);fclose(file);
        append_error=ENOKEY;assert(tar_append_file(&t,path,"file")<0);
    } else if(!strcmp(scenario,"label_error")) {
        assert(mkdir(path,0700)==0);label_get_error=EACCES;
        assert(tar_append_file(&t,path,"directory")<0);
    } else if(!strcmp(scenario,"directory_link")) {
        char outside[4096];snprintf(outside,sizeof(outside),"%s-outside",path);
        assert(mkdir(outside,0700)==0);assert(symlink(outside,path)==0);
        assert(tar_extract_dir(&t,path)<0 && policy_writes==0);
        struct stat st;assert(stat(outside,&st)==0 && (st.st_mode&0777)==0700);
    } else if(!strcmp(scenario,"backup_policy")) {
        assert(mkdir(path,0700)==0);present=true;current=make_policy(version);
        assert(tar_append_file(&t,path,"directory")==0);assert(t.th_buf.fep);assert(get_policy_descriptor(t.th_buf.fep)[1]=='C');
    } else if(!strcmp(scenario,"restore") || !strcmp(scenario,"existing") || !strcmp(scenario,"policy_error")) {
        t.th_buf.fep=malloc(sizeof(fscrypt_policy));*t.th_buf.fep=make_policy(version);
        if(!strcmp(scenario,"existing")){assert(mkdir(path,0700)==0);present=true;current=make_policy(version);}
        if(!strcmp(scenario,"policy_error"))lookup_error=1;
        int result=tar_extract_dir(&t,path);
        if(!strcmp(scenario,"policy_error"))assert(result<0 && policy_writes==0);
        else {assert(result==0);assert(present);assert(policy_writes==(!strcmp(scenario,"existing")?0:1));}
    } else if(!strcmp(scenario,"mismatch") || !strcmp(scenario,"set_error") || !strcmp(scenario,"readback_error") || !strcmp(scenario,"missing_policy")) {
        if(strcmp(scenario,"missing_policy")){t.th_buf.fep=malloc(sizeof(fscrypt_policy));*t.th_buf.fep=make_policy(version);}
        if(!strcmp(scenario,"mismatch")){present=true;current=make_policy(version);current.v1.flags^=1;}
        if(!strcmp(scenario,"set_error"))set_policy_error=ENOKEY;
        if(!strcmp(scenario,"readback_error"))mismatch_readback=1;
        if(!strcmp(scenario,"missing_policy")){present=true;current=make_policy(version);}
        assert(tar_extract_dir(&t,path)<0);
    } else if(!strcmp(scenario,"metadata_error")) {
        t.th_buf.typeflag='0';t.th_buf.selinux_context=strdup("test-label");label_set_error=EACCES;
        assert(tar_extract_file(&t,path,"/",NULL)<0);
        label_set_error=0;free(t.th_buf.selinux_context);t.th_buf.selinux_context=NULL;t.th_buf.has_cap_data=1;cap_set_error=EACCES;
        assert(tar_extract_file(&t,path,"/",NULL)<0);
    } else if(!strcmp(scenario,"validate") || !strcmp(scenario,"validate_error")) {
        header_total=1;t.th_buf.typeflag='0';strcpy(t.th_buf.name,"/file");
        if(!strcmp(scenario,"validate_error"))payload_error=1;
        int result=tar_validate_all(&t,path,path);
        assert((result==0)==!payload_error);assert(policy_writes==0 && file_writes==0);
        header_index=0;strcpy(t.th_buf.name,"../escape");assert(tar_validate_all(&t,path,path)<0);
    } else return 2;
    clear_header(&t);return 0;
}
'''


class BackupMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('gcc') or shutil.which('cc')
        if not compiler:
            raise unittest.SkipTest('C compiler unavailable; archive metadata NOT_TESTED')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        code = COMMON
        for path, signatures in [
            ('libtar/block.c', ['static int\nth_read_metadata(']),
            ('libtar/append.c', ['int\ntar_append_file(']),
            ('libtar/extract.c', ['int\ntar_extract_dir(', 'int\ntar_extract_file(']),
            ('libtar/wrapper.c', ['static int\ntar_validation_path(', 'int\ntar_validate_all(']),
        ]:
            code += ''.join(function(postimage(path), sig) for sig in signatures)
        path = cls.root / 'metadata.c'
        path.write_text(code + MAIN)
        result = subprocess.run([compiler, '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                 str(path), '-o', str(cls.root / 'metadata')],
                                capture_output=True, text=True, timeout=40)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scenario(self, name, version=2):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([str(self.root / 'metadata'), name, str(Path(tmp) / 'target'), str(version)],
                           capture_output=True, text=True, check=True, timeout=5)

    def test_binary_pax_v1_v2_and_following_capabilities(self):
        for version in (0, 2):
            self.scenario('pax', version)
            self.scenario('bad_pax', version)

    def test_backup_plain_query_errors_and_missing_key_references(self):
        for name in ('backup_plain', 'backup_error', 'backup_policy'):
            self.scenario(name)

    def test_content_key_label_and_existing_symlink_failures(self):
        for name in ('content_error', 'label_error', 'directory_link'):
            self.scenario(name)

    def test_restore_new_and_existing_policy_v1_v2(self):
        for version in (0, 2):
            self.scenario('restore', version)
            self.scenario('existing', version)

    def test_policy_conflicts_and_required_metadata_errors(self):
        for name in ('policy_error', 'mismatch', 'set_error', 'readback_error', 'missing_policy', 'metadata_error'):
            self.scenario(name)

    def test_archive_preflight_has_no_extract_or_policy_writes(self):
        self.scenario('validate')
        self.scenario('validate_error')

    def test_frontend_preflight_and_split_readers_preserve_mode(self):
        tar = postimage('twrpTar.cpp')
        self.assertIn('archive.validate_only = validate_only;', tar)
        self.assertIn('archive.require_fscrypt_policy = require_fscrypt_policy;', tar)
        self.assertIn('tar_validate_all(t, charRootDir, validation_root.c_str())', tar)
        self.assertNotIn('Required key not available, skipping file', postimage('libtar/append.c'))


ERRNO_COMMON = r'''
#include <cassert>
#include <cstdint>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <linux/fscrypt.h>
#undef fscrypt_policy
#include <string>
#include <unistd.h>
using namespace std;
union fscrypt_policy {uint8_t version; struct fscrypt_policy_v1 v1; struct fscrypt_policy_v2 v2;};
static bool keyring = true;
namespace android {namespace vold {bool isFsKeyringSupported(){return keyring;}}}
static int fail_open = 0, fail_ioctl = 0;
struct Logger {
    template<class T> Logger& operator<<(const T&) {errno=EIO;return *this;}
};
#define PLOG(level) Logger()
static int fake_open(const char*, int) {if(fail_open){errno=fail_open;return -1;}return 9;}
static int fake_close(int) {errno=EBADF;return 0;}
static int fake_ioctl(int, unsigned long, void*) {if(fail_ioctl){errno=fail_ioctl;return -1;}return 0;}
static void* get_policy(fscrypt_policy* p) {return &p->v1;}
#define open fake_open
#define close fake_close
#define ioctl fake_ioctl
'''


class FscryptErrnoTests(unittest.TestCase):
    def test_actual_helper_preserves_original_errno_after_logging_and_close(self):
        compiler = shutil.which('g++') or shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable; policy errno NOT_TESTED')
        cpp = postimage('fscrypt_policy.cpp', 'vold-fscrypt-policy-errno.patch')
        body = ''.join(function(cpp, signature) for signature in (
            'extern "C" bool fscrypt_policy_set_struct(',
            'extern "C" bool fscrypt_policy_get_struct('))
        main = r'''
int main() {
    fscrypt_policy policy = {};
    for(bool use_keyring : {false, true}) {
        keyring = use_keyring;
        for(int error : {ENODATA, ENOTTY, EOPNOTSUPP, EINVAL, EOVERFLOW, ENOKEY, EACCES}) {
            fail_ioctl=error;
            assert(!fscrypt_policy_get_struct("/fixture",&policy) && errno==error);
            assert(!fscrypt_policy_set_struct("/fixture",&policy) && errno==error);
        }
    }
    fail_ioctl=0;fail_open=EACCES;
    assert(!fscrypt_policy_get_struct("/fixture",&policy) && errno==EACCES);
    assert(!fscrypt_policy_set_struct("/fixture",&policy) && errno==EACCES);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'errno.cpp'
            path.write_text(ERRNO_COMMON + body + main)
            result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                     str(path), '-o', str(Path(tmp) / 'errno')],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(Path(tmp) / 'errno')], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
