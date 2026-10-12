/* Low-perturbation Electron 22.3.27 present-path tracer.
 * Unlike m57-ipcz-trace.c, this hooks only low-frequency functions with known
 * signatures and writes fixed binary records using direct libc calls. */
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

#define SET_VISIBLE            0x64a7900UL
#define SET_FRAME_SINK         0x64a72c0UL
#define DRAW_AND_SWAP          0x6545f80UL
#define SCHEDULER_BEGIN_FRAME  0x654ce10UL
#define NATIVE_VISIBILITY      0x724c270UL
#define RWHV_SHOW              0x2ed4360UL
#define SUSPEND                0x64bc330UL
#define UNSUSPEND              0x64bc530UL
#define VIZ_SET_VISIBLE        0x6545ab0UL
#define SCHEDULER_SET_VISIBLE  0x654c2c0UL
#define ROOT_SET_VISIBLE       0x654e3e0UL
#define UPDATE_LAYER_TREE      0x4e84830UL
#define GOT_LAYER_FRAME        0x4e84ad0UL
#define TIME_SOURCE_SET_ACTIVE 0x51ddb30UL
#define TIME_SOURCE_TICK       0x51dd9d0UL
#define BEGIN_SOURCE_ADD       0x51de820UL
#define BEGIN_SOURCE_TICK      0x51ded90UL
#define SET_NEEDS_ONE_FRAME    0x654d260UL
#define ISSUE_TO_OBSERVER      0x51deb50UL
#define OBSERVER_ON_FRAME      0x51ddf10UL
#define SCHEDULER_DERIVED_FRAME 0x654da10UL
#define FILTER_BRANCH          0x51dec19UL
#define ANIMATE_BRANCH         0x51dec1fUL

enum {
    EV_LOADED = 1, EV_SET_VISIBLE, EV_SET_FRAME_SINK, EV_DRAW_AND_SWAP,
    EV_SCHEDULER_BEGIN_FRAME, EV_NATIVE_VISIBILITY, EV_RWHV_SHOW,
    EV_SUSPEND, EV_UNSUSPEND, EV_VIZ_SET_VISIBLE,
    EV_SCHEDULER_SET_VISIBLE, EV_ROOT_SET_VISIBLE,
    EV_UPDATE_LAYER_TREE, EV_GOT_LAYER_FRAME, EV_TIME_SOURCE_SET_ACTIVE,
    EV_TIME_SOURCE_TICK, EV_BEGIN_SOURCE_ADD, EV_BEGIN_SOURCE_TICK,
    EV_SET_NEEDS_ONE_FRAME, EV_ISSUE_TO_OBSERVER, EV_OBSERVER_ON_FRAME,
    EV_SCHEDULER_DERIVED_FRAME, EV_ARGS_FRAME_TIME, EV_ARGS_INTERVAL,
    EV_LAST_FRAME_TIME, EV_LAST_INTERVAL, EV_ARGS_FLAGS, EV_OBSERVER_VFN2,
    EV_OBSERVER_VFN3, EV_OBSERVER_VFN5
};

struct record { unsigned pid, event; unsigned long value; };
struct hook { unsigned char *target, saved[12]; unsigned long replacement; };

static struct hook hooks[21];
static volatile int locks[21];
static unsigned issue_samples;

static void emit(unsigned event, unsigned long value) {
    struct record record = { (unsigned)getpid(), event, value };
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m57-narrow.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, &record, sizeof(record)); close(fd); }
}

static void patch(struct hook *hook, int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)hook->target & ~0xfffUL;
    int i;
    mprotect((void *)page, 0x2000, 7);
    if (!enabled) {
        for (i = 0; i < 12; ++i) hook->target[i] = hook->saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (i = 0; i < 8; ++i) jump[2 + i] =
        (hook->replacement >> (8 * i)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (i = 0; i < 12; ++i) hook->target[i] = jump[i];
}

static void call_void(unsigned n, unsigned event, void *self) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)self);
    ((void (*)(void *))hooks[n].target)(self);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}

static void call_bool(unsigned n, unsigned event, void *self, int value) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)value);
    ((void (*)(void *, int))hooks[n].target)(self, value);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}

