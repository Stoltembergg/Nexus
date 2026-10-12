/* darling-lol M58dk: renderer -> browser outgoing notification hooks.
 * Logs whether the renderer SENDS the commit/load notifications:
 *   content::mojom::FrameHostProxy::DidCommitProvisionalLoad   base+0x14bdf00
 *   content::mojom::FrameHostProxy::DidCommitSameDocumentNavigation base+0x14be0c0
 *   blink::mojom::blink::LocalFrameHostProxy::DidFinishLoad    base+0x24c3020
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

static unsigned long c_dcp = 0, c_same = 0, c_dfl = 0;
static struct hook *HD, *HS, *HF;

static void log1(const char *name, unsigned long *ctr) {
    (*ctr)++;
    if (*ctr <= 30) { printf("OUTHOOK %s pid=%d n=%lu\n", name, getpid(), *ctr); fflush(0); }
}

static void f_dcp(void *self, void *a, void *b) {
    log1("FrameHostProxy::DidCommitProvisionalLoad", &c_dcp);
    unhook(HD); ((void (*)(void *, void *, void *)) HD->p)(self, a, b); install(HD);
}
static void f_same(void *self, void *a, void *b) {
    log1("FrameHostProxy::DidCommitSameDocumentNavigation", &c_same);
    unhook(HS); ((void (*)(void *, void *, void *)) HS->p)(self, a, b); install(HS);
}
static void f_dfl(void *self, void *url) {
    log1("LocalFrameHostProxy::DidFinishLoad", &c_dfl);
    unhook(HF); ((void (*)(void *, void *)) HF->p)(self, url); install(HF);
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
    HD = mk(base + 0x14bdf00, (void *) f_dcp);
    HS = mk(base + 0x14be0c0, (void *) f_same);
    HF = mk(base + 0x24c3020, (void *) f_dfl);
    printf("OUTHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }

__attribute__((constructor)) static void boot(void) {
    printf("OUTHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
