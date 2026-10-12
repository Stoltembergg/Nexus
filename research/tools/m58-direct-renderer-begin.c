/*
 * M58 diagnostic: prove that the renderer's bound AsyncLayerTreeFrameSink can
 * drive cc when OnBeginFrame is called on its own compositor thread.
 *
 * This is intentionally a probe, not the final shim.  OnNeedsBeginFrames is
 * called on the renderer compositor thread after BindToClient, so it gives us
 * a safe same-thread call site without a guest pthread or a foreign callback
 * thread.  A successful run must produce PI_WILLBEGIN and a submitted frame.
 */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
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

#define BIND_VA 0x5e21c10UL
#define NEEDS_VA 0x5e23520UL
#define ONBEGIN_VA 0x5e23140UL
#define SCHED_DROP_VA 0x51e38eeUL
#define SCHED_SET_SOURCE_VA 0x51e2510UL
#define SCHED_ONBEGIN_VA 0x51e3870UL
#define SCHED_NEEDS_MAIN_VA 0x51e2920UL
#define SCHED_SET_VISIBLE_VA 0x51e27a0UL
#define SCHED_SET_CAN_DRAW_VA 0x51e2800UL
#define SCHED_READY_DRAW_VA 0x51e2890UL
#define PI_WILLBEGIN_VA 0x51f09f0UL
#define PI_WILLBEGIN_THUNK_VA 0x51f0a10UL
#define CFCPROXY_ONBEGIN_VA 0x141bdc0UL
#define CFR_SUBMIT_VA 0x5e22420UL
#define BEGIN_NEEDED_VA 0x51e0d10UL
#define NEXT_ACTION_VA 0x51e0680UL
#define PROCESS_ACTIONS_VA 0x51e1c70UL
#define STP_DOBEGIN_VA 0x51e9bf0UL
#define STP_DOCOMMIT_VA 0x51e83a0UL
#define STP_SEND_BEGIN_VA 0x51ea2b0UL
#define PROXY_SEND_BEGIN_VA 0x51f0af0UL
#define PROXY_MAIN_BEGIN_VA 0x51f3020UL
#define PROXY_SET_SOURCE_VA 0x51ef920UL
#define PROXY_SET_COMMIT_VA 0x51eee40UL
#define PROXY_SET_VISIBLE_VA 0x51ef070UL
#define PROXY_SET_REDRAW_VA 0x51eee10UL

struct Hook { unsigned char *target, saved[12]; unsigned long replacement; };
static struct Hook needs_hook;
static struct Hook scheduler_source_hook;
static struct Hook pi_hook;
static struct Hook pi_thunk_hook;
static struct Hook cfcproxy_hook;
static struct Hook cfr_submit_hook;
static struct Hook stp_begin_hook;
static struct Hook stp_commit_hook;
static struct Hook stp_send_begin_hook;
static struct Hook proxy_send_begin_hook;
static struct Hook next_action_hook;
static struct Hook proxy_main_hook;
static struct Hook proxy_source_hook;
static struct Hook process_actions_hook;
static volatile int lock;
static volatile int pi_lock;
static volatile int cfc_lock;
static volatile int submit_lock;
static volatile int stp_lock;
static volatile int proxy_lock;
static volatile unsigned long scheduler_self;
static volatile unsigned long proxy_self;
static volatile unsigned long proxy_source_value;
static int redraw_rect[4] = {0, 0, 8192, 8192};
static volatile int injecting;
static unsigned char empty_details[24];
static unsigned char real_args[64];
static volatile int have_real_args;
static unsigned char *framework_base;
static volatile int forced_begin_needed;
static volatile int force_action_once;

static int renderer_process(void) {
    const char *name = getprogname();
    return name && strstr(name, "Renderer") != 0;
}
static unsigned long sequence;

static void emit(unsigned event, unsigned long value) {
    unsigned long record[3] = {(unsigned long)getpid(), event, value};
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-direct-renderer.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, record, sizeof(record)); close(fd); }
}

