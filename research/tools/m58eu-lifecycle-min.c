/* darling-lol M58eu: minimal endpoint-lifecycle probe (cold paths only).
 *
 * Records, in the browser, the ChannelAssociatedGroupController endpoint
 * lifecycle for the LocalFrameHost interface id, alongside the two notification
 * proxy sends and the LFH stub dispatch.  No hot hooks, so it should not perturb.
 *
 *   proxies: DidDispatchDOMContentLoadedEvent base+0x24c3970, DidFinishLoad 0x24c3020
 *   LFH stub dispatch: base+0x1331e90
 *   lifecycle (id from the handle via ScopedInterfaceEndpointHandle::id 0x3b1a8f0;
 *              Close/PeerClosed take the id in esi):
 *     AttachEndpointClient 0x3e45730 / DetachEndpointClient 0x3e458d0
 *     CloseEndpointHandle  0x3e455d0 / OnPeerAssociatedEndpointClosed 0x3e463a0
 */
extern int printf(const char *, ...);
extern int fflush(void *);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern void *mmap(void *, unsigned long, int, int, int, long);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern void _dyld_register_func_for_add_image(void (*)(const void *, long));

#define ORD_DCL 0x10f795c8u
#define ORD_FL  0x4ced459cu
static const char *tag(unsigned o) {
    if (o == ORD_FL) return " DidFinishLoad";
    if (o == ORD_DCL) return " DidDispatchDOMContentLoadedEvent";
    return "";
}

struct thook { unsigned char *p; void *fn; unsigned char *tramp; int n; };
static struct thook TH[8]; static int nTH = 0;
static void *install_tramp(void *addr, void *fn, int n) {
    struct thook *t = &TH[nTH++];
    unsigned char *p = (unsigned char *) addr;
    unsigned long pg = (unsigned long) p & ~0xFFFUL;
    unsigned char *tr; int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return 0;
    tr = (unsigned char *) mmap(0, 0x1000, 7, 0x1002, -1, 0);
    if (!tr || tr == (void *) -1) return 0;
    for (i = 0; i < n; i++) tr[i] = p[i];
    tr[n] = 0x48; tr[n+1] = 0xB8;
    { unsigned long a = (unsigned long)(p + n); for (i = 0; i < 8; i++) tr[n+2+i] = (a >> (8*i)) & 0xFF; }
    tr[n+10] = 0xFF; tr[n+11] = 0xE0;
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) fn; for (i = 0; i < 8; i++) p[2+i] = (a >> (8*i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
    t->p = p; t->fn = fn; t->tramp = tr; t->n = n;
    return tr;
}
static unsigned ctr = 0;
static inline unsigned ord_of(void *m) { void *h = m ? *(void **)((char *)m + 0x18) : 0; return h ? *(unsigned *)((char *)h + 0xc) : 0; }

static unsigned (*p_handle_id)(const void *);
static int (*tramp_send_dcl)(void *);
static int (*tramp_send_fl)(void *, void *);
static int (*tramp_lfh)(void *, void *);
static void (*tramp_attach)(void *, void *, void *, void *);
static void (*tramp_detach)(void *, void *);
static void (*tramp_close)(void *, unsigned, void *);
static void (*tramp_peer)(void *, unsigned, void *);

static int f_send_dcl(void *self) { printf("M58EU n=%u SEND_DCL pid=%d\n", ++ctr, getpid()); fflush(0); return tramp_send_dcl(self); }
static int f_send_fl(void *self, void *kurl) { printf("M58EU n=%u SEND_FL pid=%d\n", ++ctr, getpid()); fflush(0); return tramp_send_fl(self, kurl); }
static int f_lfh(void *impl, void *msg) {
    unsigned o = ord_of(msg);
    printf("M58EU n=%u LFH_DISPATCH pid=%d ordinal=0x%08x%s\n", ++ctr, getpid(), o, tag(o)); fflush(0);
    return tramp_lfh(impl, msg);
}
static void f_attach(void *self, void *handle, void *client, void *runner) {
    printf("M58EU n=%u CAGC_ATTACH pid=%d ifid=%u\n", ++ctr, getpid(), p_handle_id ? p_handle_id(handle) : 0); fflush(0);
    tramp_attach(self, handle, client, runner);
}
static void f_detach(void *self, void *handle) {
    printf("M58EU n=%u CAGC_DETACH pid=%d ifid=%u\n", ++ctr, getpid(), p_handle_id ? p_handle_id(handle) : 0); fflush(0);
    tramp_detach(self, handle);
}
static void f_close(void *self, unsigned id, void *reason) {
    printf("M58EU n=%u CAGC_CLOSE pid=%d ifid=%u%s\n", ++ctr, getpid(), id, id == 3 ? " (LFH)" : ""); fflush(0);
    tramp_close(self, id, reason);
}
static void f_peer(void *self, unsigned id, void *reason) {
    printf("M58EU n=%u CAGC_PEERCLOSED pid=%d ifid=%u%s\n", ++ctr, getpid(), id, id == 3 ? " (LFH)" : ""); fflush(0);
    tramp_peer(self, id, reason);
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
    p_handle_id = (unsigned (*)(const void *)) (base + 0x3b1a8f0);
    tramp_send_dcl = install_tramp(base + 0x24c3970, (void *) f_send_dcl, 20);
    tramp_send_fl  = install_tramp(base + 0x24c3020, (void *) f_send_fl, 20);
    tramp_lfh      = install_tramp(base + 0x1331e90, (void *) f_lfh, 20);
    tramp_attach   = install_tramp(base + 0x3e45730, (void *) f_attach, 13);
    tramp_detach   = install_tramp(base + 0x3e458d0, (void *) f_detach, 14);
    tramp_close    = install_tramp(base + 0x3e455d0, (void *) f_close, 13);
    tramp_peer     = install_tramp(base + 0x3e463a0, (void *) f_peer, 13);
    printf("M58EU install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nTH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("M58EU boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
