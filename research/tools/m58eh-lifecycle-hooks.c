/* darling-lol M58eh: correlate the two dropped notifications with the browser's
 * IPC-channel endpoint lifecycle.
 *
 * Established (M58dx..M58eg): both notifications are received+
 * validated by the browser's Mojo core, then handed by
 * mojo::MessageDispatcher::Accept to IPC::ChannelAssociatedGroupController::Accept,
 * which (for an unknown interface id) drops them and still returns true.  The
 * LocalFrameHostMessage dispatcher only sees eight OTHER methods.
 *
 * This probe logs, with the mojom ordinal AND the message's interface id
 * (`[header+8]`; the ordinal is `[header+0xc]`):
 *   mojo::internal::InterfaceEndpointClient::HandleValidatedMessage  base+0x3afd670
 *   IPC::...::ChannelAssociatedGroupController::Accept               base+0x3e45d80
 *   IPC::...::ChannelAssociatedGroupController::AttachEndpointClient base+0x3e45730
 *   IPC::...::ChannelAssociatedGroupController::DetachEndpointClient base+0x3e458d0
 * plus the renderer proxies and the LFH stub dispatch.
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
#define LFH_ORD_A 0x5b6c7979u
#define LFH_ORD_B 0x125b9a70u
#define LFH_ORD_C 0x5b22b2a9u
#define LFH_ORD_D 0x3aadd8c1u
#define LFH_ORD_E 0x35e9147bu
#define LFH_ORD_F 0x23969e3du

static int is_ours(unsigned o) { return o == ORD_DCL || o == ORD_FL; }
static int is_known_lfh(unsigned o) {
    return is_ours(o) || o == LFH_ORD_A || o == LFH_ORD_B || o == LFH_ORD_C ||
           o == LFH_ORD_D || o == LFH_ORD_E || o == LFH_ORD_F;
}
static const char *tag(unsigned o) {
    if (o == ORD_FL) return " DidFinishLoad";
    if (o == ORD_DCL) return " DidDispatchDOMContentLoadedEvent";
    return "";
}

/* ---------- trampoline hook ---------- */
struct thook { unsigned char *p; void *fn; unsigned char *tramp; int n; };
static struct thook TH[12]; static int nTH = 0;
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
static void *g_tmsg[8]; static int g_nt = 0;

static inline void *hdr_of(void *msg) { return msg ? *(void **)((char *)msg + 0x18) : 0; }
static inline unsigned ord_of(void *msg) { void *h = hdr_of(msg); return h ? *(unsigned *)((char *)h + 0xc) : 0; }
static inline unsigned ifid_of(void *msg) { void *h = hdr_of(msg); return h ? *(unsigned *)((char *)h + 0x8) : 0; }

/* ---------- inbound Message construction (browser receive) ---------- */
static void (*tramp_create)(void *, void *);
static void f_create(void *out, void *handle) {
    tramp_create(out, handle);
    {
        unsigned ord = ord_of(out);
        if (is_known_lfh(ord)) {
            printf("M58EH n=%u INBOUND pid=%d msg=%p ordinal=0x%08x ifid=%u%s\n", ++ctr, getpid(), out, ord, ifid_of(out), tag(ord));
            fflush(0);
            if (is_ours(ord) && g_nt < 8) g_tmsg[g_nt++] = out;
        }
    }
}

/* ---------- MessageDispatcher::Accept (connector receiver) ---------- */
static int (*tramp_mdisp)(void *, void *);
static int f_mdisp(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    unsigned ifid = ifid_of(msg);
    int r = tramp_mdisp(self, msg);
    if (is_known_lfh(ord)) {
        void *snk = *(void **)((char *)self + 0x18);
        void *svt = snk ? *(void **)snk : 0;
        printf("M58EH n=%u MDISPATCH pid=%d ordinal=0x%08x ifid=%u ret=%d snk_accept=%p%s\n", ++ctr, getpid(), ord, ifid, r & 0xff,
               svt ? *(void **)((char *)svt + 0x18) : 0, tag(ord));
        fflush(0);
    }
    return r;
}

/* ---------- renderer proxies ---------- */
static int (*tramp_send_dcl)(void *);
static int (*tramp_send_fl)(void *, void *);
static int f_send_dcl(void *self) {
    printf("M58EH n=%u SEND_DCL pid=%d\n", ++ctr, getpid()); fflush(0);
    return tramp_send_dcl(self);
}
static int f_send_fl(void *self, void *kurl) {
    printf("M58EH n=%u SEND_FL pid=%d\n", ++ctr, getpid()); fflush(0);
    return tramp_send_fl(self, kurl);
}

/* ---------- LFH stub dispatch (browser) ---------- */
static int (*tramp_lfh)(void *, void *);
static int f_lfh(void *impl, void *msg) {
    unsigned ord = ord_of(msg);
    printf("M58EH n=%u LFH_DISPATCH pid=%d ordinal=0x%08x ifid=%u%s\n", ++ctr, getpid(), ord, ifid_of(msg), tag(ord)); fflush(0);
    return tramp_lfh(impl, msg);
}

