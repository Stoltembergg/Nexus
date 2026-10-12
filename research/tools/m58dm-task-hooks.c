/* darling-lol M58dm: does the renderer main thread still run tasks after
 * FrameLoader::FinishedParsing?  Hooks:
 *   base::TaskAnnotator::RunTaskImpl(self, task)  base+0x37c06c0
 *   blink::FrameLoader::FinishedParsing()         base+0x5923bf0
 *   blink::Document::CheckCompletedInternal()     base+0x5f29450
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
static struct hook H[8]; static int nH = 0;
static void install(struct hook *h) {
    unsigned char *p = h->p; unsigned long pg = (unsigned long) p & ~0xFFFUL; int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return;
    for (i = 0; i < 12; i++) h->orig[i] = p[i];
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) h->fn; for (i = 0; i < 8; i++) p[2 + i] = (a >> (8 * i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
}
static void unhook(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) { struct hook *h = &H[nH++]; h->p = (unsigned char *) addr; h->fn = fn; install(h); return h; }

static unsigned long g_tasks = 0;
static struct hook *HRT, *HFFP, *HCC;

static void f_rt(void *self, void *task) {
    g_tasks++;
    if ((g_tasks % 500) == 0) { printf("TASKHOOK run pid=%d n=%lu\n", getpid(), g_tasks); fflush(0); }
    unhook(HRT); ((void (*)(void *, void *)) HRT->p)(self, task); install(HRT);
}
static void f_ffp(void *s) {
    printf("TASKHOOK FrameLoader::FinishedParsing pid=%d tasks_so_far=%lu\n", getpid(), g_tasks); fflush(0);
    unhook(HFFP); ((void (*)(void *)) HFFP->p)(s); install(HFFP);
}
static void f_cc(void *s) {
    printf("TASKHOOK CheckCompletedInternal pid=%d tasks_so_far=%lu\n", getpid(), g_tasks); fflush(0);
    unhook(HCC); ((void (*)(void *)) HCC->p)(s); install(HCC);
}

static unsigned char *base = 0; static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) { const char *nm = _dyld_get_image_name(i); if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; } }
    if (!base) return;
    installed = 1;
    HRT = mk(base + 0x37c06c0, (void *) f_rt);
    HFFP = mk(base + 0x5923bf0, (void *) f_ffp);
    HCC = mk(base + 0x5f29450, (void *) f_cc);
    printf("TASKHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("TASKHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
