/* darling-lol M58du: full notification chain in one run.
 * renderer: content::RenderFrameImpl::DidDispatchDOMContentLoadedEvent  base+0x6838350
 * renderer: LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent        base+0x24c3970
 * browser : LocalFrameHostStubDispatch::Accept(LocalFrameHost*, Message*) base+0x1331e90
 * browser : RenderFrameHostImpl::DidDispatchDOMContentLoadedEvent        base+0x2cc6850
 * browser : non-virtual thunk ...DidDispatchDOMContentLoadedEvent        base+0x2cc6890
 * browser : RenderFrameHostImpl::DidFinishLoad                           base+0x2cc4e00
 * browser : non-virtual thunk ...DidFinishLoad                           base+0x2cc4e80
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
static struct hook H[16]; static int nH = 0;
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

static struct hook *H1,*H2,*H3,*H4,*H5,*H6,*H7;
static void log1(const char *tag) { printf("CHAINHOOK %-52s pid=%d\n", tag, getpid()); fflush(0); }
static void f1(void *s) { log1("R RenderFrameImpl::DidDispatchDOMContentLoadedEvent"); unhook(H1); ((void(*)(void*))H1->p)(s); install(H1); }
static void f2(void *s) { log1("R LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent"); unhook(H2); ((void(*)(void*))H2->p)(s); install(H2); }
static void f3(void *i, void *m) { log1("B LocalFrameHostStubDispatch::Accept"); unhook(H3); ((void(*)(void*,void*))H3->p)(i,m); install(H3); }
static void f4(void *s) { log1("B RenderFrameHostImpl::DidDispatchDOMContentLoadedEvent"); unhook(H4); ((void(*)(void*))H4->p)(s); install(H4); }
static void f5(void *s) { log1("B thunk RenderFrameHostImpl::DidDispatchDOMContentLoadedEvent"); unhook(H5); ((void(*)(void*))H5->p)(s); install(H5); }
static void f6(void *s, void *u) { log1("B RenderFrameHostImpl::DidFinishLoad"); unhook(H6); ((void(*)(void*,void*))H6->p)(s,u); install(H6); }
static void f7(void *s, void *u) { log1("B thunk RenderFrameHostImpl::DidFinishLoad"); unhook(H7); ((void(*)(void*,void*))H7->p)(s,u); install(H7); }

static unsigned char *base = 0; static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) { const char *nm = _dyld_get_image_name(i); if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; } }
    if (!base) return;
    installed = 1;
    H1 = mk(base + 0x6838350, (void *) f1);
    H2 = mk(base + 0x24c3970, (void *) f2);
    H3 = mk(base + 0x1331e90, (void *) f3);
    H4 = mk(base + 0x2cc6850, (void *) f4);
    H5 = mk(base + 0x2cc6890, (void *) f5);
    H6 = mk(base + 0x2cc4e00, (void *) f6);
    H7 = mk(base + 0x2cc4e80, (void *) f7);
    printf("CHAINHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("CHAINHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
