/* Low-perturbation Electron 22.3.27 frame-path tracer (M58).
 * Hooks the browser ui::Compositor, the mojom frame-sink submit path and the
 * cc scheduler in every process that loads the Electron Framework.
 * Writes fixed binary records to /Volumes/SystemRoot/tmp/opencode/m58-frame.bin.
 * (Same harness pattern as m57-narrow-present-trace.c.) */
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

#define UI_SCHEDULE    0x64a7690UL  /* ui::Compositor::ScheduleDraw() */
#define UI_BEGINMAIN   0x64a87e0UL  /* ui::Compositor::BeginMainFrame */
#define UI_ACK         0x64a9180UL  /* ui::Compositor::DidReceiveCompositorFrameAck */
#define UI_SINKSET     0x64a72c0UL  /* ui::Compositor::SetLayerTreeFrameSink */
#define PROXY_SETNEEDS 0x1419f30UL  /* viz::mojom::CompositorFrameSinkProxy::SetNeedsBeginFrame(bool) */
#define PROXY_SUBMIT   0x141a0a0UL  /* viz::mojom::CompositorFrameSinkProxy::SubmitCompositorFrame */
#define DSP_ATTEMPT    0x654c640UL  /* viz::DisplayScheduler::AttemptDrawAndSwap */
#define DSP_BEGINSCHED 0x654ce10UL  /* viz::DisplayScheduler::OnBeginFrame */
#define DSP_DRAWSWAP   0x6545f80UL  /* viz::Display::DrawAndSwap */
#define CC_SCHEDPROC   0x51e1c70UL  /* cc::Scheduler::ProcessScheduledActions */
#define CC_REDRAW      0x51e2980UL  /* cc::Scheduler::SetNeedsRedraw */
#define CC_ACK         0x51a3cf0UL  /* cc::LayerTreeHostImpl::DidReceiveCompositorFrameAck */
#define CC_CALCRENDER  0x51a0460UL  /* cc::LayerTreeHostImpl::CalculateRenderPasses */
#define CC_DIDDRAWALL  0x51a67c0UL  /* cc::LayerTreeHostImpl::DidDrawAllLayers */
#define BND_SUBMIT     0x64f5630UL  /* viz::FrameSinkBundleImpl::Submit(vector<BundledFrameSubmission>) */
#define BND_ENQBEGIN   0x64f6130UL  /* viz::FrameSinkBundleImpl::EnqueueOnBeginFrame */
#define BND_FLUSHGRP   0x64f5a60UL  /* viz::FrameSinkBundleImpl::SinkGroup::FlushMessages */
#define CFR_ACK        0x5e23020UL  /* cc::mojo_embedder::AsyncLayerTreeFrameSink::DidReceiveCompositorFrameAck */
#define CFR_BIND       0x5e21c10UL  /* AsyncLayerTreeFrameSink::BindToClient */
#define CFR_SUBMIT     0x5e22420UL  /* AsyncLayerTreeFrameSink::SubmitCompositorFrame */
#define CFR_NEEDS      0x5e23520UL  /* AsyncLayerTreeFrameSink::OnNeedsBeginFrames */
#define CSI_SETNEEDS   0x64fda00UL  /* viz::CompositorFrameSinkImpl::SetNeedsBeginFrame */
#define CSI_DIDNOTPROD 0x64fdd50UL  /* viz::CompositorFrameSinkImpl::DidNotProduceFrame */
#define RCC_SETNEEDS   0x654eab0UL  /* viz::RootCompositorFrameSinkImpl::SetNeedsBeginFrame */
#define RCC_SUBMIT     0x654eaf0UL  /* viz::RootCompositorFrameSinkImpl::SubmitCompositorFrame */
#define DSP_DIDFINISH  0x6549870UL  /* viz::Display::DidFinishFrame */
#define STP_DOBEGIN    0x51e9bf0UL  /* cc::SingleThreadProxy::DoBeginMainFrame */
#define STP_DOCOMMIT   0x51e83a0UL  /* cc::SingleThreadProxy::DoCommit */
#define CC_FINISHIMPL  0x51e4a10UL  /* cc::Scheduler::FinishImplFrame */
#define CC_SETNEEDSREDRAW 0x51e2980UL /* cc::Scheduler::SetNeedsRedraw */
#define FSMB_ADDSINK   0x64f5140UL  /* viz::FrameSinkBundleImpl::AddFrameSink */
#define PI_WILLBEGIN   0x51f09f0UL  /* cc::ProxyImpl::WillBeginImplFrame */
#define PI_DIDNOTPROD  0x51f0a70UL  /* cc::ProxyImpl::DidNotProduceFrame */
#define PI_DEFERMAIN   0x51eed50UL  /* cc::ProxyImpl::SetDeferBeginMainFrameFromMain */
#define PI_READYDRAW   0x51efcf0UL  /* cc::ProxyImpl::NotifyReadyToDraw */
#define CFR_ONBEGIN    0x5e23140UL  /* AsyncLayerTreeFrameSink::OnBeginFrame */
#define CFCPROXY_ONBEGIN 0x141bdc0UL /* viz::mojom::CompositorFrameSinkClientProxy::OnBeginFrame (viz->client sender) */
#define CFCPROXY_ACK   0x141bc60UL  /* ...ClientProxy::DidReceiveCompositorFrameAck */
#define SKIMPL_SWAP    0x64d82f0UL  /* viz::SkiaOutputSurfaceImpl::SwapBuffers */
#define SKOFF_SWAP     0x64e0340UL  /* viz::SkiaOutputDeviceOffscreen::SwapBuffers */
#define SKGL_SWAP      0x64e5340UL  /* viz::SkiaOutputDeviceGL::SwapBuffers */
#define SKBQ_SWAP      0x64e16b0UL  /* viz::SkiaOutputDeviceBufferQueue::SwapBuffers */
#define SKWEB_SWAP     0x64e4840UL  /* viz::SkiaOutputDeviceWebView::SwapBuffers */
#define DSP_SWACK      0x6548e70UL  /* viz::Display::DidReceiveSwapBuffersAck */
#define ITS_SWAPIN     0x4e7a4c0UL  /* gpu::ImageTransportSurfaceOverlayMac::SwapBuffersInternal */
#define ITS_SWAP       0x4e7aca0UL  /* gpu::ImageTransportSurfaceOverlayMac::SwapBuffers */
#define DSRC_TIMER     0x51ded90UL  /* DelayBasedBeginFrameSource::OnTimerTick */
#define DSRC_ISSUE     0x51deb50UL  /* DelayBasedBeginFrameSource::IssueBeginFrameToObserver */
#define BND_GROUPBEGIN 0x64f7840UL  /* FrameSinkBundleImpl::SinkGroup::OnBeginFrame */
#define CFSS_BEGIN     0x64fb270UL  /* CompositorFrameSinkSupport::OnBeginFrame */

