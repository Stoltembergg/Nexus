/* darling-lol M58dy: race-free trampoline probe of the renderer's OUTBOUND
 * Mojo channel write, plus the M58dx LocalFrameHost ordinal hooks.
 *
 *   mojo::Connector::Accept(mojo::Message*)          base+0x3afa280  (OUTBOUND)
 *       -> calls MojoWriteMessage(); return value is the write result.
 *   blink::mojom::LocalFrameHostStubDispatch::Accept base+0x1331e90  (browser dispatch)
 *   proxies: DidDispatchDOMContentLoadedEvent 0x24c3970 / DidFinishLoad 0x24c3020
 *   impls  : RenderFrameHostImpl::DidDispatchDOMContentLoadedEvent 0x2cc6850 /
 *            DidFinishLoad 0x2cc4e00
 *
 * Ordinal is read at *(u32*)(*(void**)(msg+0x18) + 0xc):
 *   0x4ced459c = DidFinishLoad
 *   0x10f795c8 = DidDispatchDOMContentLoadedEvent
 *
 * Unlike M58dw, the hot Connector::Accept hook is a real trampoline: the entry
 * is patched once, the original prologue is relocated to an mmap'd page, and the
 * wrapper tail-calls it.  No per-call mprotect/unhook, so it does not perturb.
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

#define ORD_DID_FINISH_LOAD   0x4ced459cu
#define ORD_DCL               0x10f795c8u

/* ---------- trampoline hook ---------- */
struct thook { unsigned char *p; void *fn; unsigned char *tramp; int n; };
static struct thook TH[16]; static int nTH = 0;

