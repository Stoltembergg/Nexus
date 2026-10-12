/*
 * M58b diagnostic/fix probe for Electron 22.3.27.
 *
 * The GPU-side FrameSink source is alive, but the renderer sinks do not get a
 * client-facing BeginFrame.  This probe feeds the renderer's already-bound
 * AsyncLayerTreeFrameSink directly.  The sink pointer crosses the timer
 * boundary through the same host file used by the CoreVideo pump; no guest
 * global is shared between the compositor and runloop views.
 *
 * This is intentionally tied to the Electron 22.3.27 framework offsets and
 * fails closed when the BindToClient prologue changes.
 */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern unsigned long mach_absolute_time(void);
extern int mach_timebase_info(void *);

typedef void *CFRunLoopRef;
typedef void *CFRunLoopTimerRef;
typedef void *CFStringRef;
typedef void (*TimerCallback)(CFRunLoopTimerRef, void *);
typedef struct {
    void *version;
    void *info;
    void *retain;
    void *release;
    void *copy_description;
} TimerContext;
extern CFRunLoopRef CFRunLoopGetMain(void);
extern CFRunLoopRef CFRunLoopGetCurrent(void);
extern double CFAbsoluteTimeGetCurrent(void);
extern CFRunLoopTimerRef CFRunLoopTimerCreate(void *, double, double,
                                               long, long, TimerCallback,
                                               TimerContext *);
extern void CFRunLoopAddTimer(CFRunLoopRef, CFRunLoopTimerRef, CFStringRef);
extern CFStringRef CFStringCreateWithCString(void *, const char *, unsigned);

#define NEEDS_VA   0x5e23520UL
#define ONBEGIN_VA 0x5e23140UL

struct PumpState {
    unsigned magic;
    unsigned reserved;
    unsigned long sink;
    unsigned long sequence;
};
static const unsigned kMagic = 0x4d353842U;
static void trace_event(unsigned event, unsigned long value) {
    unsigned long record[3] = { (unsigned long)getpid(), event, value };
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-renderer-pump.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, record, sizeof(record)); close(fd); }
}

struct Hook {
    unsigned char *target;
    unsigned char saved[12];
    unsigned long replacement;
};
static struct Hook needs_hook;
static unsigned char *framework_base;
static volatile int bind_lock;
static volatile int timer_started;

static unsigned char *find_framework_base(void) {
    unsigned i;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework"))
            return (unsigned char *)_dyld_get_image_header(i);
    }
    return 0;
}

static void path(char *out, unsigned size) {
    char digits[24]; unsigned long value = (unsigned long)getpid();
    unsigned n = 0, i;
    do { digits[n++] = (char)('0' + value % 10); value /= 10; } while (value);
    const char *prefix = "/dev/shm/darling-begin-pump-";
    unsigned p = 0;
    while (prefix[p] && p + 1 < size) { out[p] = prefix[p]; ++p; }
    for (i = 0; i < n && p + 1 < size; ++i)
        out[p + i] = digits[n - i - 1];
    p += n;
    if (p + 7 < size) {
        out[p++] = '.'; out[p++] = 's'; out[p++] = 't'; out[p++] = 'a';
        out[p++] = 't'; out[p++] = 'e'; out[p] = 0;
    }
}

static void save_sink(void *sink) {
    char filename[96]; struct PumpState state = { kMagic, 0,
                                                   (unsigned long)sink, 0 };
    path(filename, sizeof(filename));
    int fd = open(filename, 1 | 0x200 | 0x1000, 0644);
    if (fd >= 0) { write(fd, &state, sizeof(state)); close(fd); }
    trace_event(1, (unsigned long)sink);
}

static int load_state(struct PumpState *state) {
    char filename[96];
    path(filename, sizeof(filename));
    int fd = open(filename, 0, 0);
    if (fd < 0) return 0;
    long got = read(fd, state, sizeof(*state)); close(fd);
    return got == (long)sizeof(*state) && state->magic == kMagic &&
           state->sink != 0;
}