enum {
    EV_LOADED = 1, EV_UI_SCHEDULE, EV_UI_BEGINMAIN, EV_UI_ACK, EV_UI_SINKSET,
    EV_PROXY_SETNEEDS, EV_PROXY_SUBMIT, EV_DSP_ATTEMPT, EV_DSP_BEGINSCHED,
    EV_DSP_DRAWSWAP, EV_CC_SCHEDPROC, EV_CC_REDRAW, EV_CC_ACK,
    EV_CC_CALCRENDER, EV_CC_DIDDRAWALL,
    EV_BND_SUBMIT, EV_BND_ENQBEGIN, EV_BND_FLUSHGRP, EV_CFR_ACK,
    EV_CFR_BIND, EV_CFR_SUBMIT, EV_CFR_NEEDS,
    EV_CSI_SETNEEDS, EV_CSI_DIDNOTPROD, EV_RCC_SETNEEDS, EV_RCC_SUBMIT,
    EV_DSP_DIDFINISH, EV_STP_DOBEGIN, EV_STP_DOCOMMIT, EV_CC_FINISHIMPL,
    EV_FSMB_ADDSINK, EV_PI_WILLBEGIN, EV_PI_DIDNOTPROD, EV_PI_DEFERMAIN,
    EV_PI_READYDRAW, EV_CFR_ONBEGIN, EV_CFCPROXY_ONBEGIN, EV_CFCPROXY_ACK,
    EV_SKIMPL_SWAP, EV_SKOFF_SWAP, EV_SKGL_SWAP, EV_DSP_SWACK,
    EV_ITS_SWAPIN, EV_ITS_SWAP, EV_SKBQ_SWAP, EV_SKWEB_SWAP,
    EV_DSRC_TIMER, EV_DSRC_ISSUE, EV_BND_GROUPBEGIN, EV_CFSS_BEGIN,
};

