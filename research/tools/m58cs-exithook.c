/* darling-lol M58cs: capture who exits in a guest process.
 * Loaded in every guest process via DYLD_INSERT_LIBRARIES; inline-hooks
 * exit/_exit/abort and prints the immediate caller with image+offset+symbol.
 */
extern int printf(const char *, ...);
extern int fflush(void *);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern void *dlsym(void *, const char *);
extern void *dlopen(const char *, int);
extern int dladdr(const void *, void *);

struct dlinfo { const char *fname; void *fbase; const char *sname; void *saddr; };

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
static void uninstall(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) {
    struct hook *h = &H[nH++];
    h->p = (unsigned char *) addr; h->fn = fn; install(h); return h;
}

static void report(const char *what, int status, void *caller) {
    struct dlinfo di;
    di.fname = 0; di.fbase = 0; di.sname = 0; di.saddr = 0;
    dladdr(caller, &di);
    printf("XITHOOK pid=%d %s status=%d caller=%p img=%s off=0x%lx sym=%s\n",
        getpid(), what, status, caller,
        di.fname ? di.fname : "?",
        (unsigned long) ((char *) caller - (char *) (di.fbase ? di.fbase : 0)),
        di.sname ? di.sname : "?");
    fflush(0);
}

static struct hook *He, *H_e, *Ha;

static void f_exit(int status) {
    report("exit", status, __builtin_return_address(0));
    uninstall(He); ((void (*)(int)) He->p)(status);
}
static void f__exit(int status) {
    report("_exit", status, __builtin_return_address(0));
    uninstall(H_e); ((void (*)(int)) H_e->p)(status);
}
static void f_abort(void) {
    report("abort", -1, __builtin_return_address(0));
    uninstall(Ha); ((void (*)(void)) Ha->p)();
}

__attribute__((constructor)) static void boot(void) {
    void *pe = dlsym((void *) -2, "exit");
    void *p_e = dlsym((void *) -2, "_exit");
    void *pa = dlsym((void *) -2, "abort");
    printf("XITHOOK boot pid=%d exit=%p _exit=%p abort=%p\n", getpid(), pe, p_e, pa); fflush(0);
    if (pe) He = mk(pe, (void *) f_exit);
    if (p_e) H_e = mk(p_e, (void *) f__exit);
    if (pa) Ha = mk(pa, (void *) f_abort);
}