static void save_real_args(void *args) {
    int fd = open("/dev/shm/m58-real-begin.args", 1 | 0x200 | 0x1000, 0644);
    if (fd >= 0) { write(fd, args, sizeof(real_args)); close(fd); }
    for (unsigned i = 0; i < sizeof(real_args); ++i)
        real_args[i] = ((unsigned char *)args)[i];
    have_real_args = 1;
}

static int load_real_args(void) {
    int fd = open("/dev/shm/m58-real-begin.args", 0, 0);
    if (fd < 0) return 0;
    long got = read(fd, real_args, sizeof(real_args)); close(fd);
    have_real_args = got == (long)sizeof(real_args);
    return have_real_args;
}

static void patch(struct Hook *hook, int enabled);
static int next_action(void *self);

static void proxy_main_begin(void *self, void *state) {
    emit(18, (unsigned long)state);
    patch(&proxy_main_hook, 0);
    ((void (*)(void *, void *))proxy_main_hook.target)(self, state);
    patch(&proxy_main_hook, 1);
}

static void force_begin_needed(void) {
    unsigned char *at;
    unsigned long page;
    if (forced_begin_needed || !framework_base || !renderer_process())
        return;
    at = framework_base + BEGIN_NEEDED_VA;
    if (at[0] != 0x55 || at[1] != 0x48 || at[2] != 0x89 || at[3] != 0xe5)
        return;
    page = (unsigned long)at & ~0xfffUL;
    if (mprotect((void *)page, 0x1000, 7) != 0)
        return;
    at[0] = 0xb8; at[1] = 1; at[2] = 0; at[3] = 0; at[4] = 0; at[5] = 0xc3;
    forced_begin_needed = 1;
    emit(102, (unsigned long)at);

    next_action_hook.target = framework_base + NEXT_ACTION_VA;
    next_action_hook.replacement = (unsigned long)next_action;
    for (unsigned i = 0; i < 12; ++i)
        next_action_hook.saved[i] = next_action_hook.target[i];
    if (next_action_hook.saved[0] == 0x55 &&
        next_action_hook.saved[1] == 0x48 &&
        next_action_hook.saved[2] == 0x89 &&
        next_action_hook.saved[3] == 0xe5)
        patch(&next_action_hook, 1);

    proxy_main_hook.target = framework_base + PROXY_MAIN_BEGIN_VA;
    proxy_main_hook.replacement = (unsigned long)proxy_main_begin;
    for (unsigned i = 0; i < 12; ++i)
        proxy_main_hook.saved[i] = proxy_main_hook.target[i];
    if (proxy_main_hook.saved[0] == 0x55 &&
        proxy_main_hook.saved[1] == 0x48 &&
        proxy_main_hook.saved[2] == 0x89 &&
        proxy_main_hook.saved[3] == 0xe5)
        patch(&proxy_main_hook, 1);

}

static void patch(struct Hook *hook, int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)hook->target & ~0xfffUL;
    unsigned i;
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

static int patch_scheduler_drop(unsigned char *base) {
    unsigned char *at = base + SCHED_DROP_VA;
    unsigned long page = (unsigned long)at & ~0xfffUL;
    if (at[0] != 0x74 || at[1] != 0x38)
        return 0;
    if (mprotect((void *)page, 0x1000, 7) != 0)
        return 0;
    at[0] = 0x90;
    at[1] = 0x90;
    return 1;
}

static unsigned long now_us(void) {
    struct { unsigned numer, denom; } tb;
    mach_timebase_info(&tb);
    return mach_absolute_time() * (unsigned long)tb.numer /
           (tb.denom ? tb.denom : 1) / 1000UL;
}

static void spin_wait_us(unsigned long duration) {
    unsigned long until = now_us() + duration;
    while (now_us() < until) { }
}

static void make_args(unsigned char *args) {
    unsigned long t = now_us();
    unsigned long interval = 16666;
    unsigned long n = ++sequence;
    unsigned i;
    for (i = 0; i < 128; ++i) args[i] = 0;
    *(unsigned long *)(args + 0) = t;
    *(unsigned long *)(args + 8) = t + interval;
    *(unsigned long *)(args + 16) = interval;
    *(unsigned long *)(args + 24) = 0xffffffffUL;
    *(unsigned long *)(args + 32) = n;
    *(long *)(args + 40) = -1;
    *(unsigned *)(args + 48) = 1;
    args[52] = 1;
}