static void set_visible(void *s, int v) { call_bool(0, EV_SET_VISIBLE, s, v); }
static void set_frame_sink(void *s, void *sink, void *priv) {
    while (__sync_lock_test_and_set(&locks[1], 1)) { }
    patch(&hooks[1], 0); emit(EV_SET_FRAME_SINK, (unsigned long)sink);
    ((void (*)(void *, void *, void *))hooks[1].target)(s, sink, priv);
    patch(&hooks[1], 1); __sync_lock_release(&locks[1]);
}
static void draw_and_swap(void *s, const void *p) {
    while (__sync_lock_test_and_set(&locks[2], 1)) { }
    patch(&hooks[2], 0); emit(EV_DRAW_AND_SWAP, (unsigned long)p);
    ((void (*)(void *, const void *))hooks[2].target)(s, p);
    patch(&hooks[2], 1); __sync_lock_release(&locks[2]);
}
static void scheduler_begin(void *s, const void *a) {
    while (__sync_lock_test_and_set(&locks[3], 1)) { }
    patch(&hooks[3], 0); emit(EV_SCHEDULER_BEGIN_FRAME, (unsigned long)a);
    ((void (*)(void *, const void *))hooks[3].target)(s, a);
    patch(&hooks[3], 1); __sync_lock_release(&locks[3]);
}
static void native_visibility(void *s, int v) { call_bool(4, EV_NATIVE_VISIBILITY, s, v); }
static void rwhv_show(void *s, int v) { call_bool(5, EV_RWHV_SHOW, s, v); }
static void suspend(void *s) { call_void(6, EV_SUSPEND, s); }
static void unsuspend(void *s) { call_void(7, EV_UNSUSPEND, s); }
static void viz_visible(void *s, int v) { call_bool(8, EV_VIZ_SET_VISIBLE, s, v); }
static void scheduler_visible(void *s, int v) { call_bool(9, EV_SCHEDULER_SET_VISIBLE, s, v); }
static void root_visible(void *s, int v) { call_bool(10, EV_ROOT_SET_VISIBLE, s, v); }
static void update_layer(void *s, const void *p) {
    while (__sync_lock_test_and_set(&locks[11], 1)) { }
    patch(&hooks[11], 0); emit(EV_UPDATE_LAYER_TREE, (unsigned long)p);
    ((void (*)(void *, const void *))hooks[11].target)(s, p);
    patch(&hooks[11], 1); __sync_lock_release(&locks[11]);
}
static void got_layer(void *s, unsigned id) {
    while (__sync_lock_test_and_set(&locks[12], 1)) { }
    patch(&hooks[12], 0); emit(EV_GOT_LAYER_FRAME, id);
    ((void (*)(void *, unsigned))hooks[12].target)(s, id);
    patch(&hooks[12], 1); __sync_lock_release(&locks[12]);
}
static void time_source_active(void *s, int v) {
    call_bool(13, EV_TIME_SOURCE_SET_ACTIVE, s, v);
}
static void time_source_tick(void *s) { call_void(14, EV_TIME_SOURCE_TICK, s); }
static void begin_source_add(void *s, void *observer) {
    while (__sync_lock_test_and_set(&locks[15], 1)) { }
    patch(&hooks[15], 0); emit(EV_BEGIN_SOURCE_ADD, (unsigned long)observer);
    ((void (*)(void *, void *))hooks[15].target)(s, observer);
    patch(&hooks[15], 1); __sync_lock_release(&locks[15]);
}
static void begin_source_tick(void *s) { call_void(16, EV_BEGIN_SOURCE_TICK, s); }
static void set_needs_one_frame(void *s, int v) {
    call_bool(17, EV_SET_NEEDS_ONE_FRAME, s, v);
}
static void frame_arg_call(unsigned n, unsigned event, void *s, const void *args) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)s);
    ((void (*)(void *, const void *))hooks[n].target)(s, args);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}
