/*
 * Guest-side M5 test: the signed __TEXT/__LINKEDIT ranges of the main image
 * and of a dlopen()ed dylib must reject mprotect(PROT_WRITE).
 */

#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

static int probe_function(void) {
	return 1;
}

static int sealed(void* address, const char* label) {
	uintptr_t page = (uintptr_t) address & ~(uintptr_t)(getpagesize() - 1);
	void* mapped;
	int result;

	errno = 0;
	result = mprotect((void*) page, getpagesize(), PROT_READ | PROT_WRITE | PROT_EXEC);
	printf("%s mprotect r=%d errno=%d\n", label, result, errno);
	if (result != -1)
		return 0;

	/* mseal also rejects a fixed mapping over the sealed range. */
	errno = 0;
	mapped = mmap((void*) page, getpagesize(), PROT_READ | PROT_WRITE,
	    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
	printf("%s mmap_fixed r=%s errno=%d\n", label, mapped == MAP_FAILED ? "failed" : "ok", errno);
	return mapped == MAP_FAILED;
}

int main(int argc, char** argv) {
	void* handle;
	void* symbol;

	if (!sealed((void*) &probe_function, "main"))
		return 1;
	if (argc < 2) {
		printf("SEAL_OK\n");
		return 0;
	}

	handle = dlopen(argv[1], RTLD_NOW);
	if (handle == 0) {
		printf("DLOPEN_FAIL %s\n", dlerror());
		return 1;
	}
	symbol = dlsym(handle, "darling_lv_target");
	if (symbol == 0) {
		printf("DLSYM_FAIL\n");
		return 1;
	}
	if (!sealed(symbol, "library"))
		return 1;

	printf("SEAL_OK\n");
	return 0;
}