struct record { unsigned pid, event; unsigned long value; };
struct hook { unsigned char *target, saved[12]; unsigned long replacement; };

static struct hook hooks[56];
static volatile int locks[56];

static void emit(unsigned event, unsigned long value) {
    struct record record = { (unsigned)getpid(), event, value };
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-frame.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, &record, sizeof(record)); close(fd); }
}

static void patch(struct hook *hook, int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)hook->target & ~0xfffUL;
    int i;
    mprotect((void *)page, 0x2000, 7);
    if (!enabled) {
        for (i = 0; i < 12; ++i) hook->target[i] = hook->saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (i = 0; i < 8; ++i) jump[2 + i] =
        (hook->replacement >> (8 * i)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (i = 0; i < 12; ++i) hook->target[i] = jump[i];
}

static void log_void(unsigned n, unsigned event, void *self) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)self);
    ((void (*)(void *))hooks[n].target)(self);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}
static void log_bool(unsigned n, unsigned event, void *self, int value) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)value);
    ((void (*)(void *, int))hooks[n].target)(self, value);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}
static void log_arg(unsigned n, unsigned event, void *self, void *a) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)a);
    ((void (*)(void *, void *))hooks[n].target)(self, a);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}
static void log_two_args(unsigned n, unsigned event, void *self, void *a,
                         void *b) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, (unsigned long)a);
    ((void (*)(void *, void *, void *))hooks[n].target)(self, a, b);
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}

