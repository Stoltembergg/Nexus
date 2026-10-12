/* darling-lol M58di: renderer navigation-pipeline hooks.
 * Logs whether the renderer receives/commits a navigation:
 *   content::RenderFrameImpl::CommitNavigationWithParams = base+0x682eb70
 *   blink::DocumentLoader::CommitNavigation()             = base+0x590cd70
 *   content::RenderFrameImpl::DidCommitNavigation(...)    = base+0x6834ba0
 * Installed via _dyld_register_func_for_add_image.
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
extern void *pthread_self(void);

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

static unsigned long c_commit = 0, c_doc = 0, c_did = 0;
static struct hook *HA, *HB, *HC;

#define LOG(name, ctr) do { \
    (ctr)++; \
    if ((ctr) <= 20) { \
        printf("NAVHOOK %s pid=%d n=%lu main=%d\n", (name), getpid(), (ctr), \
               (unsigned long) pthread_self() == (unsigned long) (void *) (unsigned long) getpid()); \
        fflush(0); \
    } \
} while (0)

/* CommitNavigationWithParams(this, ...): rdi=this */
static void f_commit(void *self) {
    LOG("CommitNavigationWithParams", c_commit);
    unhook(HA); ((void (*)(void *)) HA->p)(self); install(HA);
}
/* DocumentLoader::CommitNavigation(this): rdi=this */
static void f_doc(void *self) {
    LOG("DocumentLoader::CommitNavigation", c_doc);
    unhook(HB); ((void (*)(void *)) HB->p)(self); install(HB);
}
/* DidCommitNavigation(this, ...): rdi=this */
static void f_did(void *self) {
    LOG("RenderFrameImpl::DidCommitNavigation", c_did);
    unhook(HC); ((void (*)(void *)) HC->p)(self); install(HC);
}

static unsigned char *base = 0;
static int installed = 0;

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
    HA = mk(base + 0x682eb70, (void *) f_commit);
    HB = mk(base + 0x590cd70, (void *) f_doc);
    HC = mk(base + 0x6834ba0, (void *) f_did);
    printf("NAVHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }

__attribute__((constructor)) static void boot(void) {
    printf("NAVHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