static void patch(struct Hook *hook, int enabled) {
    unsigned char jump[12]; unsigned long page;
    unsigned i;
    page = (unsigned long)hook->target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (i = 0; i < 12; ++i) hook->target[i] = hook->saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (i = 0; i < 8; ++i)
        jump[i + 2] = (hook->replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (i = 0; i < 12; ++i) hook->target[i] = jump[i];
}

static unsigned long now_us(void) {
    struct { unsigned numer, denom; } timebase;
    mach_timebase_info(&timebase);
    return mach_absolute_time() * (unsigned long)timebase.numer /
           (timebase.denom ? timebase.denom : 1) / 1000UL;
}

static void pump_timer(CFRunLoopTimerRef timer, void *info) {
    (void)timer; (void)info;
    struct PumpState state;
    if (!load_state(&state)) return;
    trace_event(2, state.sink);

    /* Release NDEBUG BeginFrameArgs layout: three Time values, BeginFrameId,
     * trace id, type/flags, throttled count and an empty optional tail. */
    unsigned char args[128] = { 0 };
    unsigned long t = now_us();
    unsigned long interval = 16666;
    unsigned long sequence = ++state.sequence;
    *(unsigned long *)(args + 0) = t;
    *(unsigned long *)(args + 8) = t + interval;
    *(unsigned long *)(args + 16) = interval;
    *(unsigned long *)(args + 24) = 0xffffffffUL;
    *(unsigned long *)(args + 32) = sequence;
    *(long *)(args + 40) = -1;
    *(unsigned *)(args + 48) = 1; /* NORMAL */
    args[52] = 1;                 /* on_critical_path */

    /* An empty flat_map is three null pointers in Chromium 108. */
    unsigned char details[24] = { 0 };
    /* Resolve the image on the timer thread.  Darling gives helper threads a
     * separate guest view; the constructor's framework_base is not reliable
     * here even though the host file and sink pointer are. */
    unsigned char *base = find_framework_base();
    if (!base) return;
    void (*on_begin)(void *, void *, void *) =
        (void (*)(void *, void *, void *))(base + ONBEGIN_VA);
    on_begin((void *)state.sink, args, details);
    trace_event(3, sequence);

    char filename[96]; path(filename, sizeof(filename));
    int fd = open(filename, 1 | 0x200 | 0x1000, 0644);
    if (fd >= 0) { write(fd, &state, sizeof(state)); close(fd); }
}

static void start_timer_on_current_runloop(void) {
    if (__sync_lock_test_and_set(&timer_started, 1))
        return;
    CFRunLoopTimerRef timer = CFRunLoopTimerCreate(
        0, CFAbsoluteTimeGetCurrent() + 2.0, 1.0 / 60.0, 0, 0,
        pump_timer, 0);
    if (timer)
        CFRunLoopAddTimer(CFRunLoopGetMain(), timer,
            CFStringCreateWithCString(0, "kCFRunLoopDefaultMode",
                                       0x08000100));
}

static void needs_begin(void *self, int needs) {
    while (__sync_lock_test_and_set(&bind_lock, 1)) { }
    patch(&needs_hook, 0);
    ((void (*)(void *, int))needs_hook.target)(self, needs);
    patch(&needs_hook, 1);
    __sync_lock_release(&bind_lock);
    trace_event(4, (unsigned long)self);
    if (needs) {
        unsigned char args[128] = { 0 };
        unsigned char details[24] = { 0 };
        unsigned long sequence = 0;
        /* The compositor thread has no CF run loop under this Darling build.
         * Keep the callback on this thread and pace it, which is the only
         * safe place for AsyncLayerTreeFrameSink::OnBeginFrame. */
        for (unsigned tick = 0; tick < 1000; ++tick) {
            unsigned long t = now_us();
            ++sequence;
            *(unsigned long *)(args + 0) = t;
            *(unsigned long *)(args + 8) = t + 16666;
            *(unsigned long *)(args + 16) = 16666;
            *(unsigned long *)(args + 24) = 0xffffffffUL;
            *(unsigned long *)(args + 32) = sequence;
            *(long *)(args + 40) = -1;
            *(unsigned *)(args + 48) = 1;
            args[52] = 1;
            unsigned char *base = find_framework_base();
            if (!base) break;
            ((void (*)(void *, void *, void *))(base + ONBEGIN_VA))
                (self, args, details);
            trace_event(3, sequence);
            unsigned long until = now_us() + 16666;
            while (now_us() < until) { }
        }
    }
}

__attribute__((constructor)) static void install(void) {
    unsigned i; unsigned char *base = 0;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i); break;
        }
    }
    if (!base) return;
    framework_base = base;
    needs_hook.target = base + NEEDS_VA;
    needs_hook.replacement = (unsigned long)needs_begin;
    unsigned i2;
    for (i2 = 0; i2 < 12; ++i2) needs_hook.saved[i2] = needs_hook.target[i2];
    /* OnNeedsBeginFrames starts with the usual x86_64 frame prologue. */
    if (needs_hook.saved[0] != 0x55 || needs_hook.saved[1] != 0x48 ||
        needs_hook.saved[2] != 0x89 || needs_hook.saved[3] != 0xe5)
        return;
    patch(&needs_hook, 1);

}
