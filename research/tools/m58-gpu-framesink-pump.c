/* M58 diagnostic: pace viz's CompositorFrameSinkSupport directly.  This is
 * the FrameSink-level equivalent of the CoreVideo pump and avoids relying on
 * the broken cross-view ExternalBeginFrameSource observer list. */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int getpid(void);
extern const char *getprogname(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern unsigned long mach_absolute_time(void);
extern int mach_timebase_info(void *);

#define SUPPORT_ONBEGIN_VA 0x64fb270UL
#define SHOULD_SEND_VA 0x64fb760UL
#define CFSS_SKIP_VA 0x64fb309UL

struct Hook { unsigned char *target, saved[12]; unsigned long replacement; };
static struct Hook support_hook;
static volatile int lock;
static volatile int pumped;

static void emit(unsigned event, unsigned long value) {
    unsigned long r[3] = {(unsigned long)getpid(), event, value};
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-gpu-pump.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, r, sizeof(r)); close(fd); }
}

static int gpu_process(void) {
    const char *name = getprogname();
    return name && strstr(name, "GPU") != 0;
}

static unsigned char *find_framework(void) {
    for (unsigned i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework"))
            return (unsigned char *)_dyld_get_image_header(i);
    }
    return 0;
}

static void patch(int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)support_hook.target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (unsigned i = 0; i < 12; ++i)
            support_hook.target[i] = support_hook.saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (support_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i) support_hook.target[i] = jump[i];
}

static unsigned long now_us(void) {
    struct { unsigned numer, denom; } tb;
    mach_timebase_info(&tb);
    return mach_absolute_time() * (unsigned long)tb.numer /
           (tb.denom ? tb.denom : 1) / 1000UL;
}

static void support_on_begin(void *self, void *args) {
    unsigned char frame[64];
    for (unsigned i = 0; i < sizeof(frame); ++i)
        frame[i] = ((unsigned char *)args)[i];
    patch(0);
    ((void (*)(void *, void *))support_hook.target)(self, args);
    patch(1);
    emit(1, (unsigned long)self);
    if (!gpu_process() || __sync_lock_test_and_set(&pumped, 1)) return;

    for (unsigned n = 1; n <= 600; ++n) {
        unsigned long t = now_us();
        *(unsigned long *)(frame + 0) = t;
        *(unsigned long *)(frame + 8) = t + 16666;
        *(unsigned long *)(frame + 16) = 16666;
        *(unsigned long *)(frame + 32) = n + 1;
        patch(0);
        ((void (*)(void *, void *))support_hook.target)(self, frame);
        patch(1);
        emit(2, n);
        unsigned long until = now_us() + 16666;
        while (now_us() < until) { }
    }
}

__attribute__((constructor)) static void install(void) {
    unsigned char *base = find_framework();
    if (!base) return;
    support_hook.target = base + SUPPORT_ONBEGIN_VA;
    support_hook.replacement = (unsigned long)support_on_begin;
    for (unsigned i = 0; i < 12; ++i)
        support_hook.saved[i] = support_hook.target[i];
    if (support_hook.saved[0] != 0x55 || support_hook.saved[1] != 0x48 ||
        support_hook.saved[2] != 0x89 || support_hook.saved[3] != 0xe5)
        return;
    unsigned long first = (unsigned long)(base + SHOULD_SEND_VA) & ~0xfffUL;
    unsigned long last = (unsigned long)(base + CFSS_SKIP_VA) & ~0xfffUL;
    mprotect((void *)first, last - first + 0x1000, 7);
    unsigned char *send = base + SHOULD_SEND_VA;
    if (send[0] == 0x55 && send[1] == 0x48 && send[2] == 0x89 &&
        send[3] == 0xe5 && send[4] == 0x41 && send[5] == 0x57) {
        send[0] = 0xb8; send[1] = 1; send[2] = 0; send[3] = 0;
        send[4] = 0; send[5] = 0xc3;
    }
    unsigned char *skip = base + CFSS_SKIP_VA;
    if (skip[0] == 0x0f && skip[1] == 0x84 && skip[2] == 0x3b &&
        skip[3] == 0x01 && skip[4] == 0x00 && skip[5] == 0x00)
        for (unsigned i = 0; i < 6; ++i) skip[i] = 0x90;
    patch(1);
    emit(99, (unsigned long)base);
}