static void ui_schedule(void *self) { log_void(0, EV_UI_SCHEDULE, self); }
static void ui_beginmain(void *self, void *args) {
    log_arg(1, EV_UI_BEGINMAIN, self, args);
}
static void ui_ack(void *self) { log_void(2, EV_UI_ACK, self); }
static void ui_sinkset(void *self, void *sink, void *unused) {
    (void)unused;
    log_arg(3, EV_UI_SINKSET, self, sink);
}
static void proxy_setneeds(void *self, int v) {
    log_bool(4, EV_PROXY_SETNEEDS, self, v);
}
static void proxy_submit(void *self, void *a, void *b, void *c, void *d,
                         void *e) {
    while (__sync_lock_test_and_set(&locks[5], 1)) { }
    patch(&hooks[5], 0); emit(EV_PROXY_SUBMIT, (unsigned long)b);
    ((void (*)(void *, void *, void *, void *, void *, void *))
        hooks[5].target)(self, a, b, c, d, e);
    patch(&hooks[5], 1); __sync_lock_release(&locks[5]);
}
static void dsp_attempt(void *self) { log_void(6, EV_DSP_ATTEMPT, self); }
static void dsp_beginsched(void *self, void *args) {
    log_arg(7, EV_DSP_BEGINSCHED, self, args);
}
static void dsp_drawswap(void *self, const void *p) {
    log_arg(8, EV_DSP_DRAWSWAP, self, (void *)p);
}
static void cc_schedproc(void *self) { log_void(9, EV_CC_SCHEDPROC, self); }
static void cc_redraw(void *self, int v) {
    log_bool(10, EV_CC_REDRAW, self, v);
}
static void cc_ack(void *self) { log_void(11, EV_CC_ACK, self); }
static void cc_calcrender(void *self, void *a) {
    log_arg(12, EV_CC_CALCRENDER, self, a);
}
static void cc_diddrawall(void *self, const void *a) {
    log_arg(13, EV_CC_DIDDRAWALL, self, (void *)a);
}
static void bnd_submit(void *self, void *submissions) {
    log_arg(14, EV_BND_SUBMIT, self, submissions);
}
static void bnd_enqbegin(void *self, unsigned sink, void *args, void *details) {
    (void)sink; (void)details;
    log_arg(15, EV_BND_ENQBEGIN, self, args);
}
static void bnd_flushgrp(void *self) { log_void(15 + 1, EV_BND_FLUSHGRP, self); }
static void cfr_ack(void *self, void *resources) {
    log_arg(17, EV_CFR_ACK, self, resources);
}
static void cfr_bind(void *self, void *client) { log_arg(18, EV_CFR_BIND, self, client); }
static void cfr_submit(void *self, void *frame, int has_hit_test) { log_bool(19, EV_CFR_SUBMIT, self, has_hit_test); }
static void cfr_needs(void *self, int v) { log_bool(20, EV_CFR_NEEDS, self, v); }
static void csi_setneeds(void *self, int v) {
    log_bool(21, EV_CSI_SETNEEDS, self, v);
}
static void csi_didnotproduce(void *self, void *ack) {
    log_arg(22, EV_CSI_DIDNOTPROD, self, ack);
}
static void rcc_setneeds(void *self, int v) {
    log_bool(23, EV_RCC_SETNEEDS, self, v);
}
static void rcc_submit(void *self, void *a, void *b, void *c, void *d) {
    while (__sync_lock_test_and_set(&locks[24], 1)) { }
    patch(&hooks[24], 0); emit(EV_RCC_SUBMIT, (unsigned long)self);
    ((void (*)(void *, void *, void *, void *, void *))hooks[24].target)
        (self, a, b, c, d);
    patch(&hooks[24], 1); __sync_lock_release(&locks[24]);
}
static void dsp_didfinish(void *self, void *ack) {
    log_arg(25, EV_DSP_DIDFINISH, self, ack);
}
static void stp_dobegin(void *self, void *args) {
    log_arg(26, EV_STP_DOBEGIN, self, args);
}
static void stp_docommit(void *self, void *args) {
    log_arg(27, EV_STP_DOCOMMIT, self, args);
}
static void cc_finishimpl(void *self) { log_void(28, EV_CC_FINISHIMPL, self); }
static void cc_setneedsredraw(void *self, int v) {
    log_bool(29, EV_CC_REDRAW, self, v);
}
static void fsmb_addsink(void *self, void *support) {
    log_arg(30, EV_FSMB_ADDSINK, self, support);
}
static void pi_willbegin(void *self, void *args) {
    log_arg(31, EV_PI_WILLBEGIN, self, args);
}
static void pi_didnotproduce(void *self, void *ack, int reason) {
    while (__sync_lock_test_and_set(&locks[32], 1)) { }
    patch(&hooks[32], 0); emit(EV_PI_DIDNOTPROD, (unsigned long)reason);
    ((void (*)(void *, void *, int))hooks[32].target)(self, ack, reason);
    patch(&hooks[32], 1); __sync_lock_release(&locks[32]);
}
static void pi_defermain(void *self, int v) {
    log_bool(33, EV_PI_DEFERMAIN, self, v);
}
static void pi_readydraw(void *self) { log_void(34, EV_PI_READYDRAW, self); }
static void cfr_onbegin(void *self, void *args, void *details) {
    log_arg(35, EV_CFR_ONBEGIN, self, args);
}
static void cfcproxy_onbegin(void *self, void *args, void *details) {
    log_arg(36, EV_CFCPROXY_ONBEGIN, self, args);
}
static void cfcproxy_ack(void *self, void *resources) {
    log_arg(37, EV_CFCPROXY_ACK, self, resources);
}
static void skimpl_swap(void *self, void *frame) {
    log_arg(38, EV_SKIMPL_SWAP, self, frame);
}
static void skoff_swap(void *self, void *callback, void *frame) {
    while (__sync_lock_test_and_set(&locks[39], 1)) { }
    patch(&hooks[39], 0); emit(EV_SKOFF_SWAP, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[39].target)(self, callback, frame);
    patch(&hooks[39], 1); __sync_lock_release(&locks[39]);
}
static void skgl_swap(void *self, void *callback, void *frame) {
    while (__sync_lock_test_and_set(&locks[40], 1)) { }
    patch(&hooks[40], 0); emit(EV_SKGL_SWAP, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[40].target)(self, callback, frame);
    patch(&hooks[40], 1); __sync_lock_release(&locks[40]);
}
static void dsp_swack(void *self, void *timings, void *fence) {
    while (__sync_lock_test_and_set(&locks[41], 1)) { }
    patch(&hooks[41], 0); emit(EV_DSP_SWACK, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[41].target)(self, timings, fence);
    patch(&hooks[41], 1); __sync_lock_release(&locks[41]);
}
static void its_swapin(void *self, void *cb1, void *cb2) {
    while (__sync_lock_test_and_set(&locks[42], 1)) { }
    patch(&hooks[42], 0); emit(EV_ITS_SWAPIN, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[42].target)(self, cb1, cb2);
    patch(&hooks[42], 1); __sync_lock_release(&locks[42]);
}
static void its_swap(void *self, void *feedback) {
    log_arg(43, EV_ITS_SWAP, self, feedback);
}