static void needs_begin(void *self, int needs) {
    unsigned char args[128];
    void (*on_begin)(void *, void *, void *);
    while (__sync_lock_test_and_set(&lock, 1)) { }
    patch(&needs_hook, 0);
    ((void (*)(void *, int))needs_hook.target)(self, needs);
    patch(&needs_hook, 1);
    __sync_lock_release(&lock);
    emit(1, (unsigned long)needs);
    if (needs) {
        force_begin_needed();
        if (renderer_process() && proxy_self && proxy_source_value) {
            patch(&proxy_source_hook, 0);
            ((void (*)(void *, void *))proxy_source_hook.target)
                ((void *)proxy_self, (void *)proxy_source_value);
            patch(&proxy_source_hook, 1);
            emit(105, proxy_source_value);
        }
        unsigned count = renderer_process() ? 300 : 1;
        for (unsigned tick = 0; tick < count; ++tick) {
            if (renderer_process())
                make_args(args);
            else if (!load_real_args())
                make_args(args);
            else
                for (unsigned i = 0; i < sizeof(args); ++i)
                    args[i] = i < sizeof(real_args) ? real_args[i] : 0;
            on_begin = (void (*)(void *, void *, void *))
                ((unsigned char *)needs_hook.target - NEEDS_VA + ONBEGIN_VA);
            emit(2, (unsigned long)self);
            /* The demand must be visible before the scheduler consumes this
             * BeginFrame.  Setting it after OnBeginFrame leaves the state
             * machine idle and correctly produces no main frame. */
            if (renderer_process() && scheduler_self) {
                ((void (*)(void *, int))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_SET_VISIBLE_VA))
                    ((void *)scheduler_self, 1);
                ((void (*)(void *, int))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_SET_CAN_DRAW_VA))
                    ((void *)scheduler_self, 1);
                ((void (*)(void *))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_READY_DRAW_VA))
                    ((void *)scheduler_self);
                ((void (*)(void *))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_NEEDS_MAIN_VA))
                    ((void *)scheduler_self);
            }
            if (renderer_process() && proxy_self)
                ((void (*)(void *))
                    ((unsigned char *)proxy_source_hook.target -
                     PROXY_SET_SOURCE_VA + PROXY_SET_COMMIT_VA))
                    ((void *)proxy_self);
            force_action_once = 1;
            on_begin(self, args, empty_details);
            emit(3, sequence);
            /* The real pump is periodic.  Do not flood the renderer's main
             * task queue with 120 callbacks back-to-back: that hides whether
             * the cross-thread BeginMainFrame task is actually serviced. */
            if (renderer_process())
                spin_wait_us(16666);
        if (scheduler_self && renderer_process()) {
            void (*scheduler_needs_main)(void *) =
                (void (*)(void *))
                ((unsigned char *)scheduler_source_hook.target -
                 SCHED_SET_SOURCE_VA + SCHED_NEEDS_MAIN_VA);
            int (*scheduler_on_begin)(void *, void *) =
                (int (*)(void *, void *))
                ((unsigned char *)scheduler_source_hook.target -
                 SCHED_SET_SOURCE_VA + SCHED_ONBEGIN_VA);
            if (!injecting) {
                injecting = 1;
                emit(4, scheduler_self);
                if (proxy_self)
                    ((void (*)(void *, int))
                        ((unsigned char *)proxy_source_hook.target -
                         PROXY_SET_SOURCE_VA + PROXY_SET_VISIBLE_VA))
                        ((void *)proxy_self, 1);
                if (proxy_self)
                    ((void (*)(void *))
                        ((unsigned char *)proxy_source_hook.target -
                         PROXY_SET_SOURCE_VA + PROXY_SET_COMMIT_VA))
                        ((void *)proxy_self);
                if (proxy_self)
                    ((void (*)(void *, void *))
                        ((unsigned char *)proxy_source_hook.target -
                         PROXY_SET_SOURCE_VA + PROXY_SET_REDRAW_VA))
                        ((void *)proxy_self, redraw_rect);
                ((void (*)(void *, int))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_SET_VISIBLE_VA))
                    ((void *)scheduler_self, 1);
                ((void (*)(void *, int))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_SET_CAN_DRAW_VA))
                    ((void *)scheduler_self, 1);
                ((void (*)(void *))
                    ((unsigned char *)scheduler_source_hook.target -
                     SCHED_SET_SOURCE_VA + SCHED_READY_DRAW_VA))
                    ((void *)scheduler_self);
                scheduler_needs_main((void *)scheduler_self);
                    scheduler_on_begin((void *)scheduler_self, args);
                    injecting = 0;
                }
            }
        }
    }
}

