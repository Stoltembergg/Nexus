/* Test-bed only: logs the status of Security calls made by the stock Electron
 * repro (tools/run-riot-chromium108-tls-repro.sh). Never loaded into Riot processes. */
typedef int OSStatus;
extern int snprintf(char*, unsigned long, const char*, ...);
extern long write(int, const void*, unsigned long);
extern int getpid(void);
#define INTERPOSE(name) \
	__attribute__((used, section("__DATA,__interpose"))) static const struct { const void* replacement; const void* original; } \
	interpose_##name = { (const void*)trace_##name, (const void*)name };
#define TRACE(name) \
	extern OSStatus name(void*, void*, void*, void*, void*, void*); \
	static OSStatus trace_##name(void* a, void* b, void* c, void* d, void* e, void* f) { \
		OSStatus status = name(a, b, c, d, e, f); \
		char line[96]; \
		int length = snprintf(line, sizeof(line), "SECTRACE pid=%d %s=%d\n", getpid(), #name, (int)status); \
		write(2, line, length); \
		return status; \
	} \
	INTERPOSE(name)

TRACE(SecTrustCreateWithCertificates)
TRACE(SecTrustSetAnchorCertificates)
TRACE(SecTrustSetAnchorCertificatesOnly)
TRACE(SecTrustSetKeychains)
TRACE(SecTrustSetOCSPResponse)
TRACE(SecTrustSetSignedCertificateTimestamps)
TRACE(SecTrustSetParameters)
TRACE(SecTrustEvaluate)
TRACE(SecTrustGetResult)
TRACE(SecTrustGetCssmResultCode)
TRACE(SecTrustSettingsCopyCertificates)
TRACE(SecTrustSettingsCopyTrustSettings)
TRACE(SecKeychainCopySearchList)
TRACE(SecKeychainOpen)
TRACE(SecCertificateGetCLHandle)
TRACE(SecCertificateGetData)
TRACE(CSSM_CL_CertCache)
TRACE(CSSM_CL_CertGetFirstCachedFieldValue)
TRACE(SecItemCopyMatching)

#define TRACEPTR(name) \
	extern void* name(void*, void*, void*, void*); \
	static void* trace_##name(void* a, void* b, void* c, void* d) { \
		void* value = name(a, b, c, d); \
		char line[96]; \
		int length = snprintf(line, sizeof(line), "SECTRACE pid=%d %s=%s\n", getpid(), #name, value ? "object" : "NULL"); \
		write(2, line, length); \
		return value; \
	} \
	INTERPOSE(name)

TRACEPTR(SecPolicyCreateBasicX509)
TRACEPTR(SecPolicyCreateSSL)
TRACEPTR(SecPolicyCreateRevocation)
TRACEPTR(SecCertificateCreateWithData)
TRACEPTR(SecPolicyCopyProperties)

extern char* getenv(const char*);
extern unsigned long confstr(int, char*, unsigned long);
extern int getuid(void);
extern int geteuid(void);
extern char* getcwd(char*, unsigned long);
extern int access(const char*, int);
extern int* __error(void);

__attribute__((constructor)) static void trace_environment(void)
{
	char cache[512] = "", temp[512] = "", cwd[512] = "", line[1400];
	confstr(65538 /* _CS_DARWIN_USER_CACHE_DIR */, cache, sizeof(cache));
	confstr(65537 /* _CS_DARWIN_USER_TEMP_DIR */, temp, sizeof(temp));
	getcwd(cwd, sizeof(cwd));
	const char* home = getenv("HOME");
	const char* tmpdir = getenv("TMPDIR");
	int length = snprintf(line, sizeof(line),
		"SECTRACE pid=%d env uid=%d euid=%d HOME=%s TMPDIR=%s cache=%s temp=%s cwd=%s cache_writable=%d home_writable=%d\n",
		getpid(), getuid(), geteuid(), home ? home : "(unset)", tmpdir ? tmpdir : "(unset)", cache, temp, cwd,
		access(cache, 2), home ? access(home, 2) : -9);
	write(2, line, length);
}

/* Report exceptions thrown while the traced Security calls run. */
typedef struct { const char* dli_fname; void* dli_fbase; const char* dli_sname; void* dli_saddr; } TraceDlInfo;
extern int dladdr(const void*, TraceDlInfo*);
extern char* strrchr(const char*, int);
extern void __cxa_throw(void*, void*, void (*)(void*)) __attribute__((noreturn));

__attribute__((noreturn)) static void trace___cxa_throw(void* object, void* type, void (*destructor)(void*))
{
	char line[900];
	const char* name = type ? *(const char**)((char*)type + 8) : "?";
	/* the error code follows the exception's message buffer; report the first CSSM/OSStatus-like word */
	int code = 0;
	for (int offset = 8; object && offset < 320 && code == 0; offset += 4) {
		int word = *(int*)((char*)object + offset);
		if ((word & 0xfff00000) == 0x80000000 || (word < 0 && word > -70000))
			code = word;
	}
	int length = snprintf(line, sizeof(line), "SECTRACE pid=%d throw type=%s code=%d(%#x) tail=%#x,%#x,%#x,%#x at", getpid(), name, code, code,
		object ? *(int*)((char*)object + 0x90) : 0, object ? *(int*)((char*)object + 0x94) : 0,
		object ? *(int*)((char*)object + 0x110) : 0, object ? *(int*)((char*)object + 0x114) : 0);
	void** frame = (void**)__builtin_frame_address(0);
	for (int depth = 0; depth < 9 && frame && length < 800; depth++) {
		void* address = frame[1];
		TraceDlInfo info = { 0 };
		if (address && dladdr(address, &info) && info.dli_fname) {
			const char* base = strrchr(info.dli_fname, '/');
			length += snprintf(line + length, sizeof(line) - length, " %s+%#lx", base ? base + 1 : info.dli_fname,
			                   (unsigned long)((char*)address - (char*)info.dli_fbase));
		}
		void** next = (void**)frame[0];
		if (next <= frame) break;
		frame = next;
	}
	line[length++] = '\n';
	write(2, line, length);
	__cxa_throw(object, type, destructor);
}
__attribute__((used, section("__DATA,__interpose"))) static const struct { const void* replacement; const void* original; }
	interpose___cxa_throw = { (const void*)trace___cxa_throw, (const void*)__cxa_throw };
