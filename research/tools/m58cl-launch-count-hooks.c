/* darling-lol M58cm: count the child-process launch path, installed reliably
 * via _dyld_register_func_for_add_image (the browser's Electron Framework is
 * not present at constructor time).
 * Hooks: StartLaunchOnClientThread = base+0x2903770 (void(this))
 *        LaunchOnLauncherThread    = base+0x2903930 (void(this))
 */
extern int printf(const char *, ...);
extern int fflush(void *);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern void _dyld_register_func_for_add_image(void (*)(const void *, long));

struct hook { unsigned char *p; unsigned char orig[12]; void *fn; };
static struct hook H[8];
static int nH = 0;

static void install(struct hook *h) {
    unsigned char *p = h->p;
    unsigned long pg = (unsigned long) p & ~0xFFFUL;
    int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return;
    for (i = 0; i < 12; i++) h->orig[i] = p[i];
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) h->fn; for (i = 0; i < 8; i++) p[2 + i] = (a >> (8 * i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
}
static void unhook(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) {
    struct hook *h = &H[nH++];
    h->p = (unsigned char *) addr; h->fn = fn; install(h); return h;
}

static unsigned long c_sl = 0, c_ll = 0;
static struct hook *HSL, *HLL;
static unsigned char *base = 0;
static int installed = 0;

static void f_sl(void *self) {
    c_sl++;
    if (c_sl <= 3 || (c_sl % 2000) == 0) {
        printf("LOLCNT StartLaunchOnClientThread n=%lu pid=%d main=%d\n", c_sl, getpid(), (int) c_ll);
        fflush(0);
    }
    unhook(HSL); ((void (*)(void *)) HSL->p)(self); install(HSL);
}
static void f_ll(void *self) {
    c_ll++;
    if (c_ll <= 3 || (c_ll % 2000) == 0) {
        printf("LOLCNT LaunchOnLauncherThread n=%lu pid=%d\n", c_ll, getpid()); fflush(0);
    }
    unhook(HLL); ((void (*)(void *)) HLL->p)(self); install(HLL);
}

static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) {
        const char *nm = _dyld_get_image_name(i);
        if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; }
    }
    if (!base) return;
    installed = 1;
    HSL = mk(base + 0x2903770, (void *) f_sl);
    HLL = mk(base + 0x2903930, (void *) f_ll);
    printf("LOLCNT install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }

__attribute__((constructor)) static void boot(void) {
    printf("LOLCNT boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
