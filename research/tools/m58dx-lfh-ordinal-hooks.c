/* darling-lol M58dx: decisively decode WHICH blink::mojom::LocalFrameHost method
 * reaches the browser's dispatcher, and bracket the two load notifications.
 *
 * Addresses (Electron 22.3.27 x64, breakpad Symbol file verified, base = the
 * Electron Framework Mach-O header):
 *   renderer send : blink::mojom::blink::LocalFrameHostProxy::
 *                     DidDispatchDOMContentLoadedEvent()   base+0x24c3970
 *                   blink::mojom::blink::LocalFrameHostProxy::
 *                     DidFinishLoad(blink::KURL const&)      base+0x24c3020
 *   browser recv  : blink::mojom::LocalFrameHostStubDispatch::Accept
 *                     (blink::mojom::LocalFrameHost*, mojo::Message*) base+0x1331e90
 *   browser impl  : content::RenderFrameHostImpl::
 *                     DidDispatchDOMContentLoadedEvent()    base+0x2cc6850
 *                   content::RenderFrameHostImpl::
 *                     DidFinishLoad(GURL const&)             base+0x2cc4e00
 *
 * The key advance over M58dv/M58dw: the mojom method ordinal is NOT at
 * `payload()-24`.  Disassembling `Accept` and `LocalFrameHost::MessageToMethodInfo_`
 * shows both read it as  `*(uint32_t*)(*(void**)(msg + 0x18) + 0xc)`.
 * `Accept` compares it against, among others,
 *   0x4ced459c = DidFinishLoad
 *   0x10f795c8 = DidDispatchDOMContentLoadedEvent
 * (`Proxy::DidFinishLoad` builds its Message with 0x4ced459c; the DCL proxy with
 * 0x10f795c8).  So an `Accept` entry with either ordinal IS one of the two
 * notifications - no cross-process log-ordering guesswork.
 *
 * Only low-perturbation hooks: Accept fires O(few), the sends O(2), the impls O(2).
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

#define ORD_DID_FINISH_LOAD   0x4ced459cu
#define ORD_DCL               0x10f795c8u

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

static struct hook *HS_dcl, *HS_fl, *HA, *HI_dcl, *HI_fl;
static unsigned long c_accept = 0, c_send_dcl = 0, c_send_fl = 0;

/* ---- renderer -> browser sends (proxy) ---- */
static void f_send_dcl(void *self) {
    c_send_dcl++;
    printf("M58DX SEND_DCL pid=%d n=%lu\n", getpid(), c_send_dcl); fflush(0);
    unhook(HS_dcl); ((void(*)(void*))HS_dcl->p)(self); install(HS_dcl);
}
static void f_send_fl(void *self, void *kurl) {
    c_send_fl++;
    printf("M58DX SEND_FL pid=%d n=%lu\n", getpid(), c_send_fl); fflush(0);
    unhook(HS_fl); ((void(*)(void*,void*))HS_fl->p)(self, kurl); install(HS_fl);
}

/* ---- browser -> impl ---- */
static void f_impl_dcl(void *self) {
    printf("M58DX IMPL_DCL pid=%d\n", getpid()); fflush(0);
    unhook(HI_dcl); ((void(*)(void*))HI_dcl->p)(self); install(HI_dcl);
}
static void f_impl_fl(void *self, void *gurl) {
    printf("M58DX IMPL_FL pid=%d\n", getpid()); fflush(0);
    unhook(HI_fl); ((void(*)(void*,void*))HI_fl->p)(self, gurl); install(HI_fl);
}

/* ---- browser Mojo dispatch of blink::mojom::LocalFrameHost ---- */
static void f_accept(void *impl, void *msg) {
    void *hdr = 0; unsigned ord = 0;
    const char *tag = "";
    if (msg) {
        hdr = *(void **)((char *)msg + 0x18);
        if (hdr) ord = *(unsigned *)((char *)hdr + 0xc);
    }
    if (ord == ORD_DID_FINISH_LOAD) tag = " <= DidFinishLoad";
    else if (ord == ORD_DCL)         tag = " <= DidDispatchDOMContentLoadedEvent";
    c_accept++;
    printf("M58DX ACCEPT pid=%d n=%lu ordinal=0x%08x%s\n", getpid(), c_accept, ord, tag);
    fflush(0);
    unhook(HA); ((void(*)(void*,void*))HA->p)(impl, msg); install(HA);
}

static unsigned char *base = 0; static int installed = 0;
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
    HS_dcl = mk(base + 0x24c3970, (void *) f_send_dcl);
    HS_fl  = mk(base + 0x24c3020, (void *) f_send_fl);
    HA     = mk(base + 0x1331e90, (void *) f_accept);
    HI_dcl = mk(base + 0x2cc6850, (void *) f_impl_dcl);
    HI_fl  = mk(base + 0x2cc4e00, (void *) f_impl_fl);
    printf("M58DX install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("M58DX boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