static void skoff3_swap(void *self, void *callback, void *frame) {
    while (__sync_lock_test_and_set(&locks[44], 1)) { }
    patch(&hooks[44], 0); emit(EV_SKOFF_SWAP, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[44].target)(self, callback, frame);
    patch(&hooks[44], 1); __sync_lock_release(&locks[44]);
}
static void skgl3_swap(void *self, void *callback, void *frame) {
    while (__sync_lock_test_and_set(&locks[45], 1)) { }
    patch(&hooks[45], 0); emit(EV_SKGL_SWAP, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[45].target)(self, callback, frame);
    patch(&hooks[45], 1); __sync_lock_release(&locks[45]);
}
static void skbq_swap(void *self, void *callback, void *frame) {
    while (__sync_lock_test_and_set(&locks[46], 1)) { }
    patch(&hooks[46], 0); emit(EV_SKBQ_SWAP, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[46].target)(self, callback, frame);
    patch(&hooks[46], 1); __sync_lock_release(&locks[46]);
}
static void skweb_swap(void *self, void *callback, void *frame) {
    while (__sync_lock_test_and_set(&locks[47], 1)) { }
    patch(&hooks[47], 0); emit(EV_SKWEB_SWAP, (unsigned long)self);
    ((void (*)(void *, void *, void *))hooks[47].target)(self, callback, frame);
    patch(&hooks[47], 1); __sync_lock_release(&locks[47]);
}
static void dsrc_timer(void *self) { log_void(48, EV_DSRC_TIMER, self); }
static void dsrc_issue(void *self, void *observer, void *args) {
    log_two_args(49, EV_DSRC_ISSUE, self, observer, args);
}
static void bnd_groupbegin(void *self, void *args) {
    log_arg(50, EV_BND_GROUPBEGIN, self, args);
}
static void cfss_begin(void *self, void *args) {
    log_arg(51, EV_CFSS_BEGIN, self, args);
}

static void configure(struct hook *h, unsigned char *base, unsigned long offset,
                      void *replacement) {
    int i;
    h->target = base + offset;
    h->replacement = (unsigned long)replacement;
    for (i = 0; i < 12; ++i) h->saved[i] = h->target[i];
    patch(h, 1);
}