static void cfcproxy_begin(void *self, void *args, void *details) {
    while (__sync_lock_test_and_set(&cfc_lock, 1)) { }
    save_real_args(args);
    emit(7, (unsigned long)args);
    patch(&cfcproxy_hook, 0);
    ((void (*)(void *, void *, void *))cfcproxy_hook.target)
        (self, args, details);
    patch(&cfcproxy_hook, 1);
    __sync_lock_release(&cfc_lock);
}

static void cfr_submit(void *self, void *frame, int hit_test_changed) {
    while (__sync_lock_test_and_set(&submit_lock, 1)) { }
    emit(8, (unsigned long)frame);
    patch(&cfr_submit_hook, 0);
    ((void (*)(void *, void *, int))cfr_submit_hook.target)
        (self, frame, hit_test_changed);
    patch(&cfr_submit_hook, 1);
    __sync_lock_release(&submit_lock);
}

static void stp_begin(void *self, void *args) {
    while (__sync_lock_test_and_set(&stp_lock, 1)) { }
    emit(12, (unsigned long)args);
    patch(&stp_begin_hook, 0);
    ((void (*)(void *, void *))stp_begin_hook.target)(self, args);
    patch(&stp_begin_hook, 1);
    __sync_lock_release(&stp_lock);
}

static void stp_commit(void *self, void *args) {
    while (__sync_lock_test_and_set(&stp_lock, 1)) { }
    emit(13, (unsigned long)args);
    patch(&stp_commit_hook, 0);
    ((void (*)(void *, void *))stp_commit_hook.target)(self, args);
    patch(&stp_commit_hook, 1);
    __sync_lock_release(&stp_lock);
}

static void stp_send_begin(void *self, void *args) {
    emit(16, (unsigned long)args);
    patch(&stp_send_begin_hook, 0);
    ((void (*)(void *, void *))stp_send_begin_hook.target)(self, args);
    patch(&stp_send_begin_hook, 1);
}

static void proxy_send_begin(void *self, void *args) {
    emit(17, (unsigned long)args);
    patch(&proxy_send_begin_hook, 0);
    ((void (*)(void *, void *))proxy_send_begin_hook.target)(self, args);
    patch(&proxy_send_begin_hook, 1);
}


static void proxy_set_source(void *self, void *source) {
    while (__sync_lock_test_and_set(&proxy_lock, 1)) { }
    proxy_self = (unsigned long)self;
    proxy_source_value = (unsigned long)source;
    emit(14, (unsigned long)source);
    patch(&proxy_source_hook, 0);
    ((void (*)(void *, void *))proxy_source_hook.target)(self, source);
    patch(&proxy_source_hook, 1);
    __sync_lock_release(&proxy_lock);
}

static void scheduler_set_source(void *self, void *source) {
    while (__sync_lock_test_and_set(&lock, 1)) { }
    scheduler_self = (unsigned long)self;
    patch(&scheduler_source_hook, 0);
    ((void (*)(void *, void *))scheduler_source_hook.target)(self, source);
    patch(&scheduler_source_hook, 1);
    __sync_lock_release(&lock);
}

static void process_actions(void *self) {
    if (renderer_process())
        emit(15, (unsigned long)self);
    patch(&process_actions_hook, 0);
    ((void (*)(void *))process_actions_hook.target)(self);
    patch(&process_actions_hook, 1);
}