/* nm must land on an instruction boundary in the target prologue and be >= 12 */
static void *install_tramp(void *addr, void *fn, int n) {
    struct thook *t = &TH[nTH++];
    unsigned char *p = (unsigned char *) addr;
    unsigned long pg = (unsigned long) p & ~0xFFFUL;
    unsigned char *tr;
    int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return 0;
    tr = (unsigned char *) mmap(0, 0x1000, 7, 0x1002 /*MAP_PRIVATE|MAP_ANON*/, -1, 0);
    if (!tr || tr == (void *) -1) return 0;
    for (i = 0; i < n; i++) tr[i] = p[i];
    /* jump tramp+n -> p+n */
    tr[n] = 0x48; tr[n+1] = 0xB8;
    { unsigned long a = (unsigned long)(p + n); for (i = 0; i < 8; i++) tr[n+2+i] = (a >> (8*i)) & 0xFF; }
    tr[n+10] = 0xFF; tr[n+11] = 0xE0;
    /* patch entry: mov rax, fn ; jmp rax  (12 bytes) */
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) fn; for (i = 0; i < 8; i++) p[2+i] = (a >> (8*i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
    t->p = p; t->fn = fn; t->tramp = tr; t->n = n;
    return tr;
}

/* ---------- small unhook-style hook (cold functions only) ---------- */
struct hook { unsigned char *p; unsigned char orig[12]; void *fn; };
static struct hook H[8]; static int nH = 0;
static void install(struct hook *h) {
    unsigned char *p = h->p; unsigned long pg = (unsigned long) p & ~0xFFFUL; int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return;
    for (i = 0; i < 12; i++) h->orig[i] = p[i];
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) h->fn; for (i = 0; i < 8; i++) p[2+i] = (a >> (8*i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
}
static void unhook(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) { struct hook *h = &H[nH++]; h->p = (unsigned char *) addr; h->fn = fn; install(h); return h; }

static unsigned (*p_pnum)(const void *);

static int is_lfh8(unsigned o){return o==0x5b6c7979u||o==0x125b9a70u||o==0x5b22b2a9u||o==0x3aadd8c1u||o==0x35e9147bu||o==0x23969e3du;}
static inline unsigned ifid_of(void *msg) {
    void *hdr = msg ? *(void **)((char *)msg + 0x18) : 0;
    return hdr ? *(unsigned *)((char *)hdr + 0x8) : 0;
}
static inline unsigned ord_of(void *msg) {
    void *hdr;
    if (!msg) return 0;
    hdr = *(void **)((char *)msg + 0x18);
    if (!hdr) return 0;
    return *(unsigned *)((char *)hdr + 0xc);
}

/* ---------- outbound channel write ---------- */
static int (*tramp_conn_accept)(void *, void *);
static unsigned long c_cw_dcl = 0, c_cw_fl = 0, c_cw_other = 0;
static int f_conn_accept(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    int target = (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL);
    int ret;
    if (target) {
        unsigned nb = p_pnum ? p_pnum(msg) : 0;
        if (ord == ORD_DCL) c_cw_dcl++; else c_cw_fl++;
        printf("M58DY CONNWRITE pid=%d ordinal=0x%08x payload=%u msg=%p\n", getpid(), ord, nb, msg);
        fflush(0);
    } else {
        c_cw_other++;
    }
    ret = tramp_conn_accept(self, msg);
    if (target) {
        printf("M58DY CONNWRITE_RET pid=%d ordinal=0x%08x ret=%d\n", getpid(), ord, ret);
        fflush(0);
    }
    return ret;
}

/* ---------- inbound message construction (any process, receive only) ----------
 * mojo::Message mojo::Message::CreateFromMessageHandle(ScopedMessageHandle*) is
 * an sret function: rdi = the Message out-slot, rsi = &handle.  Every inbound
 * Mojo message is built here, so the ordinal of what the browser actually
 * receives is readable from the out-slot after the original returns. */
static void (*tramp_create)(void *, void *);
static void *g_conn = 0;                 /* Connector of the in-flight DispatchMessage */
static int (*tramp_dispatch)(void *, void *);
static unsigned long c_in_total = 0, c_in_dcl = 0, c_in_fl = 0;
static int f_dispatch(void *self, void *handle) {
    void *saved = g_conn;
    int r;
    g_conn = self;
    r = tramp_dispatch(self, handle);
    g_conn = saved;
    return r;
}
static void f_create(void *out, void *handle) {
    unsigned ord;
    tramp_create(out, handle);
    ord = ord_of(out);
    c_in_total++;
    if (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL) {
        void *conn = g_conn;
        void *recv = conn ? *(void **)((char *)conn + 0x18) : 0;
        void *vtbl = recv ? *(void **)recv : 0;
        void *slot18 = vtbl ? *(void **)((char *)vtbl + 0x18) : 0;
        if (ord == ORD_DCL) c_in_dcl++; else c_in_fl++;
        printf("M58DY INBOUND pid=%d ordinal=0x%08x ifid=%u payload=%u conn=%p recv=%p vtbl=%p slot18=%p\n",
               getpid(), ord, ifid_of(out), p_pnum ? p_pnum(out) : 0, conn, recv, vtbl, slot18);
        fflush(0);
    }
}

/* mojo::MessageDispatcher::Accept(Message*) - the Connector's receiver.  Slot
 * layout: +8 validator, +0x10 filter (vtable+0x10), +0x18 sink/receiver (+0x18). */
static int (*tramp_mdisp)(void *, void *);
static unsigned long c_md = 0;
/* ---------- header/message byte dump at pass A ---------- */
static void dump_msg(const char *who, void *msg) {
    unsigned long long *q = (unsigned long long *) msg;
    void *h = msg ? *(void **)((char *)msg + 0x18) : 0;
    unsigned long long *hq = (unsigned long long *) h;
    int i;
    printf("M58F1 %s msg=%p b69=%u\n", who, msg, msg ? ((unsigned char *)msg)[0x69] : 0);
    if (msg) { printf("M58F1   msgq:"); for (i = 0; i < 13; i++) printf(" %llx", q[i]); printf("\n"); }
    if (h)   { printf("M58F1   hdr :"); for (i = 0; i < 6; i++) printf(" %llx", hq[i]); printf("\n"); }
    fflush(0);
}

static int f_mdisp(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    {
        static unsigned seenkey[16]; static int ns = 0; int i;
        if (is_lfh8(ord) || ord == ORD_DCL || ord == ORD_DID_FINISH_LOAD) {
            for (i = 0; i < ns && seenkey[i] != ord; ++i) {}
            if (i == ns && ns < 16) {
                void *h = msg ? *(void **)((char *)msg + 0x18) : 0;
                unsigned long long *hq = (unsigned long long *) h;
                seenkey[ns++] = ord;
                printf("M58F1 passA ord=0x%08x h0=%llx h1=%llx h2=%llx h3=%llx h4=%llx h5=%llx\n",
                       ord, h?hq[0]:0, h?hq[1]:0, h?hq[2]:0, h?hq[3]:0, h?hq[4]:0, h?hq[5]:0);
                fflush(0);
            }
        }
    }
    int ret = tramp_mdisp(self, msg);
    c_md++;
    if (c_md <= 25 || ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL || is_lfh8(ord)) {
        void *val = *(void **)((char *)self + 0x8);
        void *flt = *(void **)((char *)self + 0x10);
        void *snk = *(void **)((char *)self + 0x18);
        void *fvt = flt ? *(void **)flt : 0;
        void *svt = snk ? *(void **)snk : 0;
        printf("M58DY MDISPATCH pid=%d n=%lu ordinal=0x%08x ifid=%u ret=%d self=%p val=%p flt=%p snk=%p flt_accept=%p snk_accept=%p\n",
               getpid(), c_md, ord, ifid_of(msg), ret & 0xff, self, val, flt, snk,
               fvt ? *(void **)((char *)fvt + 0x10) : 0,
               svt ? *(void **)((char *)svt + 0x18) : 0);
        fflush(0);
    }
    return ret;
}

/* ---------- endpoint routing chain ---------- */
static int (*tramp_iec_accept)(void *, void *);
static int (*tramp_hvm)(void *, void *);
static int  (*tramp_mr_accept)(void *, void *);
static int f_iec_accept(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    if (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL)
        printf("M58DY IEC_ACCEPT pid=%d ordinal=0x%08x\n", getpid(), ord), fflush(0);
    return tramp_iec_accept(self, msg);
}
static int f_hvm(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    if (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL)
        printf("M58DY HANDLE_VALIDATED pid=%d ordinal=0x%08x\n", getpid(), ord), fflush(0);
    return tramp_hvm(self, msg);
}
static int f_mr_accept(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    int ret;
    if (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL)
        printf("M58DY MR_ACCEPT pid=%d ordinal=0x%08x\n", getpid(), ord), fflush(0);
    ret = tramp_mr_accept(self, msg);
    if (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL)
        printf("M58DY MR_ACCEPT_RET pid=%d ordinal=0x%08x ret=%d\n", getpid(), ord, ret & 0xff), fflush(0);
    return ret;
}

/* ---------- renderer sends ---------- */
static struct hook *HS_dcl, *HS_fl, *HA, *HI_dcl, *HI_fl;
static void f_send_dcl(void *self) {
    printf("M58DY SEND_DCL pid=%d\n", getpid()); fflush(0);
    unhook(HS_dcl); ((void(*)(void*))HS_dcl->p)(self); install(HS_dcl);
}
static void f_send_fl(void *self, void *kurl) {
    printf("M58DY SEND_FL pid=%d\n", getpid()); fflush(0);
    unhook(HS_fl); ((void(*)(void*,void*))HS_fl->p)(self, kurl); install(HS_fl);
}
static void f_impl_dcl(void *self) {
    printf("M58DY IMPL_DCL pid=%d\n", getpid()); fflush(0);
    unhook(HI_dcl); ((void(*)(void*))HI_dcl->p)(self); install(HI_dcl);
}
static void f_impl_fl(void *self, void *gurl) {
    printf("M58DY IMPL_FL pid=%d\n", getpid()); fflush(0);
    unhook(HI_fl); ((void(*)(void*,void*))HI_fl->p)(self, gurl); install(HI_fl);
}
static int (*tramp_lfh_accept)(void *, void *);
static unsigned long c_accept = 0;
static int f_accept(void *impl, void *msg) {
    unsigned ord = ord_of(msg);
    const char *tag = "";
    if (ord == ORD_DID_FINISH_LOAD) tag = " <= DidFinishLoad";
    else if (ord == ORD_DCL) tag = " <= DidDispatchDOMContentLoadedEvent";
    c_accept++;
    printf("M58DY ACCEPT pid=%d n=%lu ordinal=0x%08x%s\n", getpid(), c_accept, ord, tag);
    fflush(0);
    return tramp_lfh_accept(impl, msg);
}

/* MessageHeaderValidator::Accept(Message*) : bool.  DispatchMessage drops the
 * message (jumps to the error path) when this returns false. */
static int (*tramp_validator)(void *, void *);
static unsigned long c_val_dcl = 0, c_val_fl = 0;
static int f_validator(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    int ret = tramp_validator(self, msg);
    if (ord == ORD_DID_FINISH_LOAD || ord == ORD_DCL) {
        if (ord == ORD_DCL) c_val_dcl++; else c_val_fl++;
        printf("M58DY VALIDATOR pid=%d ordinal=0x%08x ret=%d\n", getpid(), ord, ret & 0xff);
        fflush(0);
    }
    return ret;
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
    p_pnum = (unsigned (*)(const void *)) (base + 0x3b17eb0);
    /* hot paths: trampolines (relocate the prologues) */
    tramp_conn_accept = install_tramp(base + 0x3afa280, (void *) f_conn_accept, 17);
    tramp_create      = install_tramp(base + 0x3b178f0, (void *) f_create, 20);
    tramp_dispatch    = install_tramp(base + 0x3af99f0, (void *) f_dispatch, 20);
    tramp_lfh_accept  = install_tramp(base + 0x1331e90, (void *) f_accept, 20);
    tramp_validator   = install_tramp(base + 0x3b19a70, (void *) f_validator, 13);
    tramp_iec_accept  = install_tramp(base + 0x3aff6a0, (void *) f_iec_accept, 16);
    tramp_hvm         = install_tramp(base + 0x3afd670, (void *) f_hvm, 20);
    tramp_mr_accept   = install_tramp(base + 0x3b0aad0, (void *) f_mr_accept, 20);
    tramp_mdisp       = install_tramp(base + 0x3b02110, (void *) f_mdisp, 18);
    /* cold paths */
    HS_dcl = mk(base + 0x24c3970, (void *) f_send_dcl);
    HS_fl  = mk(base + 0x24c3020, (void *) f_send_fl);
    HI_dcl = mk(base + 0x2cc6850, (void *) f_impl_dcl);
    HI_fl  = mk(base + 0x2cc4e00, (void *) f_impl_fl);
    printf("M58DY install pid=%d base=%p conn=%p create=%p lfh=%p val=%p hooked=%d\n", getpid(), (void *) base,
           (void *) tramp_conn_accept, (void *) tramp_create, (void *) tramp_lfh_accept, (void *) tramp_validator, nH);
    fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("M58DY boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