static void issue_to_observer(void *s, void *observer, const void *args) {
    while (__sync_lock_test_and_set(&locks[18], 1)) { }
    patch(&hooks[18], 0); emit(EV_ISSUE_TO_OBSERVER, (unsigned long)observer);
    if (issue_samples++ < 8 && observer && args) {
        const unsigned long *current = (const unsigned long *)args;
        emit(EV_ARGS_FRAME_TIME, current[0]);
        emit(EV_ARGS_INTERVAL, current[2]);
        emit(EV_ARGS_FLAGS, current[6]);
        emit(EV_OBSERVER_VFN2, (*(unsigned long **)observer)[2]);
        emit(EV_OBSERVER_VFN3, (*(unsigned long **)observer)[3]);
        emit(EV_OBSERVER_VFN5, (*(unsigned long **)observer)[5]);
    }
    ((void (*)(void *, void *, const void *))hooks[18].target)(s, observer, args);
    patch(&hooks[18], 1); __sync_lock_release(&locks[18]);
}
static void observer_on_frame(void *s, const void *args) {
    frame_arg_call(19, EV_OBSERVER_ON_FRAME, s, args);
}
static void scheduler_derived_frame(void *s, const void *args) {
    frame_arg_call(20, EV_SCHEDULER_DERIVED_FRAME, s, args);
}

static void configure(struct hook *h, unsigned char *base, unsigned long offset,
                      void *replacement) {
    int i;
    h->target = base + offset;
    h->replacement = (unsigned long)replacement;
    for (i = 0; i < 12; ++i) h->saved[i] = h->target[i];
    patch(h, 1);
}

__attribute__((constructor)) static void install(void) {
    unsigned i;
    unsigned char *base = 0;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i); break;
        }
    }
    if (!base) return;
    emit(EV_LOADED, (unsigned long)base);
    /* Diagnostic: allow generated frames through Chromium's time filter. */
    if (base[FILTER_BRANCH] == 0x7e && base[FILTER_BRANCH + 1] == 0x12) {
        mprotect((void *)((unsigned long)(base + FILTER_BRANCH) & ~0xfffUL),
                 0x1000, 7);
        base[FILTER_BRANCH] = 0x90;
        base[FILTER_BRANCH + 1] = 0x90;
        if (base[ANIMATE_BRANCH] == 0x75 && base[ANIMATE_BRANCH + 1] == 0x45) {
            base[ANIMATE_BRANCH] = 0x90;
            base[ANIMATE_BRANCH + 1] = 0x90;
        }
    }
    configure(&hooks[0], base, SET_VISIBLE, set_visible);
    configure(&hooks[1], base, SET_FRAME_SINK, set_frame_sink);
    configure(&hooks[2], base, DRAW_AND_SWAP, draw_and_swap);
    configure(&hooks[3], base, SCHEDULER_BEGIN_FRAME, scheduler_begin);
    configure(&hooks[4], base, NATIVE_VISIBILITY, native_visibility);
    configure(&hooks[5], base, RWHV_SHOW, rwhv_show);
    configure(&hooks[6], base, SUSPEND, suspend);
    configure(&hooks[7], base, UNSUSPEND, unsuspend);
    configure(&hooks[8], base, VIZ_SET_VISIBLE, viz_visible);
    configure(&hooks[9], base, SCHEDULER_SET_VISIBLE, scheduler_visible);
    configure(&hooks[10], base, ROOT_SET_VISIBLE, root_visible);
    configure(&hooks[11], base, UPDATE_LAYER_TREE, update_layer);
    configure(&hooks[12], base, GOT_LAYER_FRAME, got_layer);
    configure(&hooks[13], base, TIME_SOURCE_SET_ACTIVE, time_source_active);
    configure(&hooks[14], base, TIME_SOURCE_TICK, time_source_tick);
    configure(&hooks[15], base, BEGIN_SOURCE_ADD, begin_source_add);
    configure(&hooks[16], base, BEGIN_SOURCE_TICK, begin_source_tick);
    configure(&hooks[17], base, SET_NEEDS_ONE_FRAME, set_needs_one_frame);
    configure(&hooks[18], base, ISSUE_TO_OBSERVER, issue_to_observer);
    configure(&hooks[19], base, OBSERVER_ON_FRAME, observer_on_frame);
    configure(&hooks[20], base, SCHEDULER_DERIVED_FRAME, scheduler_derived_frame);
}