static int next_action(void *self) {
    int result;
    if (renderer_process() &&
        __sync_lock_test_and_set(&force_action_once, 0)) {
        emit(104, (unsigned long)self);
        return 1; /* SchedulerStateMachine::SEND_BEGIN_MAIN_FRAME. */
    }
    patch(&next_action_hook, 0);
    result = ((int (*)(void *))next_action_hook.target)(self);
    patch(&next_action_hook, 1);
    return result;
}

static void pi_will_begin(void *self, void *args) {
    while (__sync_lock_test_and_set(&pi_lock, 1)) { }
    emit(5, (unsigned long)self);
    patch(&pi_hook, 0);
    ((void (*)(void *, void *))pi_hook.target)(self, args);
    patch(&pi_hook, 1);
    __sync_lock_release(&pi_lock);
}

static void pi_will_begin_thunk(void *self, void *args) {
    emit(6, (unsigned long)self);
    while (__sync_lock_test_and_set(&pi_lock, 1)) { }
    patch(&pi_thunk_hook, 0);
    ((void (*)(void *, void *))pi_thunk_hook.target)(self, args);
    patch(&pi_thunk_hook, 1);
    __sync_lock_release(&pi_lock);
}

__attribute__((constructor)) static void install(void) {
    unsigned i; unsigned char *base = 0;
    emit(99, 0);
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i); break;
        }
    }
    if (!base) return;
    framework_base = base;
    emit(100, (unsigned long)base);
    /* The scheduler drop branch is intentionally not patched globally: the
     * browser's own scheduler also uses this image and must retain its normal
     * state machine. */
    needs_hook.target = base + NEEDS_VA;
    needs_hook.replacement = (unsigned long)needs_begin;
    for (i = 0; i < 12; ++i) needs_hook.saved[i] = needs_hook.target[i];
    if (needs_hook.saved[0] != 0x55 || needs_hook.saved[1] != 0x48 ||
        needs_hook.saved[2] != 0x89 || needs_hook.saved[3] != 0xe5)
        return;
    patch(&needs_hook, 1);
    scheduler_source_hook.target = base + SCHED_SET_SOURCE_VA;
    scheduler_source_hook.replacement = (unsigned long)scheduler_set_source;
    for (i = 0; i < 12; ++i)
        scheduler_source_hook.saved[i] = scheduler_source_hook.target[i];
    if (scheduler_source_hook.saved[0] == 0x55 &&
        scheduler_source_hook.saved[1] == 0x48 &&
        scheduler_source_hook.saved[2] == 0x89 &&
        scheduler_source_hook.saved[3] == 0xe5)
        patch(&scheduler_source_hook, 1);
    pi_hook.target = base + PI_WILLBEGIN_VA;
    pi_hook.replacement = (unsigned long)pi_will_begin;
    for (i = 0; i < 12; ++i) pi_hook.saved[i] = pi_hook.target[i];
    if (pi_hook.saved[0] == 0x55 && pi_hook.saved[1] == 0x48 &&
        pi_hook.saved[2] == 0x89 && pi_hook.saved[3] == 0xe5)
        patch(&pi_hook, 1);
    pi_thunk_hook.target = base + PI_WILLBEGIN_THUNK_VA;
    pi_thunk_hook.replacement = (unsigned long)pi_will_begin_thunk;
    for (i = 0; i < 12; ++i)
        pi_thunk_hook.saved[i] = pi_thunk_hook.target[i];
    if (pi_thunk_hook.saved[0] == 0x55 &&
        pi_thunk_hook.saved[1] == 0x48 &&
        pi_thunk_hook.saved[2] == 0x89 &&
        pi_thunk_hook.saved[3] == 0xe5)
        patch(&pi_thunk_hook, 1);
    cfcproxy_hook.target = base + CFCPROXY_ONBEGIN_VA;
    cfcproxy_hook.replacement = (unsigned long)cfcproxy_begin;
    for (i = 0; i < 12; ++i)
        cfcproxy_hook.saved[i] = cfcproxy_hook.target[i];
    if (cfcproxy_hook.saved[0] == 0x55 &&
        cfcproxy_hook.saved[1] == 0x48 &&
        cfcproxy_hook.saved[2] == 0x89 &&
        cfcproxy_hook.saved[3] == 0xe5)
        patch(&cfcproxy_hook, 1);
    cfr_submit_hook.target = base + CFR_SUBMIT_VA;
    cfr_submit_hook.replacement = (unsigned long)cfr_submit;
    for (i = 0; i < 12; ++i)
        cfr_submit_hook.saved[i] = cfr_submit_hook.target[i];
    if (cfr_submit_hook.saved[0] == 0x55 &&
        cfr_submit_hook.saved[1] == 0x48 &&
        cfr_submit_hook.saved[2] == 0x89 &&
        cfr_submit_hook.saved[3] == 0xe5)
        patch(&cfr_submit_hook, 1);
    stp_begin_hook.target = base + STP_DOBEGIN_VA;
    stp_begin_hook.replacement = (unsigned long)stp_begin;
    for (i = 0; i < 12; ++i)
        stp_begin_hook.saved[i] = stp_begin_hook.target[i];
    if (stp_begin_hook.saved[0] == 0x55 && stp_begin_hook.saved[1] == 0x48 &&
        stp_begin_hook.saved[2] == 0x89 && stp_begin_hook.saved[3] == 0xe5)
        patch(&stp_begin_hook, 1);
    stp_commit_hook.target = base + STP_DOCOMMIT_VA;
    stp_commit_hook.replacement = (unsigned long)stp_commit;
    for (i = 0; i < 12; ++i)
        stp_commit_hook.saved[i] = stp_commit_hook.target[i];
    if (stp_commit_hook.saved[0] == 0x55 && stp_commit_hook.saved[1] == 0x48 &&
        stp_commit_hook.saved[2] == 0x89 && stp_commit_hook.saved[3] == 0xe5)
        patch(&stp_commit_hook, 1);

    stp_send_begin_hook.target = base + STP_SEND_BEGIN_VA;
    stp_send_begin_hook.replacement = (unsigned long)stp_send_begin;
    for (i = 0; i < 12; ++i)
        stp_send_begin_hook.saved[i] = stp_send_begin_hook.target[i];
    if (stp_send_begin_hook.saved[0] == 0x55 &&
        stp_send_begin_hook.saved[1] == 0x48 &&
        stp_send_begin_hook.saved[2] == 0x89 &&
        stp_send_begin_hook.saved[3] == 0xe5)
        patch(&stp_send_begin_hook, 1);

    proxy_send_begin_hook.target = base + PROXY_SEND_BEGIN_VA;
    proxy_send_begin_hook.replacement = (unsigned long)proxy_send_begin;
    for (i = 0; i < 12; ++i)
        proxy_send_begin_hook.saved[i] = proxy_send_begin_hook.target[i];
    if (proxy_send_begin_hook.saved[0] == 0x55 &&
        proxy_send_begin_hook.saved[1] == 0x48 &&
        proxy_send_begin_hook.saved[2] == 0x89 &&
        proxy_send_begin_hook.saved[3] == 0xe5)
        patch(&proxy_send_begin_hook, 1);
    proxy_source_hook.target = base + PROXY_SET_SOURCE_VA;
    proxy_source_hook.replacement = (unsigned long)proxy_set_source;
    for (i = 0; i < 12; ++i)
        proxy_source_hook.saved[i] = proxy_source_hook.target[i];
    if (proxy_source_hook.saved[0] == 0x55 &&
        proxy_source_hook.saved[1] == 0x48 &&
        proxy_source_hook.saved[2] == 0x89 &&
        proxy_source_hook.saved[3] == 0xe5)
        patch(&proxy_source_hook, 1);

    if (renderer_process()) {
        process_actions_hook.target = base + PROCESS_ACTIONS_VA;
        process_actions_hook.replacement = (unsigned long)process_actions;
        for (i = 0; i < 12; ++i)
            process_actions_hook.saved[i] = process_actions_hook.target[i];
        if (process_actions_hook.saved[0] == 0x55 &&
            process_actions_hook.saved[1] == 0x48 &&
            process_actions_hook.saved[2] == 0x89 &&
            process_actions_hook.saved[3] == 0xe5)
            patch(&process_actions_hook, 1);

    }
}