/* ---------- endpoint inbound handler (browser) ---------- */
static int (*tramp_hvm)(void *, void *);
static int f_hvm(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    int r = tramp_hvm(self, msg);
    if (is_known_lfh(ord)) {
        printf("M58EH n=%u HANDLE_VALIDATED pid=%d ordinal=0x%08x ifid=%u ret=%d%s\n", ++ctr, getpid(), ord, ifid_of(msg), r & 0xff, tag(ord)); fflush(0);
    }
    return r;
}

/* ---------- IPC channel controller: route / drop ----------
 * The dispatcher's vtable slot calls 0x3e46690 (a full duplicate of Accept used
 * by the MessageReceiver subobject), NOT the 0x3e45d80 copy.  Hook both. */
static int (*tramp_ctrl)(void *, void *);
static int (*tramp_ctrl2)(void *, void *);
static unsigned c_ctrl = 0;
static int f_ctrl(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    unsigned ifid = ifid_of(msg);
    int i, ours = 0, r;
    for (i = 0; i < g_nt; ++i) if (g_tmsg[i] == msg) ours = 1;
    c_ctrl++;
    if (!is_known_lfh(ord) && !ours && c_ctrl > 60) return tramp_ctrl(self, msg);
    r = tramp_ctrl(self, msg);
    printf("M58EH n=%u CAGC_ACCEPT pid=%d msg=%p ordinal=0x%08x ifid=%u ret=%d%s%s\n", ++ctr, getpid(), msg, ord, ifid, r & 0xff, ours ? " PTR": "", tag(ord)); fflush(0);
    return r;
}

/* endpoint close / peer-close (id in esi) */
static void (*tramp_close)(void *, unsigned, void *);
static void (*tramp_peer)(void *, unsigned, void *);
static void f_close(void *self, unsigned id, void *reason) {
    printf("M58EH n=%u CAGC_CLOSE pid=%d ifid=%u%s\n", ++ctr, getpid(), id, id == 3 ? " (LFH)" : ""); fflush(0);
    tramp_close(self, id, reason);
}
static void f_peer(void *self, unsigned id, void *reason) {
    printf("M58EH n=%u CAGC_PEERCLOSED pid=%d ifid=%u%s\n", ++ctr, getpid(), id, id == 3 ? " (LFH)" : ""); fflush(0);
    tramp_peer(self, id, reason);
}
static int f_ctrl2(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    unsigned ifid = ifid_of(msg);
    int r;
    if (!is_known_lfh(ord)) return tramp_ctrl2(self, msg);
    r = tramp_ctrl2(self, msg);
    printf("M58EH n=%u CAGC_ACCEPT_45d80 pid=%d ordinal=0x%08x ifid=%u ret=%d%s\n", ++ctr, getpid(), ord, ifid, r & 0xff, tag(ord)); fflush(0);
    return r;
}

/* ---------- endpoint attach / detach ---------- */
static unsigned (*p_handle_id)(const void *);
static void (*tramp_attach)(void *, void *, void *, void *);
static void (*tramp_detach)(void *, void *);
static void f_attach(void *self, void *handle, void *client, void *runner) {
    unsigned id = p_handle_id(handle);
    printf("M58EH n=%u CAGC_ATTACH pid=%d ifid=%u\n", ++ctr, getpid(), id); fflush(0);
    tramp_attach(self, handle, client, runner);
}
static void f_detach(void *self, void *handle) {
    unsigned id = p_handle_id(handle);
    printf("M58EH n=%u CAGC_DETACH pid=%d ifid=%u\n", ++ctr, getpid(), id); fflush(0);
    tramp_detach(self, handle);
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
    tramp_create   = install_tramp(base + 0x3b178f0, (void *) f_create, 20);
    tramp_mdisp    = install_tramp(base + 0x3b02110, (void *) f_mdisp, 18);
    tramp_send_dcl = install_tramp(base + 0x24c3970, (void *) f_send_dcl, 20);
    tramp_send_fl  = install_tramp(base + 0x24c3020, (void *) f_send_fl, 20);
    tramp_lfh      = install_tramp(base + 0x1331e90, (void *) f_lfh, 20);
    tramp_hvm      = install_tramp(base + 0x3afd670, (void *) f_hvm, 20);
    tramp_ctrl     = install_tramp(base + 0x3e46690, (void *) f_ctrl, 20);
    tramp_close    = install_tramp(base + 0x3e455d0, (void *) f_close, 13);
    tramp_peer     = install_tramp(base + 0x3e463a0, (void *) f_peer, 13);
    tramp_ctrl2    = install_tramp(base + 0x3e45d80, (void *) f_ctrl2, 20);
    tramp_attach   = install_tramp(base + 0x3e45730, (void *) f_attach, 13);
    tramp_detach   = install_tramp(base + 0x3e458d0, (void *) f_detach, 14);
    printf("M58EH install pid=%d base=%p ctrl=%p attach=%p detach=%p\n", getpid(), (void *) base,
           (void *) tramp_ctrl, (void *) tramp_attach, (void *) tramp_detach); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("M58EH boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
