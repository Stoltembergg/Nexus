/* Diagnostic/fallback patch for Electron 22.3.27.
 * DelayBasedBeginFrameSource::IssueBeginFrameToObserver rejects every generated
 * frame under Darling. NOP its `jle skip` so the observer receives the frame.
 * The expected bytes make this fail closed on any other Electron build. */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

#define FILTER_BRANCH_VA 0x51dec19UL
#define ANIMATE_BRANCH_VA 0x51dec1fUL

static void report(unsigned long value) {
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m57-force-begin-frame.status",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, &value, sizeof(value)); close(fd); }
}

__attribute__((constructor)) static void install(void) {
    unsigned i;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            unsigned char *base = (unsigned char *)_dyld_get_image_header(i);
            unsigned char *branch = base + FILTER_BRANCH_VA;
            unsigned long page = (unsigned long)branch & ~0xfffUL;
            if (branch[0] != 0x7e || branch[1] != 0x12) {
                report(0xbad00000UL | branch[0] | ((unsigned long)branch[1] << 8));
                return;
            }
            if (mprotect((void *)page, 0x1000, 7) != 0) {
                report(0xbad00001UL);
                return;
            }
            branch[0] = 0x90;
            branch[1] = 0x90;
            if (base[ANIMATE_BRANCH_VA] == 0x75 &&
                base[ANIMATE_BRANCH_VA + 1] == 0x45) {
                base[ANIMATE_BRANCH_VA] = 0x90;
                base[ANIMATE_BRANCH_VA + 1] = 0x90;
            }
            report(0x51dec19UL);
            return;
        }
    }
    report(0xbad00002UL);
}
