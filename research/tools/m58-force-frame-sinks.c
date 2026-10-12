/*
 * M58b Darling workaround for Electron/Chromium 108.
 *
 * The CoreVideo pump supplies the display source, but Chromium's GPU-side
 * FrameSink source drops the generated tick before it reaches renderer sinks
 * and then viz stops observing them.  This deliberately narrow, build-checked
 * patch keeps those two gates open for the Electron 22.3.27 framework.
 */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

#define FILTER_BRANCH_VA 0x51dec19UL
#define SHOULD_SEND_VA   0x64fb760UL
#define CFSS_SKIP_BRANCH_VA 0x64fb309UL
#define ASYNC_NEEDS_BRANCH_VA 0x5e2318dUL

static void report(unsigned long value) {
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-frame-sinks.status",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, &value, sizeof(value)); close(fd); }
}

static int patch_bytes(unsigned char *at, const unsigned char *expected,
                       unsigned count, const unsigned char *replacement) {
    unsigned i;
    for (i = 0; i < count; ++i)
        if (at[i] != expected[i])
            return 0;
    for (i = 0; i < count; ++i)
        at[i] = replacement[i];
    return 1;
}

__attribute__((constructor)) static void install(void) {
    unsigned i;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            unsigned char *base = (unsigned char *)_dyld_get_image_header(i);
            unsigned char *filter = base + FILTER_BRANCH_VA;
            unsigned char *should_send = base + SHOULD_SEND_VA;
            unsigned char filter_expected[] = { 0x7e, 0x12 };
            unsigned char filter_replacement[] = { 0x90, 0x90 };
            unsigned char send_expected[] = {
                0x55, 0x48, 0x89, 0xe5, 0x41, 0x57
            };
            unsigned char send_replacement[] = {
                0xb8, 0x01, 0x00, 0x00, 0x00, 0xc3
            };
            unsigned char skip_expected[] = {
                0x0f, 0x84, 0x3b, 0x01, 0x00, 0x00
            };
            unsigned char skip_replacement[] = {
                0x90, 0x90, 0x90, 0x90, 0x90, 0x90
            };
            unsigned char async_needs_expected[] = { 0x74, 0x4d };
            unsigned char async_needs_replacement[] = { 0x90, 0x90 };
            unsigned long first_page = (unsigned long)filter & ~0xfffUL;
            unsigned long last_page = (unsigned long)should_send & ~0xfffUL;
            unsigned long branch_page =
                (unsigned long)(base + CFSS_SKIP_BRANCH_VA) & ~0xfffUL;
            unsigned long async_page =
                (unsigned long)(base + ASYNC_NEEDS_BRANCH_VA) & ~0xfffUL;
            if (branch_page > last_page)
                last_page = branch_page;
            if (async_page > last_page)
                last_page = async_page;
            unsigned long length = last_page - first_page + 0x1000UL;
            if (mprotect((void *)first_page, length, 7) != 0) {
                report(0xbad00001UL);
                return;
            }
            if (!patch_bytes(filter, filter_expected, 2, filter_replacement)) {
                report(0xbad00002UL);
                return;
            }
            if (!patch_bytes(should_send, send_expected, 6,
                             send_replacement)) {
                report(0xbad00003UL);
                return;
            }
            if (!patch_bytes(base + CFSS_SKIP_BRANCH_VA, skip_expected, 6,
                             skip_replacement)) {
                report(0xbad00005UL);
                return;
            }
            if (!patch_bytes(base + ASYNC_NEEDS_BRANCH_VA,
                             async_needs_expected, 2,
                             async_needs_replacement)) {
                report(0xbad00006UL);
                return;
            }
            report(0x5e2318dUL);
            return;
        }
    }
    report(0xbad00004UL);
}