__attribute__((constructor)) static void install(void) {
    unsigned i;
    unsigned char *base = 0;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i); break;
        }
    }
    if (!base) return;
    emit(EV_LOADED, (unsigned long)base);
    configure(&hooks[0], base, UI_SCHEDULE, ui_schedule);
    configure(&hooks[1], base, UI_BEGINMAIN, ui_beginmain);
    configure(&hooks[2], base, UI_ACK, ui_ack);
    configure(&hooks[6], base, DSP_ATTEMPT, dsp_attempt);
    configure(&hooks[7], base, DSP_BEGINSCHED, dsp_beginsched);
    configure(&hooks[8], base, DSP_DRAWSWAP, dsp_drawswap);
    configure(&hooks[9], base, CC_SCHEDPROC, cc_schedproc);
    configure(&hooks[11], base, CC_ACK, cc_ack);
    configure(&hooks[12], base, CC_CALCRENDER, cc_calcrender);
    configure(&hooks[13], base, CC_DIDDRAWALL, cc_diddrawall);
    configure(&hooks[14], base, BND_SUBMIT, bnd_submit);
    configure(&hooks[15], base, BND_ENQBEGIN, bnd_enqbegin);
    configure(&hooks[16], base, BND_FLUSHGRP, bnd_flushgrp);
    configure(&hooks[17], base, CFR_ACK, cfr_ack);
    configure(&hooks[18], base, CFR_BIND, cfr_bind);
    configure(&hooks[19], base, CFR_SUBMIT, cfr_submit);
    configure(&hooks[20], base, CFR_NEEDS, cfr_needs);
    configure(&hooks[21], base, CSI_SETNEEDS, csi_setneeds);
    configure(&hooks[22], base, CSI_DIDNOTPROD, csi_didnotproduce);
    configure(&hooks[23], base, RCC_SETNEEDS, rcc_setneeds);
    configure(&hooks[24], base, RCC_SUBMIT, rcc_submit);
    configure(&hooks[25], base, DSP_DIDFINISH, dsp_didfinish);
    configure(&hooks[26], base, STP_DOBEGIN, stp_dobegin);
    configure(&hooks[27], base, STP_DOCOMMIT, stp_docommit);
    configure(&hooks[28], base, CC_FINISHIMPL, cc_finishimpl);
    configure(&hooks[29], base, CC_SETNEEDSREDRAW, cc_setneedsredraw);
    configure(&hooks[30], base, FSMB_ADDSINK, fsmb_addsink);
    configure(&hooks[31], base, PI_WILLBEGIN, pi_willbegin);
    configure(&hooks[32], base, PI_DIDNOTPROD, pi_didnotproduce);
    configure(&hooks[33], base, PI_DEFERMAIN, pi_defermain);
    configure(&hooks[34], base, PI_READYDRAW, pi_readydraw);
    configure(&hooks[35], base, CFR_ONBEGIN, cfr_onbegin);
    configure(&hooks[36], base, CFCPROXY_ONBEGIN, cfcproxy_onbegin);
    configure(&hooks[37], base, CFCPROXY_ACK, cfcproxy_ack);
    configure(&hooks[38], base, SKIMPL_SWAP, skimpl_swap);
    configure(&hooks[39], base, SKOFF_SWAP, skoff_swap);
    configure(&hooks[40], base, SKGL_SWAP, skgl_swap);
    configure(&hooks[41], base, DSP_SWACK, dsp_swack);
    configure(&hooks[42], base, ITS_SWAPIN, its_swapin);
    configure(&hooks[43], base, ITS_SWAP, its_swap);
    configure(&hooks[44], base, SKOFF_SWAP, skoff3_swap);
    configure(&hooks[45], base, SKGL_SWAP, skgl3_swap);
    configure(&hooks[46], base, SKBQ_SWAP, skbq_swap);
    configure(&hooks[47], base, SKWEB_SWAP, skweb_swap);
    configure(&hooks[48], base, DSRC_TIMER, dsrc_timer);
    configure(&hooks[49], base, DSRC_ISSUE, dsrc_issue);
    configure(&hooks[50], base, BND_GROUPBEGIN, bnd_groupbegin);
    configure(&hooks[51], base, CFSS_BEGIN, cfss_begin);
}
