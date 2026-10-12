/* Minimal Electron 22.3.27 Mojo ChannelMac tracer for Darling/M57.
 * Output is a sequence of fixed-size records; see m57-ipcz-trace.py.
 */
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern char *getenv(const char *);
extern unsigned long pthread_self(void);
extern void *dlopen(const char *path, int mode);
extern void *dlsym(void *handle, const char *symbol);

/* M57bo: Chromium loads EGL with a bare `dlopen("libEGL.dylib")`, which Darling's
 * dyld resolves to /usr/lib/native/libEGL.dylib (its Mesa-backed shim) while GL
 * resolves to the app-bundled ANGLE libGLESv2 - a mismatched pair. Interpose
 * dlopen so the bare EGL name loads the app-bundled ANGLE libEGL instead, without
 * touching the absolute /usr/lib/native reference OpenGL.framework needs. */
#define M57_ANGLE_LIBEGL \
    "/Applications/Electron.app/Contents/Frameworks/Electron Framework.framework/Versions/A/Libraries/libEGL.dylib"
static void *(*m57_real_dlopen)(const char *, int);
static void *m57_dlopen(const char *path, int mode) {
    if (!m57_real_dlopen)
        m57_real_dlopen = (void *(*)(const char *, int))dlsym((void *)-1L, "dlopen");
    void *h = 0;
    if (path && strstr(path, "libEGL.dylib") && !strstr(path, "/native/") &&
        !strstr(path, "Libraries/libEGL")) {
        h = m57_real_dlopen(M57_ANGLE_LIBEGL, mode);
    }
    if (!h) h = m57_real_dlopen(path, mode);
    if (path && (strstr(path, "EGL") || strstr(path, "GLES"))) {
        printf("M57DLOPEN %s -> %p\n", path, h);
        fflush(0);
    }
    return h;
}
static void *(*m57_real_dlsym)(void *, const char *);
static void *m57_dlsym(void *handle, const char *symbol) {
    if (!m57_real_dlsym)
        m57_real_dlsym = (void *(*)(void *, const char *))dlsym((void *)-1L, "dlsym");
    void *r = m57_real_dlsym(handle, symbol);
    if (symbol && (strstr(symbol, "eglMakeCurrent") || strstr(symbol, "eglGetProcAddress") ||
                   strstr(symbol, "eglCreateContext") || strstr(symbol, "eglInitialize"))) {
        void *bogus = m57_real_dlsym(handle, "M57_NONEXISTENT_SYMBOL_ZZZ");
        printf("M57DLSYM %p %s -> %p (bogus_sym -> %p)\n", handle, symbol, r, bogus);
        fflush(0);
    }
    return r;
}
typedef struct { const void *replacement; const void *replacee; } m57_interpose_t;
/* NOTE: interposing dlopen/dlsym perturbs the Riot app's startup (it hangs in
 * Sentry/logger init). The __interpose section is removed entirely; the
 * interposer functions are retained but unused. Re-add the section only for the
 * EGL-fix `dlsym` check. */
__attribute__((used)) static const m57_interpose_t m57_interposers[] = {
    { (const void *)0, (const void *)0 },
};

#define TRANSMIT_VA 0x74f370UL
#define ACCEPT_EVENT_VA 0x3b34740UL
#define ACCEPT_INTERNAL_VA 0x3b337d0UL
#define ON_USER_MESSAGE_VA 0x3b33a60UL
#define GET_PORT_VA 0x3b2cfb0UL
#define ACCEPT_MESSAGE_VA 0x3b2c990UL
#define FORWARD_PROXY_VA 0x3b36120UL
#define PORT_STATUS_CHANGED_VA 0x74e160UL
#define PIPE_OBSERVER_VA 0x748710UL
#define WATCHER_NOTIFY_VA 0x75d4e0UL
#define DISPATCHER_NOTIFY_VA 0x75a3b0UL
#define WATCH_NOTIFY_VA 0x75a170UL
#define WATCH_CALLBACK_VA 0x75a260UL
#define WATCHER_ADD_VA 0x75d590UL
#define WATCHER_REMOVE_VA 0x75e170UL
#define PIPE_DISPATCHER_CTOR_VA 0x7473c0UL
#define GPU_CLIENT_ADD_VA 0x6408ca0UL
#define GPU_RECEIVER_ADD_VA 0x6409d60UL
#define GPU_RECEIVER_CTOR_VA 0x6409ea0UL
#define GPU_STUB_ACCEPT_VA 0x6409fd0UL
#define CORE_ADD_DISPATCHER_VA 0x7301d0UL
#define PIPE_READ_VA 0x747a20UL
#define PIPE_ADD_WATCHER_VA 0x747eb0UL
/* mojo::core::ports::Node::Node(NodeName const&, NodeDelegate*) @rsi.
 * Identifies this process's own Mojo node, so the SOURCE_NODE of an incoming
 * event can be attributed to local self vs a remote peer. */
#define NODE_CTOR_VA 0x3b2cdb0UL
/* mojo::core::NodeController::AddPeer(NodeName const&, ...) @rsi.
 * Logs every peer node this process attaches. */
#define ADD_PEER_VA 0x74d260UL
/* Port transfer / merge path. AcceptPort fires on the *receiving* node when a
 * port descriptor arrives; OnAcceptPeer / OnRequestPortMerge are the control
 * handshakes that move an endpoint between nodes. */
#define ACCEPT_PORT_VA 0x3b36000UL
#define ON_ACCEPT_PEER_VA 0x750140UL
#define ON_REQUEST_PORT_MERGE_VA 0x74f5d0UL
/* Browser-side viz host chain (components/viz/host/gpu_client.cc). GpuClient
 * implements viz::mojom::Gpu; Add() binds the renderer's receiver. */
#define GPU_CLIENT_CTOR_VA 0x6408950UL
#define GPU_CLIENT_ESTABLISH_VA 0x64094e0UL
#define GPU_HOST_ESTABLISH_VA 0x640b280UL
#define GPU_HOST_ON_ESTABLISHED_VA 0x640b730UL
#define BROWSER_DELEGATE_ENSURE_VA 0x2a4ef90UL
/* Browser-side registration of the renderer's viz.mojom.Gpu binder. If these
 * fire but GpuClient::Add does not, the renderer's bind request never reaches
 * the registry; if they do not fire, registration itself is skipped. */
#define RP_ADD_UI_GPU_VA 0x2d063f0UL
#define BINDER_ADD_GPU_VA 0x2d14eb0UL
/* Registry lookup/dispatch for an incoming BindInterface(Gpu), and the
 * renderer-side generated proxy that issues the call. */
#define TRY_BIND_INTERFACE_VA 0x6f97f50UL
#define GPU_PROXY_ESTABLISH_VA 0x1429f50UL
/* base::WritableSharedPersistentMemoryAllocator::IsSharedMemoryAcceptable(
 * WritableSharedMemoryMapping const&) — the check whose failure leads to
 * SetCorrupt()/"Corruption detected in shared-memory segment". Logs the
 * mapping's base pointer (+0x10) and size (+0x18). */
#define IS_SHM_ACCEPTABLE_VA 0x3790670UL
/* base::WritableSharedMemoryRegion::Create(size) and ::Map(mapper).
 * GlobalHistogramAllocator::CreateWithSharedMemoryRegion bails (returns null,
 * writing no header) when Map yields a null base, so log whether Map succeeded
 * and what base/size it produced. */
#define WSR_CREATE_VA 0x3780850UL
#define WSR_MAP_VA 0x37809c0UL
/* base::PersistentMemoryAllocator::Allocate(size, type) — the bump allocator
 * whose "Corruption detected in shared-memory segment" (line 842) fires when a
 * request would exceed the region. Logs the request and the allocator's
 * internal cursors so we can see the real size/limit mismatch. */
#define PERSIST_ALLOCATE_VA 0x378fce0UL
/* base::PersistentMemoryAllocator::PersistentMemoryAllocator(Memory, size,
 * page_size, id, name, ...) - logs every allocator's region base/size so the
 * corrupted one (M57bb-bl) can be identified without hooking the hot Allocate. */
#define PERSIST_CTOR_VA 0x378f9e0UL
/* Chromium-side EGL/ANGLE extension-flag divergence (M57s/M57t). Chromium
 * appends a context attribute for an extension ANGLE never advertised; read
 * Chromium's own requested attributes and its parsed per-display extension
 * flags instead of ANGLE's.
 *   gl::GLContextEGL::Initialize(GLSurface*, GLContextAttribs const&) assembles
 *   the EGL attribute list and is where eglCreateContext is called (M57p);
 *   gl::DisplayExtensionsEGL::InitializeExtensionSettings(void*) fills the
 *   per-display bools by calling gfx::HasExtension 56x, and that call carries
 *   the extension name (StringPiece at %rsi), making it the decodable point. */
#define GL_CTX_INIT_VA 0x46f2760UL
#define EGL_EXT_SETTINGS_VA 0x46ee690UL
#define GFX_HAS_EXTENSION_VA 0x45d6220UL
/* Chromium calls eglCreateContext through its gl::EGLApi vtable
 * (`call *0x40`), not the exported ANGLE symbol (M57t), and the wrapper takes
 * the final EGLint attribute array in the 5th argument (%r8). Hooking both the
 * base and tracing wrapper entries catches whichever the display object uses. */
#define EGL_CREATE_CONTEXT_BASE_VA 0x46eefd0UL   /* gl::EGLApiBase::eglCreateContextFn */
#define EGL_CREATE_CONTEXT_TRACE_VA 0x46efc30UL  /* gl::TraceEGLApi::eglCreateContextFn */
#define EGL_NONE 0x3038U
/* GL capability query (M57bn). SharedContextState::InitializeGL calls
 * glGetIntegerv(GL_MAX_VERTEX_ATTRIBS) through the gl::GLApi vtable (+0x610);
 * which implementation handles it decides whether a context is current. */
#define GLA_GETINTEGERV_BASE_VA 0x46c1a30UL       /* gl::GLApiBase::glGetIntegervFn */
#define GLA_GETINTEGERV_NOCONTEXT_VA 0x46da4a0UL  /* gl::NoContextGLApi::glGetIntegervFn */
#define GLA_GETINTEGERV_STUB_VA 0x4727650UL       /* gl::GLStubApi::glGetIntegervFn */
#define GL_MAX_VERTEX_ATTRIBS 0x8869U
/* Present path (M57u/M57bp): does the browser compositor get a frame sink, and
 * does the GPU actually draw/emit CALayerParams? */
#define DISPLAY_UPDATE_LAYER_TREE_VA 0x4e84830UL   /* ui::DisplayCALayerTree::UpdateCALayerTree */
#define DISPLAY_GOT_LAYER_FRAME_VA 0x4e84ad0UL     /* ui::DisplayCALayerTree::GotCALayerFrame */
#define COMPOSITOR_SET_VISIBLE_VA 0x64a7900UL      /* ui::Compositor::SetVisible */
#define COMPOSITOR_SET_FRAME_SINK_VA 0x64a72c0UL   /* ui::Compositor::SetLayerTreeFrameSink */
#define DISPLAY_DRAW_AND_SWAP_VA 0x6545f80UL       /* viz::Display::DrawAndSwap */
#define DISPLAY_SCHEDULER_ON_BEGIN_FRAME_VA 0x654ce10UL /* viz::DisplayScheduler::OnBeginFrame */
/* Widget visibility chain that should call ui::Compositor::SetVisible. */
#define NATIVE_WIDGET_ON_VISIBILITY_VA 0x724c270UL     /* views::NativeWidgetMacNSWindowHost::OnVisibilityChanged */
#define NATIVE_WIDGET_MAC_SHOW_VA 0x7255ce0UL          /* views::NativeWidgetMac::Show */
#define RWHV_SHOW_WITH_VISIBILITY_VA 0x2ed4360UL       /* content::RenderWidgetHostViewMac::ShowWithVisibility */
/* Browser compositor suspend/unsuspend + GPU display visibility. */
#define RECYCLABLE_SUSPEND_VA 0x64bc330UL              /* ui::RecyclableCompositorMac::Suspend */
#define RECYCLABLE_UNSUSPEND_VA 0x64bc530UL            /* ui::RecyclableCompositorMac::Unsuspend */
#define VIZ_DISPLAY_SET_VISIBLE_VA 0x6545ab0UL         /* viz::Display::SetVisible */
#define VIZ_DISPLAY_SCHEDULER_SET_VISIBLE_VA 0x654c2c0UL /* viz::DisplayScheduler::SetVisible */
#define VIZ_ROOT_SET_DISPLAY_VISIBLE_VA 0x654e3e0UL    /* viz::RootCompositorFrameSinkImpl::SetDisplayVisible */
/* Electron's own window-visibility path. */
#define ELECTRON_WINDOW_OCCLUSION_VA 0x53de00UL        /* -[ElectronNSWindowDelegate windowDidChangeOcclusionState:] */
#define WEBCONTENTS_VIEW_VISIBILITY_VA 0x2ee3d40UL     /* content::WebContentsViewMac::OnWindowVisibilityChanged */
#define NATIVE_WIDGET_SET_VISIBILITY_VA 0x4ec40f0UL    /* remote_cocoa::NativeWidgetNSWindowBridge::SetVisibilityState */
/* Electron window-show entry points. */
#define NATIVEWINDOWMAC_SHOW_VA 0x530ce0UL             /* electron::NativeWindowMac::Show */
#define NATIVEWINDOWMAC_SHOW_INACTIVE_VA 0x530ec0UL    /* electron::NativeWindowMac::ShowInactive */
#define NATIVEWIDGETMAC_NSWINDOW_ORDER_FRONT_VA 0x4ebf100UL /* -[NativeWidgetMacNSWindow orderFrontKeepWindowKeyState] */
#define NATIVEWINDOWMAC_CTOR_VA 0x52f550UL             /* electron::NativeWindowMac::NativeWindowMac */
/* new BrowserWindow path (M57bw): localize the Riot startup hang. */
#define BROWSERWINDOW_CTOR_VA 0x3a6970UL               /* electron::api::BrowserWindow::BrowserWindow */
#define BASEWINDOW_CTOR_VA 0x392ab0UL                  /* electron::api::BaseWindow::BaseWindow */
#define NATIVEWINDOW_CREATE_VA 0x535a60UL              /* electron::NativeWindow::Create */
#define WEBCONTENTS_CTOR_VA 0x40e760UL                 /* electron::api::WebContents::WebContents */
#define WEBCONTENTS_FROM_PREFS_VA 0x4260b0UL           /* electron::api::WebContents::CreateFromWebPreferences */
/* BrowserWindow ctor's post-WebContents gin/v8 setup (M57bw). */
#define GIN_GET_BOOL_VA 0x392f60UL                     /* gin_helper::Dictionary::Get<char[],bool> */
#define GIN_SET_BOOL_VA 0x393060UL                     /* gin_helper::Dictionary::Set<char[],bool> */
#define GIN_GET_STRING_VA 0x3a7150UL                   /* gin_helper::Dictionary::Get<char[],string> */
#define V8_PRIVATE_FORAPI_VA 0x1580970UL               /* v8::Private::ForApi */
#define V8_SET_PRIVATE_VA 0x156bb50UL                  /* v8::Object::SetPrivate */
/* BrowserWindow ctor tail (M57bw). */
#define WEBCONTENTS_SET_OWNER_VA 0x40f880UL            /* electron::api::WebContents::SetOwnerWindow */
#define BASEWINDOW_SET_CONTENTVIEW_VA 0x395d60UL       /* electron::api::BaseWindow::SetContentView */
#define BROWSERWINDOW_OVERRIDE_CONTENTVIEW_VA 0x519f30UL /* electron::api::BrowserWindow::OverrideNSWindowContentView */
#define NATIVEWINDOW_INITFROMOPTIONS_VA 0x47a7c0UL     /* electron::NativeWindow::InitFromOptions */
/* Context binding: if eglMakeCurrent never succeeds, the real glGetIntegerv
 * resolves but the ANGLE context is not current, so queries leave 0. */
#define EGL_MAKE_CURRENT_BASE_VA 0x46ef500UL      /* gl::EGLApiBase::eglMakeCurrentFn */
#define EGL_MAKE_CURRENT_TRACE_VA 0x46f1200UL     /* gl::TraceEGLApi::eglMakeCurrentFn */
/* Real registry dispatch (modern API): the map lookup + per-interface
 * CallbackBinder<Gpu>::BindInterface, which runs the registered callback. */
#define REGISTRY_BIND_VA 0x50d0c0UL
#define CALLBACK_BINDER_GPU_VA 0x2d15080UL
/* ICF-folded CallbackBinder<*>::RunCallback, posted by BindInterface; and the
 * task runner it is posted to. */
#define RUN_CALLBACK_VA 0x2d13280UL
/* base::TaskRunner::PostTask(Location const&, OnceCallback<void()>) -> bool.
 * Armed lazily from CallbackBinder<Gpu>::BindInterface, filtered to its runner. */
#define POST_TASK_VA 0x37e5ff0UL
/* Enqueue + wake-up path for the UI task queue. */
#define POST_DELAYED_TASK_VA 0x37d12f0UL
#define RUNS_IN_SEQ_VA 0x37d21d0UL
#define THREAD_CTRL_SCHEDULE_VA 0x37ddf40UL
#define PUMP_DEFAULT_SCHEDULE_VA 0x3780db0UL
#define PUMP_CF_SCHEDULE_VA 0x381df00UL
#define CAPTURE 128

struct record {
    unsigned int magic;
    unsigned int pid;
    unsigned long sequence;
    unsigned long byte_count;
    unsigned long handle_count;
    unsigned char bytes[CAPTURE];
};

struct hook {
    unsigned char *target;
    unsigned char saved[12];
    unsigned long destination;
};

static struct hook transmit_hook;
static struct hook accept_hook;
static struct hook internal_hook;
static struct hook user_message_hook;
static struct hook get_port_hook;
static struct hook accept_message_hook;
static struct hook forward_proxy_hook;
static struct hook port_status_hook;
static struct hook pipe_observer_hook;
static struct hook watcher_notify_hook;
static struct hook dispatcher_notify_hook;
static struct hook watch_notify_hook;
static struct hook watch_callback_hook;
static struct hook watcher_add_hook;
static struct hook watcher_remove_hook;
static struct hook pipe_ctor_hook;
static struct hook gpu_client_add_hook, gpu_receiver_add_hook;
static struct hook gpu_receiver_ctor_hook, gpu_stub_accept_hook;
static struct hook core_add_hook, pipe_read_hook, pipe_add_watcher_hook;
static struct hook node_ctor_hook, add_peer_hook;
static struct hook accept_port_hook, on_accept_peer_hook, on_request_port_merge_hook;
static struct hook gpu_client_ctor_hook, gpu_client_establish_hook;
static struct hook gpu_host_establish_hook, gpu_host_onestab_hook, browser_delegate_ensure_hook;
static struct hook rp_add_ui_gpu_hook, binder_add_gpu_hook;
static struct hook try_bind_interface_hook, gpu_proxy_establish_hook;
static struct hook registry_bind_hook, callback_binder_gpu_hook;
static struct hook is_shm_acceptable_hook;
static struct hook wsr_create_hook, wsr_map_hook;
static struct hook persist_allocate_hook;
static struct hook persist_ctor_hook;
static struct hook display_update_layer_tree_hook;
static struct hook display_got_layer_frame_hook;
static struct hook compositor_set_visible_hook;
static struct hook compositor_set_frame_sink_hook;
static struct hook display_draw_and_swap_hook;
static struct hook display_scheduler_on_begin_frame_hook;
static struct hook native_widget_on_visibility_hook;
static struct hook native_widget_mac_show_hook;
static struct hook rwhv_show_with_visibility_hook;
static struct hook recyclable_suspend_hook;
static struct hook recyclable_unsuspend_hook;
static struct hook viz_display_set_visible_hook;
static struct hook viz_display_scheduler_set_visible_hook;
static struct hook viz_root_set_display_visible_hook;
static struct hook electron_occlusion_hook;
static struct hook webcontents_visibility_hook;
static struct hook native_widget_set_visibility_hook;
static struct hook nativewindowmac_show_hook;
static struct hook nativewindowmac_show_inactive_hook;
static struct hook nativewidgetmac_nswindow_order_front_hook;
static struct hook nativewindowmac_ctor_hook;
static struct hook browserwindow_ctor_hook;
static struct hook basewindow_ctor_hook;
static struct hook nativewindow_create_hook;
static struct hook webcontents_ctor_hook;
static struct hook webcontents_from_prefs_hook;
static struct hook gin_get_bool_hook, gin_set_bool_hook, gin_get_string_hook;
static struct hook v8_private_forapi_hook, v8_set_private_hook;
static struct hook webcontents_set_owner_hook;
static struct hook basewindow_set_contentview_hook;
static struct hook browserwindow_override_contentview_hook;
static struct hook nativewindow_initfromoptions_hook;
/* M57bv diagnostic: the Riot window is shown on ready-to-show (needs a frame),
 * which never happens because the compositor won't composite a hidden window.
 * Force NativeWindowMac::Show() once the render view is shown. */
static unsigned long g_native_window_mac;
static volatile int g_forced_show;
static struct hook gl_ctx_init_hook;
static struct hook egl_ext_settings_hook;
static struct hook gfx_has_extension_hook;
static struct hook egl_create_context_base_hook;
static struct hook egl_create_context_trace_hook;
static struct hook gla_getintegerv_base_hook;
static struct hook gla_getintegerv_nocontext_hook;
static struct hook gla_getintegerv_stub_hook;
static struct hook egl_make_current_base_hook;
static struct hook egl_make_current_trace_hook;
static struct hook set_current_context_hook;
static struct hook set_ctx_helper_hook;
static struct hook thread_make_current_hook;
static struct hook run_callback_hook;
static struct hook post_task_hook;
static struct hook post_delayed_hook, thread_schedule_hook, pump_default_schedule_hook, pump_cf_schedule_hook;
static volatile unsigned long cb_runner;
static unsigned char *framework_base;
static volatile unsigned long sequence;
/* Set from traced_watcher_notify when the tracked message pipe signals. After
 * that, the persistent watcher_add hook only emits records for this exact set,
 * so a late connector bind to the same pipe is observable without spamming the
 * trace or perturbing bootstrap. Zero until the tracked pipe is identified. */
static volatile unsigned long tracked_watcher_set;
static volatile unsigned long watcher_add_total;
static volatile int patch_lock;
static volatile int accept_patch_lock;
static volatile int internal_patch_lock;
static volatile int user_message_patch_lock;
static volatile int get_port_patch_lock;
static volatile int accept_message_patch_lock;
static volatile int forward_proxy_patch_lock;
static volatile int port_status_patch_lock;
static volatile int pipe_observer_patch_lock;
static volatile int watcher_notify_patch_lock;
static volatile int dispatcher_notify_patch_lock;
static volatile int watch_notify_patch_lock;
static volatile int watch_callback_patch_lock;
static volatile int watcher_add_patch_lock;
static volatile int watcher_remove_patch_lock;
static volatile int pipe_ctor_patch_lock;
static volatile int gpu_client_add_lock, gpu_receiver_add_lock;
static volatile int gpu_receiver_ctor_lock, gpu_stub_accept_lock;
static volatile int core_add_lock, pipe_read_lock, pipe_add_watcher_lock;
static volatile int node_ctor_lock, add_peer_lock;
static volatile int accept_port_lock, on_accept_peer_lock, on_request_port_merge_lock;
static volatile int gpu_client_ctor_lock, gpu_client_establish_lock;
static volatile int gpu_host_establish_lock, gpu_host_onestab_lock, browser_delegate_ensure_lock;
static volatile int rp_add_ui_gpu_lock, binder_add_gpu_lock;
static volatile int try_bind_interface_lock, gpu_proxy_establish_lock;
static volatile int registry_bind_lock, callback_binder_gpu_lock;
static volatile int is_shm_acceptable_lock;
static volatile int wsr_lock;
static volatile int persist_allocate_lock;
static volatile int persist_ctor_lock;
static volatile int present_path_lock;
/* Recursive spinlock (thread-local recursion counter) so hooked functions that
 * call other hooked functions (BrowserWindow -> BaseWindow -> WebContents) do
 * not self-deadlock. */
static __thread int present_path_recursion;
static void present_path_acquire(void) {
    if (present_path_recursion) {
        ++present_path_recursion;
        return;
    }
    while (__sync_lock_test_and_set(&present_path_lock, 1)) { }
    present_path_recursion = 1;
}
static void present_path_release(void) {
    if (--present_path_recursion == 0)
        __sync_lock_release(&present_path_lock);
}
static volatile int gl_ctx_init_lock, egl_ext_settings_lock, gfx_has_extension_lock;
/* Separate locks: if the tracing wrapper ever forwards through the base, a
 * shared lock would deadlock. */
static volatile int egl_cc_base_lock, egl_cc_trace_lock;
static volatile int gla_gi_base_lock, gla_gi_nocontext_lock, gla_gi_stub_lock;
static volatile int egl_mc_base_lock, egl_mc_trace_lock;
static volatile int set_current_context_lock;
static volatile int set_ctx_helper_lock;
static volatile int thread_make_current_lock;
static volatile int set_ctx_installed;
/* Diagnostic (M57s follow-up): when M57_FORCE_NO_ERROR_OFF=1, clear
 * GLContextAttribs.is_no_error (attribs+0x14) before the original runs, so
 * Chromium does not append EGL_CONTEXT_OPENGL_NO_ERROR_KHR. -1 = unread. */
static volatile int force_no_error_off = -1;
static volatile int image_lookup_done;
static volatile int run_callback_lock;
static volatile int post_task_lock;
static volatile int post_delayed_lock, thread_schedule_lock, pump_default_schedule_lock, pump_cf_schedule_lock;

static void status(unsigned long code, unsigned long value) {
    unsigned long r[3];
    int fd;
    r[0] = 0x53555a435049UL; /* "IPCZUS" marker */
    r[1] = code;
    r[2] = value;
    fd = open("/Volumes/SystemRoot/tmp/m57-ipcz-status.bin", 1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, r, sizeof(r)); close(fd); }
}

static unsigned long last_rwx_page;

static void patch(struct hook *hook, int enable) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)hook->target & ~0xfffUL;
    int i;
    /* mprotect is the dominant cost of the unpatch/repatch cycle, and a page
     * stays RWX once raised. Cache the last page so a persistent, high-rate
     * hook does not pay a syscall per invocation (which perturbed startup in
     * the broad lifetime probe). */
    if (last_rwx_page != page) {
        mprotect((void *)page, 0x2000, 7);
        last_rwx_page = page;
    }
    if (!enable) {
        for (i = 0; i < 12; ++i) hook->target[i] = hook->saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (i = 0; i < 8; ++i) jump[2 + i] = (hook->destination >> (8 * i)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (i = 0; i < 12; ++i) hook->target[i] = jump[i];
}

static void traced_transmit(void *, const void *, const unsigned char *);
static unsigned int traced_accept_event(void *, const void *, void *);
static unsigned int traced_accept_internal(void *, const void *, const void *, void *);
static unsigned int traced_user_message(void *, const void *, const void *, void *);
static unsigned int traced_get_port(void *, const void *, void *);
static void traced_accept_message(void *, void *, void *);
static unsigned int traced_forward_proxy(void *, const void *);
static void traced_port_status(void *, const void *);
static void traced_pipe_observer(void *);
static void traced_watcher_notify(void *, const void *);
static void traced_dispatcher_notify(void *, void *, const void *);
static void traced_watch_notify(void *, const void *, int);
static void traced_watch_callback(void *, unsigned int, const void *, unsigned int);
static unsigned int traced_watcher_add(void *, const void *, unsigned long, const void *);
static unsigned int traced_watcher_remove(void *, void *, unsigned long);
static void traced_pipe_ctor(void *, void *, const void *, unsigned long long, int);
static void traced_gpu_client_add(void *, void *);
static unsigned long traced_gpu_receiver_add(void *, void *, void *, int, void *);
static void traced_gpu_receiver_ctor(void *, void *, void *, void *);
static unsigned int traced_gpu_stub_accept(void *, void *, void *);
static unsigned long traced_core_add(void *, void *);
static unsigned int traced_pipe_read(void *, void *);
static unsigned int traced_pipe_add_watcher(void *, const void *, unsigned long);
static void traced_node_ctor(void *, const void *, void *);
static void traced_add_peer(void *, const void *, void *, int, int);
static void traced_accept_port(void *, const void *, const void *);
static void traced_on_accept_peer(void *, const void *, const void *, const void *, const void *);
static void traced_on_request_port_merge(void *, const void *, const void *, const void *);
static void traced_gpu_client_ctor(void *, void *, int, unsigned long long, void *);
static void traced_gpu_client_establish(void *, void *);
static void traced_gpu_host_establish(void *, int, unsigned long long, int, int, void *);
static void traced_gpu_host_onestab(void *, int, int, unsigned long long, void *, void *);
static void *traced_browser_delegate_ensure(void *);
static void traced_rp_add_ui_gpu(void *, void *, void *);
static void traced_binder_add_gpu(void *, void *, void *);
static unsigned int traced_try_bind_interface(void *, void *, void *);
static void traced_gpu_proxy_establish(void *, void *);
static unsigned int traced_registry_bind(void *, void *, void *);
static unsigned int traced_callback_binder_gpu(void *, void *, void *);
static unsigned char traced_is_shm_acceptable(const void *);
static void *traced_wsr_create(void *, unsigned long);
static void traced_wsr_map(void *, const void *, void *);
static unsigned int traced_persist_allocate(void *, unsigned long, unsigned int);
static void traced_persist_ctor(void *, void *, unsigned long, unsigned long, unsigned long, unsigned long);
static void traced_display_update_layer_tree(void *, const void *);
static void traced_display_got_layer_frame(void *, unsigned);
static void traced_compositor_set_visible(void *, int);
static void traced_compositor_set_frame_sink(void *, void *, void *);
static void traced_display_draw_and_swap(void *, const void *);
static void traced_display_scheduler_on_begin_frame(void *, const void *);
static void traced_native_widget_on_visibility(void *, int);
static void traced_native_widget_mac_show(void *, int, const void *);
static void traced_rwhv_show_with_visibility(void *, int);
static unsigned char traced_gl_ctx_init(void *, void *, void *);
static void traced_egl_ext_settings(void *, void *);
static unsigned char traced_gfx_has_extension(void *, const void *, void *);
static void *traced_egl_create_context_base(void *, void *, void *, void *, const void *);
static void *traced_egl_create_context_trace(void *, void *, void *, void *, const void *);
static void traced_gla_getintegerv_base(void *, unsigned, int *);
static void traced_gla_getintegerv_nocontext(void *, unsigned, int *);
static void traced_gla_getintegerv_stub(void *, unsigned, int *);
static unsigned int traced_egl_make_current_base(void *, void *, void *, void *, void *);
static unsigned int traced_egl_make_current_trace(void *, void *, void *, void *, void *);
static void traced_set_current_context(void *);
static void traced_set_ctx_helper(void *);
static unsigned int traced_thread_make_current(void *, void *, void *, void *, void *);
static void traced_run_callback(void *, void *);
static unsigned int traced_post_task(void *, void *, void *);
static unsigned long traced_post_delayed(void *, void *, void *, unsigned long);
static void traced_thread_schedule(void *);
static void traced_pump_default_schedule(void *);
static void traced_pump_cf_schedule(void *);

static void write_marker_value(const char *marker, unsigned long value) {
    struct record r;
    unsigned long i;
    int ended = 0;
    r.magic = 0x5a435049;
    r.pid = (unsigned int)getpid();
    r.sequence = __sync_fetch_and_add(&sequence, 1);
    r.byte_count = ~0UL;
    r.handle_count = value;
    for (i = 0; i < CAPTURE; ++i) {
        if (!marker || ended || !marker[i]) {
            ended = 1;
            r.bytes[i] = 0;
        } else {
            r.bytes[i] = marker[i];
        }
    }
    {
        int fd = open("/Volumes/SystemRoot/tmp/m57-ipcz.bin", 1 | 0x200 | 8, 0644);
        if (fd >= 0) { write(fd, &r, sizeof(r)); close(fd); }
    }
}

static void write_marker(const char *marker) { write_marker_value(marker, 0); }

static unsigned int traced_accept_event(void *self, const void *node_name,
                                        void *event_slot) {
    unsigned int result;
    while (__sync_lock_test_and_set(&accept_patch_lock, 1)) { }
    patch(&accept_hook, 0);
    write_marker("ACCEPT_EVENT");
    result = ((unsigned int (*)(void *, const void *, void *))accept_hook.target)(
        self, node_name, event_slot);
    patch(&accept_hook, 1);
    __sync_lock_release(&accept_patch_lock);
    return result;
}

static unsigned int traced_accept_internal(void *self, const void *port_ref,
                                           const void *node_name, void *event_slot) {
    unsigned int result;
    while (__sync_lock_test_and_set(&internal_patch_lock, 1)) { }
    patch(&internal_hook, 0);
    write_marker("ACCEPT_INTERNAL");
    result = ((unsigned int (*)(void *, const void *, const void *, void *))internal_hook.target)(
        self, port_ref, node_name, event_slot);
    patch(&internal_hook, 1);
    __sync_lock_release(&internal_patch_lock);
    return result;
}

static unsigned int traced_user_message(void *self, const void *port_ref,
                                        const void *node_name, void *event_slot) {
    unsigned int result;
    while (__sync_lock_test_and_set(&user_message_patch_lock, 1)) { }
    patch(&user_message_hook, 0);
    write_marker("ON_USER_MESSAGE");
    result = ((unsigned int (*)(void *, const void *, const void *, void *))user_message_hook.target)(
        self, port_ref, node_name, event_slot);
    patch(&user_message_hook, 1);
    __sync_lock_release(&user_message_patch_lock);
    return result;
}

static unsigned int traced_get_port(void *self, const void *port_name,
                                    void *port_ref) {
    unsigned int result;
    while (__sync_lock_test_and_set(&get_port_patch_lock, 1)) { }
    patch(&get_port_hook, 0);
    write_marker("GET_PORT");
    if (port_name) {
        write_marker_value("PORT_NAME_0", ((const unsigned long *)port_name)[0]);
        write_marker_value("PORT_NAME_1", ((const unsigned long *)port_name)[1]);
    }
    result = ((unsigned int (*)(void *, const void *, void *))get_port_hook.target)(
        self, port_name, port_ref);
    write_marker_value("GET_PORT_RESULT", result);
    patch(&get_port_hook, 1);
    __sync_lock_release(&get_port_patch_lock);
    return result;
}

static void traced_accept_message(void *self, void *event_slot, void *was_empty) {
    while (__sync_lock_test_and_set(&accept_message_patch_lock, 1)) { }
    patch(&accept_message_hook, 0);
    write_marker("QUEUE_ACCEPT");
    ((void (*)(void *, void *, void *))accept_message_hook.target)(
        self, event_slot, was_empty);
    patch(&accept_message_hook, 1);
    __sync_lock_release(&accept_message_patch_lock);
}

static unsigned int traced_forward_proxy(void *self, const void *port_ref) {
    unsigned int result;
    while (__sync_lock_test_and_set(&forward_proxy_patch_lock, 1)) { }
    patch(&forward_proxy_hook, 0);
    write_marker("FORWARD_PROXY");
    result = ((unsigned int (*)(void *, const void *))forward_proxy_hook.target)(self, port_ref);
    write_marker_value("FORWARD_RESULT", result);
    patch(&forward_proxy_hook, 1);
    __sync_lock_release(&forward_proxy_patch_lock);
    return result;
}

static void traced_port_status(void *self, const void *port_ref) {
    while (__sync_lock_test_and_set(&port_status_patch_lock, 1)) { }
    patch(&port_status_hook, 0);
    write_marker("PORT_STATUS");
    ((void (*)(void *, const void *))port_status_hook.target)(self, port_ref);
    patch(&port_status_hook, 1);
    __sync_lock_release(&port_status_patch_lock);
}

static void traced_pipe_observer(void *self) {
    while (__sync_lock_test_and_set(&pipe_observer_patch_lock, 1)) { }
    patch(&pipe_observer_hook, 0);
    write_marker("PIPE_OBSERVER");
    ((void (*)(void *))pipe_observer_hook.target)(self);
    patch(&pipe_observer_hook, 1);
    __sync_lock_release(&pipe_observer_patch_lock);
}

static void traced_watcher_notify(void *self, const void *signals_state) {
    unsigned long begin;
    unsigned long end;
    unsigned long old_state;
    unsigned long new_state;
    while (__sync_lock_test_and_set(&watcher_notify_patch_lock, 1)) { }
    patch(&watcher_notify_hook, 0);
    write_marker("WATCHER_NOTIFY");
    tracked_watcher_set = (unsigned long)self;
    write_marker_value("WATCHER_SET", (unsigned long)self);
    write_marker_value("PIPE_DISPATCHER", (unsigned long)self - 0x90);
    write_marker_value("PIPE_ID", *(unsigned long *)((unsigned char *)self - 0x60));
    write_marker_value("PIPE_MODE", *(unsigned int *)((unsigned char *)self - 0x58));
    begin = *(unsigned long *)((unsigned char *)self + 0x08);
    end = *(unsigned long *)((unsigned char *)self + 0x10);
    old_state = *(unsigned long *)((unsigned char *)self + 0x24);
    new_state = signals_state ? *(const unsigned long *)signals_state : 0;
    write_marker_value("WATCHER_COUNT", end >= begin ? (end - begin) / 0x28 : ~0UL);
    /* Liveness proof for the persistent watcher_add hook: total Adds seen for
     * every pipe up to this point. If this is non-zero the hook is firing, so
     * the absence of WATCHER_ADD_TARGET afterwards is a real negative. */
    write_marker_value("WATCHER_ADD_TOTAL", watcher_add_total);
    write_marker_value("WATCHER_OLD", old_state);
    write_marker_value("WATCHER_NEW", new_state);
    ((void (*)(void *, const void *))watcher_notify_hook.target)(self, signals_state);
    patch(&watcher_notify_hook, 1);
    __sync_lock_release(&watcher_notify_patch_lock);
}

static void traced_dispatcher_notify(void *self, void *dispatcher,
                                     const void *signals_state) {
    while (__sync_lock_test_and_set(&dispatcher_notify_patch_lock, 1)) { }
    patch(&dispatcher_notify_hook, 0);
    write_marker("DISPATCHER_NOTIFY");
    ((void (*)(void *, void *, const void *))dispatcher_notify_hook.target)(
        self, dispatcher, signals_state);
    patch(&dispatcher_notify_hook, 1);
    __sync_lock_release(&dispatcher_notify_patch_lock);
}

static void traced_watch_notify(void *self, const void *signals_state, int force) {
    while (__sync_lock_test_and_set(&watch_notify_patch_lock, 1)) { }
    patch(&watch_notify_hook, 0);
    write_marker_value("WATCH_NOTIFY", (unsigned int)force);
    ((void (*)(void *, const void *, int))watch_notify_hook.target)(self, signals_state, force);
    patch(&watch_notify_hook, 1);
    __sync_lock_release(&watch_notify_patch_lock);
}

static void traced_watch_callback(void *self, unsigned int result,
                                  const void *signals_state, unsigned int flags) {
    while (__sync_lock_test_and_set(&watch_callback_patch_lock, 1)) { }
    patch(&watch_callback_hook, 0);
    write_marker_value("WATCH_CALLBACK", result);
    ((void (*)(void *, unsigned int, const void *, unsigned int))watch_callback_hook.target)(
        self, result, signals_state, flags);
    patch(&watch_callback_hook, 1);
    __sync_lock_release(&watch_callback_patch_lock);
}

static unsigned int traced_watcher_add(void *self, const void *watcher,
                                       unsigned long context, const void *state) {
    unsigned int result;
    while (__sync_lock_test_and_set(&watcher_add_patch_lock, 1)) { }
    patch(&watcher_add_hook, 0);
    ++watcher_add_total;
    if (tracked_watcher_set && (unsigned long)self == tracked_watcher_set) {
        write_marker_value("WATCHER_ADD_TARGET", (unsigned long)self);
        write_marker_value("WATCHER_ADD_WATCHER", (unsigned long)watcher);
        write_marker_value("WATCHER_ADD_TOTAL", watcher_add_total);
    }
    result = ((unsigned int (*)(void *, const void *, unsigned long, const void *))watcher_add_hook.target)(
        self, watcher, context, state);
    patch(&watcher_add_hook, 1);
    __sync_lock_release(&watcher_add_patch_lock);
    return result;
}

static unsigned int traced_watcher_remove(void *self, void *watcher,
                                          unsigned long context) {
    unsigned int result;
    while (__sync_lock_test_and_set(&watcher_remove_patch_lock, 1)) { }
    patch(&watcher_remove_hook, 0);
    write_marker_value("WATCHER_REMOVE", (unsigned long)self);
    result = ((unsigned int (*)(void *, void *, unsigned long))watcher_remove_hook.target)(
        self, watcher, context);
    write_marker_value("WATCHER_REMOVE_RESULT", result);
    patch(&watcher_remove_hook, 1);
    __sync_lock_release(&watcher_remove_patch_lock);
    return result;
}

static void traced_pipe_ctor(void *self, void *controller, const void *port_ref,
                             unsigned long long pipe_id, int mode) {
    unsigned long caller = (unsigned long)__builtin_return_address(0);
    while (__sync_lock_test_and_set(&pipe_ctor_patch_lock, 1)) { }
    patch(&pipe_ctor_hook, 0);
    write_marker_value("PIPE_CTOR", (unsigned long)self);
    write_marker_value("PIPE_CTOR_CALLER", caller - (unsigned long)framework_base);
    ((void (*)(void *, void *, const void *, unsigned long long, int))pipe_ctor_hook.target)(
        self, controller, port_ref, pipe_id, mode);
    patch(&pipe_ctor_hook, 1);
    __sync_lock_release(&pipe_ctor_patch_lock);
}

static void traced_gpu_client_add(void *self, void *receiver) {
    while (__sync_lock_test_and_set(&gpu_client_add_lock, 1)) { }
    patch(&gpu_client_add_hook, 0); write_marker("GPU_CLIENT_ADD");
    ((void (*)(void *, void *))gpu_client_add_hook.target)(self, receiver);
    patch(&gpu_client_add_hook, 1); __sync_lock_release(&gpu_client_add_lock);
}

static unsigned long traced_gpu_receiver_add(void *self, void *impl, void *receiver,
                                             int has_context, void *runner) {
    unsigned long result;
    while (__sync_lock_test_and_set(&gpu_receiver_add_lock, 1)) { }
    patch(&gpu_receiver_add_hook, 0); write_marker("GPU_RECEIVER_ADD");
    result = ((unsigned long (*)(void *, void *, void *, int, void *))gpu_receiver_add_hook.target)(
        self, impl, receiver, has_context, runner);
    patch(&gpu_receiver_add_hook, 1); __sync_lock_release(&gpu_receiver_add_lock);
    return result;
}

static void traced_gpu_receiver_ctor(void *self, void *impl, void *receiver, void *runner) {
    while (__sync_lock_test_and_set(&gpu_receiver_ctor_lock, 1)) { }
    patch(&gpu_receiver_ctor_hook, 0); write_marker("GPU_RECEIVER_CTOR");
    ((void (*)(void *, void *, void *, void *))gpu_receiver_ctor_hook.target)(self, impl, receiver, runner);
    patch(&gpu_receiver_ctor_hook, 1); __sync_lock_release(&gpu_receiver_ctor_lock);
}

static unsigned int traced_gpu_stub_accept(void *self, void *message, void *responder) {
    unsigned int result;
    while (__sync_lock_test_and_set(&gpu_stub_accept_lock, 1)) { }
    patch(&gpu_stub_accept_hook, 0); write_marker("GPU_STUB_ACCEPT");
    result = ((unsigned int (*)(void *, void *, void *))gpu_stub_accept_hook.target)(self, message, responder);
    patch(&gpu_stub_accept_hook, 1); __sync_lock_release(&gpu_stub_accept_lock);
    return result;
}

static unsigned long traced_core_add(void *self, void *dispatcher) {
    unsigned long result;
    while (__sync_lock_test_and_set(&core_add_lock, 1)) { }
    patch(&core_add_hook, 0); write_marker_value("CORE_ADD_OBJECT", (unsigned long)dispatcher);
    result = ((unsigned long (*)(void *, void *))core_add_hook.target)(self, dispatcher);
    write_marker_value("CORE_ADD_HANDLE", result);
    patch(&core_add_hook, 1); __sync_lock_release(&core_add_lock); return result;
}

static unsigned int traced_pipe_read(void *self, void *message) {
    unsigned int result;
    while (__sync_lock_test_and_set(&pipe_read_lock, 1)) { }
    patch(&pipe_read_hook, 0); write_marker_value("PIPE_READ", (unsigned long)self);
    result = ((unsigned int (*)(void *, void *))pipe_read_hook.target)(self, message);
    write_marker_value("PIPE_READ_RESULT", result);
    patch(&pipe_read_hook, 1); __sync_lock_release(&pipe_read_lock); return result;
}

static unsigned int traced_pipe_add_watcher(void *self, const void *watcher,
                                            unsigned long context) {
    unsigned int result;
    while (__sync_lock_test_and_set(&pipe_add_watcher_lock, 1)) { }
    patch(&pipe_add_watcher_hook, 0); write_marker_value("PIPE_ADD_WATCH", (unsigned long)self);
    result = ((unsigned int (*)(void *, const void *, unsigned long))pipe_add_watcher_hook.target)(
        self, watcher, context);
    patch(&pipe_add_watcher_hook, 1); __sync_lock_release(&pipe_add_watcher_lock); return result;
}

/* The local Mojo node name for this process. Every incoming event carries the
 * source node name, so this is what lets us say whether the tracked
 * EstablishGpuChannel message came from our own node or from a peer (GPU). */
static void traced_node_ctor(void *self, const void *local_name, void *delegate) {
    while (__sync_lock_test_and_set(&node_ctor_lock, 1)) { }
    patch(&node_ctor_hook, 0);
    if (local_name) {
        write_marker_value("LOCAL_NODE_0", ((const unsigned long *)local_name)[0]);
        write_marker_value("LOCAL_NODE_1", ((const unsigned long *)local_name)[1]);
    }
    ((void (*)(void *, const void *, void *))node_ctor_hook.target)(self, local_name, delegate);
    patch(&node_ctor_hook, 1);
    __sync_lock_release(&node_ctor_lock);
}

static void traced_add_peer(void *self, const void *node_name, void *channel,
                            int start_sending, int start_receiving) {
    while (__sync_lock_test_and_set(&add_peer_lock, 1)) { }
    patch(&add_peer_hook, 0);
    if (node_name) {
        write_marker_value("ADD_PEER_0", ((const unsigned long *)node_name)[0]);
        write_marker_value("ADD_PEER_1", ((const unsigned long *)node_name)[1]);
    }
    ((void (*)(void *, const void *, void *, int, int))add_peer_hook.target)(
        self, node_name, channel, start_sending, start_receiving);
    patch(&add_peer_hook, 1);
    __sync_lock_release(&add_peer_lock);
}

/* Fires on the node that *receives* a moved endpoint. If the tracked pipe's
 * destination port is ever accepted anywhere, it was transferred; if its name
 * never appears here, it stayed local. */
static void traced_accept_port(void *self, const void *port_name, const void *descriptor) {
    while (__sync_lock_test_and_set(&accept_port_lock, 1)) { }
    patch(&accept_port_hook, 0);
    if (port_name) write_marker_value("ACCEPT_PORT_0", ((const unsigned long *)port_name)[0]);
    if (port_name) write_marker_value("ACCEPT_PORT_1", ((const unsigned long *)port_name)[1]);
    ((void (*)(void *, const void *, const void *))accept_port_hook.target)(
        self, port_name, descriptor);
    patch(&accept_port_hook, 1);
    __sync_lock_release(&accept_port_lock);
}

static void traced_on_accept_peer(void *self, const void *n1, const void *n2,
                                  const void *n3, const void *port_name) {
    while (__sync_lock_test_and_set(&on_accept_peer_lock, 1)) { }
    patch(&on_accept_peer_hook, 0);
    if (port_name) {
        write_marker_value("ACCEPT_PEER_PORT_0", ((const unsigned long *)port_name)[0]);
        write_marker_value("ACCEPT_PEER_PORT_1", ((const unsigned long *)port_name)[1]);
    }
    if (n1) {
        write_marker_value("ACCEPT_PEER_NODE1_0", ((const unsigned long *)n1)[0]);
        write_marker_value("ACCEPT_PEER_NODE1_1", ((const unsigned long *)n1)[1]);
    }
    ((void (*)(void *, const void *, const void *, const void *, const void *))on_accept_peer_hook.target)(
        self, n1, n2, n3, port_name);
    patch(&on_accept_peer_hook, 1);
    __sync_lock_release(&on_accept_peer_lock);
}

static void traced_on_request_port_merge(void *self, const void *from_node,
                                         const void *port_name, const void *connector) {
    while (__sync_lock_test_and_set(&on_request_port_merge_lock, 1)) { }
    patch(&on_request_port_merge_hook, 0);
    if (from_node) {
        write_marker_value("REQ_MERGE_FROM_0", ((const unsigned long *)from_node)[0]);
        write_marker_value("REQ_MERGE_FROM_1", ((const unsigned long *)from_node)[1]);
    }
    if (port_name) {
        write_marker_value("REQ_MERGE_PORT_0", ((const unsigned long *)port_name)[0]);
        write_marker_value("REQ_MERGE_PORT_1", ((const unsigned long *)port_name)[1]);
    }
    ((void (*)(void *, const void *, const void *, const void *))on_request_port_merge_hook.target)(
        self, from_node, port_name, connector);
    patch(&on_request_port_merge_hook, 1);
    __sync_lock_release(&on_request_port_merge_lock);
}

static void traced_gpu_client_ctor(void *self, void *delegate, int client_id,
                                   unsigned long long a, void *runner) {
    unsigned long caller = (unsigned long)__builtin_return_address(0);
    while (__sync_lock_test_and_set(&gpu_client_ctor_lock, 1)) { }
    patch(&gpu_client_ctor_hook, 0);
    write_marker("GPU_CLIENT_CTOR");
    write_marker_value("GPU_CLIENT_CTOR_ID", (unsigned long)(unsigned int)client_id);
    write_marker_value("GPU_CLIENT_CTOR_CALLER",
                       caller - (unsigned long)framework_base);
    ((void (*)(void *, void *, int, unsigned long long, void *))gpu_client_ctor_hook.target)(
        self, delegate, client_id, a, runner);
    patch(&gpu_client_ctor_hook, 1);
    __sync_lock_release(&gpu_client_ctor_lock);
}

static void traced_gpu_client_establish(void *self, void *callback) {
    while (__sync_lock_test_and_set(&gpu_client_establish_lock, 1)) { }
    patch(&gpu_client_establish_hook, 0);
    write_marker("GPU_CLIENT_ESTABLISH");
    ((void (*)(void *, void *))gpu_client_establish_hook.target)(self, callback);
    patch(&gpu_client_establish_hook, 1);
    __sync_lock_release(&gpu_client_establish_lock);
}

static void traced_gpu_host_establish(void *self, int client_id, unsigned long long a,
                                      int b, int c, void *callback) {
    while (__sync_lock_test_and_set(&gpu_host_establish_lock, 1)) { }
    patch(&gpu_host_establish_hook, 0);
    write_marker("GPU_HOST_ESTABLISH");
    write_marker_value("GPU_HOST_ESTABLISH_ID", (unsigned long)(unsigned int)client_id);
    ((void (*)(void *, int, unsigned long long, int, int, void *))gpu_host_establish_hook.target)(
        self, client_id, a, b, c, callback);
    patch(&gpu_host_establish_hook, 1);
    __sync_lock_release(&gpu_host_establish_lock);
}

static void traced_gpu_host_onestab(void *self, int client_id, int ok,
                                    unsigned long long handle, void *info, void *finfo) {
    while (__sync_lock_test_and_set(&gpu_host_onestab_lock, 1)) { }
    patch(&gpu_host_onestab_hook, 0);
    write_marker("GPU_HOST_ON_ESTABLISHED");
    write_marker_value("GPU_HOST_ON_ESTABLISHED_ID", (unsigned long)(unsigned int)client_id);
    ((void (*)(void *, int, int, unsigned long long, void *, void *))gpu_host_onestab_hook.target)(
        self, client_id, ok, handle, info, finfo);
    patch(&gpu_host_onestab_hook, 1);
    __sync_lock_release(&gpu_host_onestab_lock);
}

static void *traced_browser_delegate_ensure(void *self) {
    void *result;
    while (__sync_lock_test_and_set(&browser_delegate_ensure_lock, 1)) { }
    patch(&browser_delegate_ensure_hook, 0);
    write_marker("BROWSER_DELEGATE_ENSURE");
    result = ((void *(*)(void *))browser_delegate_ensure_hook.target)(self);
    patch(&browser_delegate_ensure_hook, 1);
    __sync_lock_release(&browser_delegate_ensure_lock);
    return result;
}

static void traced_rp_add_ui_gpu(void *self, void *callback, void *runner) {
    while (__sync_lock_test_and_set(&rp_add_ui_gpu_lock, 1)) { }
    patch(&rp_add_ui_gpu_hook, 0);
    write_marker("RP_ADD_UI_GPU");
    if (callback) {
        /* base::CallbackBase: [0]=polymorphic invoke fn, [1]=bind_state */
        write_marker_value("RP_ADD_UI_GPU_INVOKE",
                           ((const unsigned long *)callback)[0] - (unsigned long)framework_base);
        write_marker_value("RP_ADD_UI_GPU_STATE", ((const unsigned long *)callback)[1]);
    }
    ((void (*)(void *, void *, void *))rp_add_ui_gpu_hook.target)(self, callback, runner);
    patch(&rp_add_ui_gpu_hook, 1);
    __sync_lock_release(&rp_add_ui_gpu_lock);
}

static void traced_binder_add_gpu(void *self, void *callback, void *runner) {
    while (__sync_lock_test_and_set(&binder_add_gpu_lock, 1)) { }
    patch(&binder_add_gpu_hook, 0);
    write_marker("BINDER_ADD_GPU");
    ((void (*)(void *, void *, void *))binder_add_gpu_hook.target)(self, callback, runner);
    patch(&binder_add_gpu_hook, 1);
    __sync_lock_release(&binder_add_gpu_lock);
}

static unsigned int traced_try_bind_interface(void *self, void *name, void *handle) {
    unsigned int result;
    while (__sync_lock_test_and_set(&try_bind_interface_lock, 1)) { }
    patch(&try_bind_interface_hook, 0);
    write_marker("TRY_BIND");
    result = ((unsigned int (*)(void *, void *, void *))try_bind_interface_hook.target)(
        self, name, handle);
    patch(&try_bind_interface_hook, 1);
    __sync_lock_release(&try_bind_interface_lock);
    return result;
}

static void traced_gpu_proxy_establish(void *self, void *callback) {
    while (__sync_lock_test_and_set(&gpu_proxy_establish_lock, 1)) { }
    patch(&gpu_proxy_establish_hook, 0);
    write_marker("GPU_PROXY_ESTABLISH");
    ((void (*)(void *, void *))gpu_proxy_establish_hook.target)(self, callback);
    patch(&gpu_proxy_establish_hook, 1);
    __sync_lock_release(&gpu_proxy_establish_lock);
}

static unsigned int traced_registry_bind(void *self, void *name, void *handle) {
    unsigned int result;
    while (__sync_lock_test_and_set(&registry_bind_lock, 1)) { }
    patch(&registry_bind_hook, 0);
    write_marker("REGISTRY_BIND");
    if (name) {
        const unsigned long *w = (const unsigned long *)name;
        write_marker_value("RB_W0", w[0]);
        write_marker_value("RB_W1", w[1]);
        write_marker_value("RB_W2", w[2]);
    }
    result = ((unsigned int (*)(void *, void *, void *))registry_bind_hook.target)(
        self, name, handle);
    patch(&registry_bind_hook, 1);
    __sync_lock_release(&registry_bind_lock);
    return result;
}

static unsigned int traced_callback_binder_gpu(void *self, void *name, void *handle) {
    unsigned int result;
    while (__sync_lock_test_and_set(&callback_binder_gpu_lock, 1)) { }
    patch(&callback_binder_gpu_hook, 0);
    write_marker("CALLBACK_BIND_GPU");
    if (self) {
        cb_runner = ((const unsigned long *)self)[2];
        patch(&post_task_hook, 1);   /* filtered; arm now so the nested PostTask is seen */
        patch(&post_delayed_hook, 1);
    }
    if (self) write_marker_value("CB_RUNNER", ((const unsigned long *)self)[2]);
    if (cb_runner) write_marker_value("CB_RUNNER_VT",
        *(const unsigned long *)cb_runner - (unsigned long)framework_base);
    if (name) {
        const unsigned long *w = (const unsigned long *)name;
        write_marker_value("CB_W0", w[0]);
        write_marker_value("CB_W1", w[1]);
        write_marker_value("CB_W2", w[2]);
    }
    result = ((unsigned int (*)(void *, void *, void *))callback_binder_gpu_hook.target)(
        self, name, handle);
    patch(&callback_binder_gpu_hook, 1);
    __sync_lock_release(&callback_binder_gpu_lock);
    return result;
}

/* Mirrors IsSharedMemoryAcceptable's own tests so the log distinguishes an
 * alignment failure from a size-range failure. */
static unsigned char traced_is_shm_acceptable(const void *mapping) {
    unsigned char result;
    while (__sync_lock_test_and_set(&is_shm_acceptable_lock, 1)) { }
    patch(&is_shm_acceptable_hook, 0);
    {
        const unsigned long *w = (const unsigned long *)mapping;
        unsigned long base = w[2];   /* +0x10 */
        unsigned long size = w[3];   /* +0x18 */
        write_marker("SHM_ACCEPTABLE");
        write_marker_value("SHM_BASE", base);
        write_marker_value("SHM_SIZE", size);
        write_marker_value("SHM_BASE_ALIGNED", (base & 7) == 0);
        write_marker_value("SHM_SIZE_ALIGNED", (size & 7) == 0);
        write_marker_value("SHM_SIZE_IN_RANGE", size >= 0x40 && size < 0x40000000UL);
    }
    result = ((unsigned char (*)(const void *))is_shm_acceptable_hook.target)(mapping);
    write_marker_value("SHM_ACCEPTABLE_RESULT", result);
    patch(&is_shm_acceptable_hook, 1);
    __sync_lock_release(&is_shm_acceptable_lock);
    return result;
}

/* WritableSharedMemoryRegion::Create(size) -> region (sret in rdi). Logged so
 * we can see whether creation yields a valid region at all. */
static void *traced_wsr_create(void *sret, unsigned long size) {
    void *result;
    while (__sync_lock_test_and_set(&wsr_lock, 1)) { }
    patch(&wsr_create_hook, 0);
    result = ((void *(*)(void *, unsigned long))wsr_create_hook.target)(sret, size);
    write_marker_value("WSR_CREATE", size);
    if (sret) {
        write_marker_value("WSR_CREATE_VALID",
                           (unsigned long)(*(const unsigned char *)sret != 0));
    }
    patch(&wsr_create_hook, 1);
    __sync_lock_release(&wsr_lock);
    return result;
}

/* WritableSharedMemoryRegion::Map(mapper) -> mapping (sret in rdi, this in rsi).
 * The mapping's base pointer is the first field of the sret object; a null base
 * is what makes CreateWithSharedMemoryRegion bail without writing a header. */
static void traced_wsr_map(void *sret, const void *self, void *mapper) {
    while (__sync_lock_test_and_set(&wsr_lock, 1)) { }
    patch(&wsr_map_hook, 0);
    ((void (*)(void *, const void *, void *))wsr_map_hook.target)(sret, self, mapper);
    write_marker("WSR_MAP");
    if (sret) {
        const unsigned long *w = (const unsigned long *)sret;
        write_marker_value("WSR_MAP_BASE", w[0]);
        write_marker_value("WSR_MAP_SIZE", w[1]);
        write_marker_value("WSR_MAP_OK", w[0] != 0);
    }
    patch(&wsr_map_hook, 1);
    __sync_lock_release(&wsr_lock);
}

/* ContentSize/DataSize/used/free live at known offsets in the allocator; log
 * them with the request so a too-small region is obvious. */
static unsigned int traced_persist_allocate(void *self, unsigned long req_size,
                                            unsigned int type) {
    unsigned int result;
    while (__sync_lock_test_and_set(&persist_allocate_lock, 1)) { }
    patch(&persist_allocate_hook, 0);
    write_marker("PERSIST_ALLOC");
    write_marker_value("PA_REQUEST", req_size);
    write_marker_value("PA_TYPE", type);
    if (self) {
        /* From Allocate's disassembly: +0x8 = memory descriptor ptr,
         * +0x14 = region size (u32). The descriptor holds: +0x24 = "corrupt"
         * flag byte, +0x28 = used (u32, atomic). */
        const unsigned char *mem = *(const unsigned char *const *)((const unsigned char *)self + 0x8);
        write_marker_value("PA_SIZE", *(const unsigned int *)((const unsigned char *)self + 0x14));
        if (mem) {
            write_marker_value("PA_USED", *(const unsigned int *)(mem + 0x28));
            write_marker_value("PA_CORRUPTFLAG", *(const unsigned char *)(mem + 0x24));
            write_marker_value("PA_BASE", (unsigned long) mem);
        }
    }
    result = ((unsigned int (*)(void *, unsigned long, unsigned int))persist_allocate_hook.target)(
        self, req_size, type);
    write_marker_value("PA_RESULT", result);
    patch(&persist_allocate_hook, 1);
    __sync_lock_release(&persist_allocate_lock);
    return result;
}

/* base::PersistentMemoryAllocator ctor: rsi=memory.base, rdx=memory.size,
 * rcx=size. Logs every allocator's region so the corrupted one can be tied to a
 * region without arming the hot Allocate. */
static void traced_persist_ctor(void *self, void *base, unsigned long memsize,
                                unsigned long size, unsigned long page_size,
                                unsigned long id) {
    while (__sync_lock_test_and_set(&persist_ctor_lock, 1)) { }
    patch(&persist_ctor_hook, 0);
    write_marker_value("PERSIST_CTOR_BASE", (unsigned long)base);
    write_marker_value("PERSIST_CTOR_MEMSIZE", memsize);
    write_marker_value("PERSIST_CTOR_SIZE", size);
    write_marker_value("PERSIST_CTOR_ID", id);
    ((void (*)(void *, void *, unsigned long, unsigned long, unsigned long, unsigned long))
         persist_ctor_hook.target)(self, base, memsize, size, page_size, id);
    if (base) {
        const unsigned long *w = (const unsigned long *)base;
        write_marker_value("PERSIST_CTOR_HDR0", w[0]);
        write_marker_value("PERSIST_CTOR_HDR1", w[1]);
    }
    patch(&persist_ctor_hook, 1);
    __sync_lock_release(&persist_ctor_lock);
}

/* Present-path probes (M57bp). Each logs only; none nests into another. */
static void traced_display_update_layer_tree(void *self, const void *params) {
    present_path_acquire();
    patch(&display_update_layer_tree_hook, 0);
    write_marker("DISPLAY_UPDATE_LAYER_TREE");
    write_marker_value("DULT_PARAMS", (unsigned long)params);
    ((void (*)(void *, const void *))display_update_layer_tree_hook.target)(self, params);
    patch(&display_update_layer_tree_hook, 1);
    present_path_release();
}

static void traced_display_got_layer_frame(void *self, unsigned context_id) {
    present_path_acquire();
    patch(&display_got_layer_frame_hook, 0);
    write_marker_value("DISPLAY_GOT_LAYER_FRAME", context_id);
    ((void (*)(void *, unsigned))display_got_layer_frame_hook.target)(self, context_id);
    patch(&display_got_layer_frame_hook, 1);
    present_path_release();
}

static void traced_compositor_set_visible(void *self, int visible) {
    present_path_acquire();
    patch(&compositor_set_visible_hook, 0);
    write_marker_value("COMPOSITOR_SET_VISIBLE", (unsigned long)visible);
    ((void (*)(void *, int))compositor_set_visible_hook.target)(self, visible);
    patch(&compositor_set_visible_hook, 1);
    present_path_release();
}

static void traced_compositor_set_frame_sink(void *self, void *sink, void *display_private) {
    present_path_acquire();
    patch(&compositor_set_frame_sink_hook, 0);
    write_marker_value("COMPOSITOR_SET_FRAME_SINK", (unsigned long)sink);
    ((void (*)(void *, void *, void *))compositor_set_frame_sink_hook.target)(
        self, sink, display_private);
    patch(&compositor_set_frame_sink_hook, 1);
    present_path_release();
}

static void traced_display_draw_and_swap(void *self, const void *params) {
    present_path_acquire();
    patch(&display_draw_and_swap_hook, 0);
    write_marker("DISPLAY_DRAW_AND_SWAP");
    ((void (*)(void *, const void *))display_draw_and_swap_hook.target)(self, params);
    patch(&display_draw_and_swap_hook, 1);
    present_path_release();
}

static void traced_display_scheduler_on_begin_frame(void *self, const void *args) {
    present_path_acquire();
    patch(&display_scheduler_on_begin_frame_hook, 0);
    write_marker("DISPLAY_SCHEDULER_ON_BEGIN_FRAME");
    ((void (*)(void *, const void *))display_scheduler_on_begin_frame_hook.target)(self, args);
    patch(&display_scheduler_on_begin_frame_hook, 1);
    present_path_release();
}

static void traced_native_widget_on_visibility(void *self, int visible) {
    present_path_acquire();
    patch(&native_widget_on_visibility_hook, 0);
    write_marker_value("NATIVE_WIDGET_ON_VISIBILITY", (unsigned long)visible);
    ((void (*)(void *, int))native_widget_on_visibility_hook.target)(self, visible);
    patch(&native_widget_on_visibility_hook, 1);
    present_path_release();
}

static void traced_native_widget_mac_show(void *self, int state, const void *bounds) {
    present_path_acquire();
    patch(&native_widget_mac_show_hook, 0);
    write_marker_value("NATIVE_WIDGET_MAC_SHOW", (unsigned long)state);
    ((void (*)(void *, int, const void *))native_widget_mac_show_hook.target)(self, state, bounds);
    patch(&native_widget_mac_show_hook, 1);
    present_path_release();
}

static void traced_rwhv_show_with_visibility(void *self, int state) {
    present_path_acquire();
    patch(&rwhv_show_with_visibility_hook, 0);
    write_marker_value("RWHV_SHOW_WITH_VISIBILITY", (unsigned long)state);
    ((void (*)(void *, int))rwhv_show_with_visibility_hook.target)(self, state);
    patch(&rwhv_show_with_visibility_hook, 1);
    present_path_release();
    /* M57bv diagnostic: force the window shown (the app waits for ready-to-show). */
    if (g_native_window_mac && !g_forced_show && nativewindowmac_show_hook.target) {
        g_forced_show = 1;
        write_marker("FORCE_NATIVEWINDOWMAC_SHOW");
        ((void (*)(void *))nativewindowmac_show_hook.target)((void *)g_native_window_mac);
    }
}

/* Generic loggers for the present-path bool/void hooks (M57bp). */
static void present_bool_log(const char *marker, void *self, int value, struct hook *hook) {
    present_path_acquire();
    patch(hook, 0);
    write_marker_value(marker, (unsigned long)value);
    ((void (*)(void *, int))hook->target)(self, value);
    patch(hook, 1);
    present_path_release();
}

static void present_void_log(const char *marker, void *self, struct hook *hook) {
    present_path_acquire();
    patch(hook, 0);
    write_marker(marker);
    ((void (*)(void *))hook->target)(self);
    patch(hook, 1);
    present_path_release();
}

static void traced_recyclable_suspend(void *self) {
    present_path_acquire();
    patch(&recyclable_suspend_hook, 0);
    write_marker("RECYCLABLE_SUSPEND");
    ((void (*)(void *))recyclable_suspend_hook.target)(self);
    patch(&recyclable_suspend_hook, 1);
    present_path_release();
}

static void traced_recyclable_unsuspend(void *self) {
    present_void_log("RECYCLABLE_UNSUSPEND", self, &recyclable_unsuspend_hook);
}

static void traced_viz_display_set_visible(void *self, int value) {
    present_bool_log("VIZ_DISPLAY_SET_VISIBLE", self, value, &viz_display_set_visible_hook);
}

static void traced_viz_display_scheduler_set_visible(void *self, int value) {
    present_bool_log("VIZ_DISPLAY_SCHEDULER_SET_VISIBLE", self, value,
                     &viz_display_scheduler_set_visible_hook);
}

static void traced_viz_root_set_display_visible(void *self, int value) {
    present_bool_log("VIZ_ROOT_SET_DISPLAY_VISIBLE", self, value,
                     &viz_root_set_display_visible_hook);
}

static void traced_electron_occlusion(void *self, void *cmd, void *notification) {
    present_path_acquire();
    patch(&electron_occlusion_hook, 0);
    write_marker("ELECTRON_WINDOW_OCCLUSION");
    ((void (*)(void *, void *, void *))electron_occlusion_hook.target)(self, cmd, notification);
    patch(&electron_occlusion_hook, 1);
    present_path_release();
}

static void traced_webcontents_visibility(void *self, int visibility) {
    present_bool_log("WEBCONTENTS_ON_WINDOW_VISIBILITY", self, visibility,
                     &webcontents_visibility_hook);
}

static void traced_native_widget_set_visibility(void *self, int state) {
    present_bool_log("NATIVE_WIDGET_SET_VISIBILITY", self, state,
                     &native_widget_set_visibility_hook);
}

static void traced_browserwindow_ctor(void *self, void *args, void *dict) {
    present_path_acquire();
    patch(&browserwindow_ctor_hook, 0);
    write_marker("BROWSERWINDOW_CTOR");
    ((void (*)(void *, void *, void *))browserwindow_ctor_hook.target)(self, args, dict);
    write_marker("BROWSERWINDOW_CTOR_DONE");
    patch(&browserwindow_ctor_hook, 1);
    present_path_release();
}

static void traced_basewindow_ctor(void *self, void *isolate, void *dict) {
    present_path_acquire();
    patch(&basewindow_ctor_hook, 0);
    write_marker("BASEWINDOW_CTOR");
    ((void (*)(void *, void *, void *))basewindow_ctor_hook.target)(self, isolate, dict);
    write_marker("BASEWINDOW_CTOR_DONE");
    patch(&basewindow_ctor_hook, 1);
    present_path_release();
}

static void *traced_nativewindow_create(void *dict, void *parent) {
    void *result;
    present_path_acquire();
    patch(&nativewindow_create_hook, 0);
    write_marker("NATIVEWINDOW_CREATE");
    result = ((void *(*)(void *, void *))nativewindow_create_hook.target)(dict, parent);
    write_marker_value("NATIVEWINDOW_CREATE_DONE", (unsigned long)result);
    patch(&nativewindow_create_hook, 1);
    present_path_release();
    return result;
}

static void *traced_webcontents_from_prefs(void *isolate, void *dict) {
    void *result;
    present_path_acquire();
    patch(&webcontents_from_prefs_hook, 0);
    write_marker("WEBCONTENTS_FROM_PREFS");
    result = ((void *(*)(void *, void *))webcontents_from_prefs_hook.target)(isolate, dict);
    write_marker_value("WEBCONTENTS_FROM_PREFS_DONE", (unsigned long)result);
    patch(&webcontents_from_prefs_hook, 1);
    present_path_release();
    return result;
}

static unsigned int traced_gin_get_bool(void *self, void *name, void *out) {
    unsigned int r;
    present_path_acquire();
    patch(&gin_get_bool_hook, 0);
    write_marker("GIN_GET_BOOL");
    r = ((unsigned int (*)(void *, void *, void *))gin_get_bool_hook.target)(self, name, out);
    write_marker_value("GIN_GET_BOOL_DONE", r);
    patch(&gin_get_bool_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_gin_set_bool(void *self, void *name, void *val) {
    unsigned int r;
    present_path_acquire();
    patch(&gin_set_bool_hook, 0);
    write_marker("GIN_SET_BOOL");
    r = ((unsigned int (*)(void *, void *, void *))gin_set_bool_hook.target)(self, name, val);
    write_marker_value("GIN_SET_BOOL_DONE", r);
    patch(&gin_set_bool_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_gin_get_string(void *self, void *name, void *out) {
    unsigned int r;
    present_path_acquire();
    patch(&gin_get_string_hook, 0);
    write_marker("GIN_GET_STRING");
    r = ((unsigned int (*)(void *, void *, void *))gin_get_string_hook.target)(self, name, out);
    write_marker_value("GIN_GET_STRING_DONE", r);
    patch(&gin_get_string_hook, 1);
    present_path_release();
    return r;
}

static unsigned long traced_v8_private_forapi(void *isolate, void *name) {
    unsigned long r;
    present_path_acquire();
    patch(&v8_private_forapi_hook, 0);
    write_marker("V8_PRIVATE_FORAPI");
    r = ((unsigned long (*)(void *, void *))v8_private_forapi_hook.target)(isolate, name);
    write_marker_value("V8_PRIVATE_FORAPI_DONE", r);
    patch(&v8_private_forapi_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_v8_set_private(void *self, void *context, void *priv, void *value) {
    unsigned int r;
    present_path_acquire();
    patch(&v8_set_private_hook, 0);
    write_marker("V8_SET_PRIVATE");
    r = ((unsigned int (*)(void *, void *, void *, void *))v8_set_private_hook.target)(
        self, context, priv, value);
    write_marker_value("V8_SET_PRIVATE_DONE", r);
    patch(&v8_set_private_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_webcontents_set_owner(void *self, void *owner) {
    unsigned int r;
    present_path_acquire();
    patch(&webcontents_set_owner_hook, 0);
    write_marker("WEBCONTENTS_SET_OWNER");
    r = ((unsigned int (*)(void *, void *))webcontents_set_owner_hook.target)(self, owner);
    write_marker_value("WEBCONTENTS_SET_OWNER_DONE", r);
    patch(&webcontents_set_owner_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_basewindow_set_contentview(void *self, void *a, void *b) {
    unsigned int r;
    present_path_acquire();
    patch(&basewindow_set_contentview_hook, 0);
    write_marker("BASEWINDOW_SET_CONTENTVIEW");
    r = ((unsigned int (*)(void *, void *, void *))basewindow_set_contentview_hook.target)(self, a, b);
    write_marker_value("BASEWINDOW_SET_CONTENTVIEW_DONE", r);
    patch(&basewindow_set_contentview_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_browserwindow_override_contentview(void *self, void *view) {
    unsigned int r;
    present_path_acquire();
    patch(&browserwindow_override_contentview_hook, 0);
    write_marker("BROWSERWINDOW_OVERRIDE_CONTENTVIEW");
    r = ((unsigned int (*)(void *, void *))browserwindow_override_contentview_hook.target)(self, view);
    write_marker_value("BROWSERWINDOW_OVERRIDE_CONTENTVIEW_DONE", r);
    patch(&browserwindow_override_contentview_hook, 1);
    present_path_release();
    return r;
}

static unsigned int traced_nativewindow_initfromoptions(void *self, void *dict) {
    unsigned int r;
    present_path_acquire();
    patch(&nativewindow_initfromoptions_hook, 0);
    write_marker("NATIVEWINDOW_INITFROMOPTIONS");
    r = ((unsigned int (*)(void *, void *))nativewindow_initfromoptions_hook.target)(self, dict);
    write_marker_value("NATIVEWINDOW_INITFROMOPTIONS_DONE", r);
    patch(&nativewindow_initfromoptions_hook, 1);
    present_path_release();
    return r;
}

static void traced_webcontents_ctor(void *self, void *isolate, void *dict) {
    present_path_acquire();
    patch(&webcontents_ctor_hook, 0);
    write_marker("WEBCONTENTS_CTOR");
    ((void (*)(void *, void *, void *))webcontents_ctor_hook.target)(self, isolate, dict);
    write_marker("WEBCONTENTS_CTOR_DONE");
    patch(&webcontents_ctor_hook, 1);
    present_path_release();
}

static void traced_nativewindowmac_ctor(void *self, void *dict, void *owner) {
    present_path_acquire();
    patch(&nativewindowmac_ctor_hook, 0);
    ((void (*)(void *, void *, void *))nativewindowmac_ctor_hook.target)(self, dict, owner);
    g_native_window_mac = (unsigned long)self;
    write_marker_value("NATIVEWINDOWMAC_CTOR", (unsigned long)self);
    patch(&nativewindowmac_ctor_hook, 1);
    present_path_release();
}

static void traced_nativewindowmac_show(void *self) {
    present_void_log("NATIVEWINDOWMAC_SHOW", self, &nativewindowmac_show_hook);
}

static void traced_nativewindowmac_show_inactive(void *self) {
    present_void_log("NATIVEWINDOWMAC_SHOW_INACTIVE", self, &nativewindowmac_show_inactive_hook);
}

static void traced_nativewidgetmac_nswindow_order_front(void *self, void *cmd, void *sender) {
    present_path_acquire();
    patch(&nativewidgetmac_nswindow_order_front_hook, 0);
    write_marker("NSWINDOW_ORDER_FRONT_KEEP_KEY");
    ((void (*)(void *, void *, void *))nativewidgetmac_nswindow_order_front_hook.target)(
        self, cmd, sender);
    patch(&nativewidgetmac_nswindow_order_front_hook, 1);
    present_path_release();
}

static void traced_run_callback(void *callback, void *receiver) {    while (__sync_lock_test_and_set(&run_callback_lock, 1)) { }
    patch(&run_callback_hook, 0);
    write_marker("RUN_CALLBACK");
    ((void (*)(void *, void *))run_callback_hook.target)(callback, receiver);
    patch(&run_callback_hook, 1);
    __sync_lock_release(&run_callback_lock);
}

static unsigned int traced_post_task(void *self, void *location, void *task) {
    unsigned int result;
    int match;
    while (__sync_lock_test_and_set(&post_task_lock, 1)) { }
    patch(&post_task_hook, 0);
    match = cb_runner && (unsigned long)self == cb_runner;
    if (match) {
        void *cur = ((void *(*)(void))(framework_base + 0x37fd0e0))();
        write_marker("POST_TASK_MATCH");
        write_marker_value("POST_TASK_CUR_RUNNER", (unsigned long)cur);
        write_marker_value("POST_TASK_SAME_SEQ", (unsigned long)cur == cb_runner);
        if (task) {
            write_marker_value("POST_TASK_INVOKE0", ((const unsigned long *)task)[0]);
            write_marker_value("POST_TASK_INVOKE1", ((const unsigned long *)task)[1]);
        }
    }
    result = ((unsigned int (*)(void *, void *, void *))post_task_hook.target)(
        self, location, task);
    if (match) write_marker_value("POST_TASK_RESULT", result);
    patch(&post_task_hook, 1);
    __sync_lock_release(&post_task_lock);
    return result;
}

/* TaskQueueImpl::TaskRunner::PostDelayedTask: self == cb_runner for the UI
 * queue, so this arms wake-up tracing lazily and reports same-sequence. */
static unsigned long traced_post_delayed(void *self, void *location, void *task,
                                         unsigned long delta) {
    unsigned long result;
    while (__sync_lock_test_and_set(&post_delayed_lock, 1)) { }
    patch(&post_delayed_hook, 0);
    if (cb_runner && (unsigned long)self == cb_runner) {
        void *cur = ((void *(*)(void))(framework_base + 0x37fd0e0))();
        unsigned int same = ((unsigned int (*)(void *))(framework_base + RUNS_IN_SEQ_VA))(self);
        patch(&thread_schedule_hook, 1);
        patch(&pump_default_schedule_hook, 1);
        patch(&pump_cf_schedule_hook, 1);
        write_marker("POST_DELAYED_UI");
        write_marker_value("POST_DELAYED_SAME_SEQ", (unsigned long)(unsigned int)same);
        write_marker_value("POST_DELAYED_CUR_IS_RUNNER", (unsigned long)cur == cb_runner);
    }
    result = ((unsigned long (*)(void *, void *, void *, unsigned long))post_delayed_hook.target)(
        self, location, task, delta);
    patch(&post_delayed_hook, 1);
    __sync_lock_release(&post_delayed_lock);
    return result;
}

static void traced_thread_schedule(void *self) {
    while (__sync_lock_test_and_set(&thread_schedule_lock, 1)) { }
    patch(&thread_schedule_hook, 0);
    write_marker("THREAD_SCHEDULE_WORK");
    ((void (*)(void *))thread_schedule_hook.target)(self);
    patch(&thread_schedule_hook, 1);
    __sync_lock_release(&thread_schedule_lock);
}

static void traced_pump_default_schedule(void *self) {
    while (__sync_lock_test_and_set(&pump_default_schedule_lock, 1)) { }
    patch(&pump_default_schedule_hook, 0);
    write_marker("PUMP_DEFAULT_SCHEDULE");
    ((void (*)(void *))pump_default_schedule_hook.target)(self);
    patch(&pump_default_schedule_hook, 1);
    __sync_lock_release(&pump_default_schedule_lock);
}

static void traced_pump_cf_schedule(void *self) {
    while (__sync_lock_test_and_set(&pump_cf_schedule_lock, 1)) { }
    patch(&pump_cf_schedule_hook, 0);
    write_marker("PUMP_CF_SCHEDULE");
    ((void (*)(void *))pump_cf_schedule_hook.target)(self);
    patch(&pump_cf_schedule_hook, 1);
    __sync_lock_release(&pump_cf_schedule_lock);
}

static void traced_transmit(void *self, const void *node_name,
                            const unsigned char *message_slot) {
    struct record r;
    unsigned long i;
    const void *message = message_slot ? *(const void * const *)message_slot : 0;
    const unsigned char *bytes = 0;
    unsigned long byte_count = 0;
    unsigned long handle_count = 0;
    int tracked = 0;

    /* Only one thread may temporarily expose/call the original prologue. Other
     * callers entering while it is exposed simply bypass this hook. */
    while (__sync_lock_test_and_set(&patch_lock, 1)) { }
    patch(&transmit_hook, 0);

    if (message && framework_base) {
        struct payload_span { const unsigned char *data; unsigned long size; } span;
        span = ((struct payload_span (*)(const void *))(framework_base + 0x72e040))(message);
        bytes = span.data;
        byte_count = ((unsigned long (*)(const void *))(framework_base + 0x72e110))(message);
        handle_count = ((unsigned long (*)(const void *))(framework_base + 0x72e1b0))(message);
        for (i = 0; i + 4 <= byte_count && i + 4 <= CAPTURE; ++i) {
            if (bytes[i] == 0xcd && bytes[i + 1] == 0x54 &&
                bytes[i + 2] == 0x3b && bytes[i + 3] == 0x55) {
                tracked = 1;
                break;
            }
        }
    }

    r.magic = 0x5a435049; /* "IPCZ" in the little-endian file. */
    r.pid = (unsigned int)getpid();
    r.sequence = __sync_fetch_and_add(&sequence, 1);
    r.byte_count = byte_count;
    r.handle_count = handle_count;
    for (i = 0; i < CAPTURE; ++i)
        r.bytes[i] = (bytes && i < byte_count) ? bytes[i] : 0;
    {
        int fd = open("/Volumes/SystemRoot/tmp/m57-ipcz.bin", 1 | 0x200 | 8, 0644);
        if (fd >= 0) { write(fd, &r, sizeof(r)); close(fd); }
    }

    if (tracked) {
        if (node_name) {
            write_marker_value("SOURCE_NODE_0", ((const unsigned long *)node_name)[0]);
            write_marker_value("SOURCE_NODE_1", ((const unsigned long *)node_name)[1]);
        }
        patch(&accept_hook, 1);
        patch(&internal_hook, 1);
        patch(&user_message_hook, 1);
        patch(&get_port_hook, 1);
        patch(&accept_message_hook, 1);
        patch(&forward_proxy_hook, 1);
        patch(&port_status_hook, 1);
        patch(&pipe_observer_hook, 1);
        patch(&watcher_notify_hook, 1);
        patch(&dispatcher_notify_hook, 1);
        patch(&watch_notify_hook, 1);
        patch(&watch_callback_hook, 1);
    }
    ((void (*)(void *, const void *, const unsigned char *))transmit_hook.target)(
        self, node_name, message_slot);
    if (tracked) {
        patch(&watch_callback_hook, 0);
        patch(&watch_notify_hook, 0);
        patch(&dispatcher_notify_hook, 0);
        patch(&watcher_notify_hook, 0);
        patch(&pipe_observer_hook, 0);
        patch(&port_status_hook, 0);
        patch(&forward_proxy_hook, 0);
        patch(&accept_message_hook, 0);
        patch(&get_port_hook, 0);
        patch(&user_message_hook, 0);
        patch(&internal_hook, 0);
        patch(&accept_hook, 0);
    }
    patch(&transmit_hook, 1);
    __sync_lock_release(&patch_lock);
}

/* Emits a string as PREFIX_LEN + PREFIX_00..PREFIX_15 (8 bytes per chunk). */
static void write_marker_string(const char *prefix, const char *s) {
    unsigned long len = 0;
    unsigned i, k, n;
    char name[48];
    if (!s) s = "";
    while (len < 128 && s[len]) ++len;
    for (n = 0; prefix[n] && n < 40; ++n) name[n] = prefix[n];
    name[n] = '_'; name[n + 1] = 'L'; name[n + 2] = 'E'; name[n + 3] = 'N'; name[n + 4] = 0;
    write_marker_value(name, len);
    for (i = 0; i < 16; ++i) {
        unsigned long v = 0;
        for (k = 0; k < 8 && i * 8 + k < len; ++k)
            v |= (unsigned long)(unsigned char)s[i * 8 + k] << (8 * k);
        for (n = 0; prefix[n] && n < 40; ++n) name[n] = prefix[n];
        name[n] = '_';
        name[n + 1] = (char)('0' + (i / 10) % 10);
        name[n + 2] = (char)('0' + (i % 10));
        name[n + 3] = 0;
        write_marker_value(name, v);
    }
}

/* Identifies the dyld image containing addr without parsing Mach-O headers:
 * take the nearest image header <= addr and the next header > addr, so the
 * image's [base, next) range is known. Logs the path, offset and containment. */
static void log_addr_image(const char *prefix, unsigned long addr) {
    unsigned i, n = _dyld_image_count();
    unsigned best = ~0u;
    unsigned long bestbase = 0, next = ~0UL;
    for (i = 0; i < n; ++i) {
        unsigned long h = (unsigned long)_dyld_get_image_header(i);
        if (!h) continue;
        if (h <= addr && (best == ~0u || h > bestbase)) {
            bestbase = h;
            best = i;
        }
        if (h > addr && h < next) next = h;
    }
    if (best != ~0u) {
        write_marker_string(prefix, _dyld_get_image_name(best));
        write_marker_value("GLA_GI_FN_NEAR_OFF", addr - bestbase);
        write_marker_value("GLA_GI_FN_NEAR_NEXT", next);
        write_marker_value("GLA_GI_FN_NEAR_IN",
                           (next == ~0UL || addr < next) ? 1UL : 0UL);
        write_marker("GLA_GI_FN_NEAR_END");
        return;
    }
    write_marker_value("GLA_GI_FN_NOIMG", addr);
}

/* Prints the loaded EGL/GL images (captured in the Chromium log) so an EGL/GL
 * library pairing mismatch is visible. */
static void dump_gl_images(void) {
    unsigned i, n = _dyld_image_count();
    for (i = 0; i < n; ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && (strstr(name, "EGL") || strstr(name, "GLES") ||
                     strstr(name, "OpenGL") || strstr(name, "ANGLE") ||
                     strstr(name, "GLRenderer") || strstr(name, "libGL"))) {
            printf("M57IMG %p %s\n", (void *)_dyld_get_image_header(i), name);
        }
    }
    fflush(0);
}

/* Base address of the first dyld image whose path contains needle. */
static unsigned long find_image_base(const char *needle) {
    unsigned i, n = _dyld_image_count();
    for (i = 0; i < n; ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, needle))
            return (unsigned long)_dyld_get_image_header(i);
    }
    return 0;
}

/* Builds a fixed marker name with a two-digit index suffix, e.g.
 * ("GL_CTX_Q", 3) -> "GL_CTX_Q03". */
static void marker_name_index(char *out, const char *base, unsigned idx) {
    unsigned i = 0;
    while (base[i] && i < 26) { out[i] = base[i]; ++i; }
    out[i++] = (char)('0' + (idx / 10) % 10);
    out[i++] = (char)('0' + (idx % 10));
    out[i] = 0;
}

/* Chromium's requested GL context attributes, captured at the entry to
 * gl::GLContextEGL::Initialize. The final EGLint array is a local vector built
 * inside the function (not reachable from the entry), so dump the
 * GLContextAttribs object plus the words the disassembly reads directly
 * (+0xc, +0x10, +0x14); the extension gates are named by the GFX_HAS_* records
 * emitted while DisplayExtensionsEGL::InitializeExtensionSettings runs. */
static unsigned char traced_gl_ctx_init(void *self, void *surface, void *attribs) {
    unsigned char result;
    while (__sync_lock_test_and_set(&gl_ctx_init_lock, 1)) { }
    patch(&gl_ctx_init_hook, 0);
    write_marker_value("GL_CTX_INIT", (unsigned long)self);
    write_marker_value("GL_CTX_SURFACE", (unsigned long)surface);
    write_marker_value("GL_CTX_ATTRIBS", (unsigned long)attribs);
    if (attribs) {
        const unsigned long *q = (const unsigned long *)attribs;
        const unsigned char *b = (const unsigned char *)attribs;
        char name[32];
        unsigned i;
        for (i = 0; i < 8; ++i) {
            marker_name_index(name, "GL_CTX_Q", i);
            write_marker_value(name, q[i]);
        }
        write_marker_value("GL_CTX_A0C", *(const unsigned int *)(b + 0x0c));
        write_marker_value("GL_CTX_A10", *(const unsigned int *)(b + 0x10));
        write_marker_value("GL_CTX_A14", *(const unsigned char *)(b + 0x14));
        if (force_no_error_off < 0) {
            const char *v = getenv("M57_FORCE_NO_ERROR_OFF");
            force_no_error_off = (v && v[0] == '1') ? 1 : 0;
        }
        if (force_no_error_off) {
            write_marker_value("GL_CTX_FORCE_NO_ERROR_OFF",
                               *(const unsigned char *)(b + 0x14));
            *(unsigned char *)((unsigned char *)attribs + 0x14) = 0;
        }
    }
    result = ((unsigned char (*)(void *, void *, void *))gl_ctx_init_hook.target)(
        self, surface, attribs);
    write_marker_value("GL_CTX_INIT_RESULT", result);
    patch(&gl_ctx_init_hook, 1);
    __sync_lock_release(&gl_ctx_init_lock);
    return result;
}

/* Chromium's per-display EGL extension parse. Arms gfx::HasExtension only for
 * the duration of this call so the general-purpose helper is not hooked during
 * boot, and dumps the DisplayExtensionsEGL object's leading words. */
static void traced_egl_ext_settings(void *self, void *display) {
    unsigned i;
    while (__sync_lock_test_and_set(&egl_ext_settings_lock, 1)) { }
    patch(&egl_ext_settings_hook, 0);
    write_marker_value("EGL_EXT_SETTINGS", (unsigned long)self);
    write_marker_value("EGL_EXT_DISPLAY", (unsigned long)display);
    for (i = 0; self && i < 16; ++i) {
        char name[32];
        marker_name_index(name, "EGL_EXT_DUMP_", i);
        write_marker_value(name, ((const unsigned long *)self)[i]);
    }
    patch(&gfx_has_extension_hook, 1);
    ((void (*)(void *, void *))egl_ext_settings_hook.target)(self, display);
    patch(&gfx_has_extension_hook, 0);
    write_marker("EGL_EXT_SETTINGS_END");
    patch(&egl_ext_settings_hook, 1);
    __sync_lock_release(&egl_ext_settings_lock);
}

/* gfx::HasExtension(extensions, StringPiece name): the extension name is a
 * {const char* data; size_t len} at %rsi. Emits the queried extension and the
 * result so Chromium's per-display view can be diffed against ANGLE's
 * advertised set (M57s). rdx is forwarded verbatim to the original. */
static unsigned char traced_gfx_has_extension(void *extensions, const void *piece,
                                              void *rdx) {
    unsigned char result;
    while (__sync_lock_test_and_set(&gfx_has_extension_lock, 1)) { }
    patch(&gfx_has_extension_hook, 0);
    if (piece) {
        const unsigned long *w = (const unsigned long *)piece;
        const char *s = (const char *)w[0];
        unsigned long len = w[1] > 48 ? 48 : w[1];
        if (s && len) {
            char name[32];
            unsigned j, k;
            write_marker_value("GFX_HAS_NAME_LEN", len);
            for (j = 0; j < 6; ++j) {
                unsigned long v = 0;
                for (k = 0; k < 8 && j * 8 + k < len; ++k)
                    v |= (unsigned long)(unsigned char)s[j * 8 + k] << (8 * k);
                marker_name_index(name, "GFX_HAS_NAME_", j);
                write_marker_value(name, v);
            }
        }
    }
    result = ((unsigned char (*)(void *, const void *, void *))gfx_has_extension_hook.target)(
        extensions, piece, rdx);
    write_marker_value("GFX_HAS_RESULT", result);
    patch(&gfx_has_extension_hook, 1);
    __sync_lock_release(&gfx_has_extension_lock);
    return result;
}

/* Dumps the final EGLint context-attribute array Chromium passes to
 * eglCreateContext (5th argument, %r8). The array is {name, value, ...}
 * terminated by EGL_NONE (0x3038). This is the array that actually reaches
 * ANGLE, so it names the rejected attribute directly. */
static void egl_create_context_log(void *self, void *display, void *config,
                                   void *share, const void *attribs) {
    char name[32];
    unsigned long n = 0;
    write_marker_value("EGL_CREATE_CTX", (unsigned long)self);
    write_marker_value("EGL_CREATE_DISPLAY", (unsigned long)display);
    write_marker_value("EGL_CREATE_CONFIG", (unsigned long)config);
    write_marker_value("EGL_CREATE_SHARE", (unsigned long)share);
    write_marker_value("EGL_CREATE_ATTRIBS", (unsigned long)attribs);
    if (attribs) {
        const unsigned int *a = (const unsigned int *)attribs;
        while (n < 40 && a[n * 2] != EGL_NONE) {
            unsigned long packed = (unsigned long)a[n * 2] |
                                   ((unsigned long)a[n * 2 + 1] << 32);
            marker_name_index(name, "EGL_CTX_ATTR_", (unsigned)n);
            write_marker_value(name, packed);
            ++n;
        }
        write_marker_value("EGL_CTX_ATTR_COUNT", n);
    }
}

static void *traced_egl_create_context_base(void *self, void *display, void *config,
                                            void *share, const void *attribs) {
    void *result;
    while (__sync_lock_test_and_set(&egl_cc_base_lock, 1)) { }
    patch(&egl_create_context_base_hook, 0);
    egl_create_context_log(self, display, config, share, attribs);
    result = ((void *(*)(void *, void *, void *, void *, const void *))
                  egl_create_context_base_hook.target)(self, display, config, share, attribs);
    write_marker_value("EGL_CREATE_RESULT", (unsigned long)result);
    patch(&egl_create_context_base_hook, 1);
    __sync_lock_release(&egl_cc_base_lock);
    return result;
}

static void *traced_egl_create_context_trace(void *self, void *display, void *config,
                                             void *share, const void *attribs) {
    void *result;
    while (__sync_lock_test_and_set(&egl_cc_trace_lock, 1)) { }
    patch(&egl_create_context_trace_hook, 0);
    egl_create_context_log(self, display, config, share, attribs);
    result = ((void *(*)(void *, void *, void *, void *, const void *))
                  egl_create_context_trace_hook.target)(self, display, config, share, attribs);
    write_marker_value("EGL_CREATE_RESULT", (unsigned long)result);
    patch(&egl_create_context_trace_hook, 1);
    __sync_lock_release(&egl_cc_trace_lock);
    return result;
}

/* Shared glGetIntegerv tracer: only GL_MAX_VERTEX_ATTRIBS is logged, and the
 * pre/post values show whether the handler actually writes the out-param (a
 * NoContextGLApi handler leaves the caller's 0 untouched). */
static void traced_gla_getintegerv_common(const char *pre, const char *post, void *self,
                                          unsigned pname, int *params, struct hook *hook,
                                          volatile int *lock, int is_base) {
    while (__sync_lock_test_and_set(lock, 1)) { }
    patch(hook, 0);
    if (pname == GL_MAX_VERTEX_ATTRIBS) {
        write_marker_value(pre, params ? (unsigned long)(unsigned)*params : ~0UL);
        if (is_base) {
            /* GLApiBase reads this+8 -> real_api, then real_api+0x5f8 is the
             * loaded glGetIntegerv. Log it so the resolved target is visible. */
            void *real_api = *(void **)((char *)self + 8);
            unsigned long fn = real_api ? (unsigned long)(*(void **)((char *)real_api + 0x5f8)) : 0;
            write_marker_value("GLA_GI_REAL_API", (unsigned long)real_api);
            write_marker_value("GLA_GI_REAL_FN", fn);
            /* ANGLE's _GL_GetIntegerv calls its internal current-context getter
             * at libGLESv2+0x416c0 first; if that returns NULL the out-param is
             * left untouched. Call it to see ANGLE's view of the context. */
            {
                unsigned long gles = find_image_base("libGLESv2.dylib");
                if (gles) {
                    void *angle_ctx = ((void *(*)(void))(gles + 0x416c0))();
                    write_marker_value("GLA_GI_ANGLE_CTX", (unsigned long)angle_ctx);
                    write_marker_value("GLA_GI_THREAD", pthread_self());
                } else {
                    write_marker_value("GLA_GI_NO_GLES", 0);
                }
            }
            if (fn && !image_lookup_done) {
                image_lookup_done = 1;
                write_marker_value("M57_FRAMEWORK_BASE", (unsigned long)framework_base);
                write_marker_value("M57_IMAGE_COUNT", _dyld_image_count());
                log_addr_image("GLA_GI_FN_IMG", fn);
            }
        }
    }
    ((void (*)(void *, unsigned, int *))hook->target)(self, pname, params);
    if (pname == GL_MAX_VERTEX_ATTRIBS)
        write_marker_value(post, params ? (unsigned long)(unsigned)*params : ~0UL);
    patch(hook, 1);
    __sync_lock_release(lock);
}

static void traced_gla_getintegerv_base(void *self, unsigned pname, int *params) {
    traced_gla_getintegerv_common("GLA_GI_BASE_PRE", "GLA_GI_BASE_POST", self, pname,
                                  params, &gla_getintegerv_base_hook, &gla_gi_base_lock, 1);
}

static void traced_gla_getintegerv_nocontext(void *self, unsigned pname, int *params) {
    traced_gla_getintegerv_common("GLA_GI_NOCONTEXT_PRE", "GLA_GI_NOCONTEXT_POST", self,
                                  pname, params, &gla_getintegerv_nocontext_hook,
                                  &gla_gi_nocontext_lock, 0);
}

static void traced_gla_getintegerv_stub(void *self, unsigned pname, int *params) {
    traced_gla_getintegerv_common("GLA_GI_STUB_PRE", "GLA_GI_STUB_POST", self, pname,
                                  params, &gla_getintegerv_stub_hook, &gla_gi_stub_lock, 0);
}

/* eglMakeCurrent(this, display, draw, read, context) -> EGLBoolean. */
static void egl_make_current_log(const char *tag, void *self, void *display, void *draw,
                                 void *read, void *context, unsigned int result) {
    write_marker_value(tag, (unsigned long)self);
    write_marker_value("EGL_MC_DISPLAY", (unsigned long)display);
    write_marker_value("EGL_MC_DRAW", (unsigned long)draw);
    write_marker_value("EGL_MC_READ", (unsigned long)read);
    write_marker_value("EGL_MC_CONTEXT", (unsigned long)context);
    write_marker_value("EGL_MC_RESULT", result);
    write_marker_value("EGL_MC_THREAD", pthread_self());
    /* Resolve the real eglMakeCurrent Chromium is dispatching to, and which
     * module it lives in (1=libGLESv2, 2=libEGL, 3=Electron Framework, 0=other). */
    {
        void *real_api = *(void **)((char *)self + 8);
        unsigned long fn = real_api ? (unsigned long)(*(void **)((char *)real_api + 0x170)) : 0;
        unsigned long angle_gles = find_image_base("Libraries/libGLESv2.dylib");
        unsigned long angle_egl = find_image_base("Libraries/libEGL.dylib");
        unsigned long native_egl = find_image_base("/usr/lib/native/libEGL.dylib");
        unsigned long glfw = find_image_base("OpenGL.framework");
        unsigned long fw = (unsigned long)framework_base;
        unsigned long region = 0;   /* 1=ANGLE libGLESv2, 2=ANGLE libEGL,
                                       3=Darling native libEGL, 4=OpenGL.framework,
                                       5=Electron Framework, 0=other */
        if (angle_gles && fn >= angle_gles && fn < angle_gles + 0x1000000UL) region = 1;
        else if (angle_egl && fn >= angle_egl && fn < angle_egl + 0x1000000UL) region = 2;
        else if (native_egl && fn >= native_egl && fn < native_egl + 0x1000000UL) region = 3;
        else if (glfw && fn >= glfw && fn < glfw + 0x10000000UL) region = 4;
        else if (fw && fn >= fw && fn < fw + 0x10000000UL) region = 5;
        write_marker_value("EGL_MC_REAL_FN", fn);
        write_marker_value("EGL_MC_FN_REGION", region);
        write_marker_value("EGL_MC_BASE_ANGLE", angle_egl);
        write_marker_value("EGL_MC_BASE_NATIVE", native_egl);
    }
    /* ANGLE's per-thread GL current context right after eglMakeCurrent returns.
     * (Calling libEGL's eglGetCurrentContext from here crashed the GPU process,
     * so only the internal getter is probed.) */
    {
        unsigned long gles = find_image_base("libGLESv2.dylib");
        if (gles) {
            void *angle_ctx = ((void *(*)(void))(gles + 0x416c0))();
            write_marker_value("EGL_MC_ANGLE_CTX", (unsigned long)angle_ctx);
        }
    }
}

/* Installs a hook on a runtime address (used for libGLESv2 internals that are
 * only known once the dylib is loaded). */
static int install_late_hook(struct hook *h, unsigned long target, unsigned long dest) {
    unsigned i;
    if (!target) return 0;
    h->target = (unsigned char *)target;
    h->destination = dest;
    for (i = 0; i < 12; ++i) h->saved[i] = h->target[i];
    patch(h, 1);
    return 1;
}

/* gl::SetCurrentContext(Context*) at libGLESv2+0x416f0: stores into the GL-level
 * thread-local (descriptor 0x92e9d8). Logging the argument shows whether
 * eglMakeCurrent ever hands it a non-null context. */
static void traced_set_current_context(void *ctx) {
    while (__sync_lock_test_and_set(&set_current_context_lock, 1)) { }
    patch(&set_current_context_hook, 0);
    write_marker_value("SET_CURRENT_CONTEXT", (unsigned long)ctx);
    write_marker_value("SCC_THREAD", pthread_self());
    ((void (*)(void *))set_current_context_hook.target)(ctx);
    patch(&set_current_context_hook, 1);
    __sync_lock_release(&set_current_context_lock);
}

/* Helper at libGLESv2+0x2e4c0: takes a pointer to a context, sets it on the
 * thread object and tail-calls SetCurrentContext. */
static void traced_set_ctx_helper(void *p) {
    while (__sync_lock_test_and_set(&set_ctx_helper_lock, 1)) { }
    patch(&set_ctx_helper_hook, 0);
    write_marker_value("SET_CTX_HELPER", (unsigned long)(p ? *(void **)p : 0));
    write_marker_value("SCH_THREAD", pthread_self());
    ((void (*)(void *))set_ctx_helper_hook.target)(p);
    patch(&set_ctx_helper_hook, 1);
    __sync_lock_release(&set_ctx_helper_lock);
}

/* egl::Thread::makeCurrent(Display*, Surface* draw, Surface* read, Context*)
 * at libGLESv2+0x9e10: the function EGL_MakeCurrent calls after the display's
 * makeCurrent, and which ends by calling 0x2e4c0 -> SetCurrentContext. */
static unsigned int traced_thread_make_current(void *self, void *display, void *draw,
                                               void *read, void *context) {
    unsigned int result;
    while (__sync_lock_test_and_set(&thread_make_current_lock, 1)) { }
    patch(&thread_make_current_hook, 0);
    write_marker_value("THREAD_MAKE_CURRENT", (unsigned long)self);
    write_marker_value("TMC_CONTEXT", (unsigned long)context);
    write_marker_value("TMC_THREAD", pthread_self());
    result = ((unsigned int (*)(void *, void *, void *, void *, void *))
                  thread_make_current_hook.target)(self, display, draw, read, context);
    write_marker_value("TMC_RESULT", result);
    patch(&thread_make_current_hook, 1);
    __sync_lock_release(&thread_make_current_lock);
    return result;
}

static unsigned int traced_egl_make_current_base(void *self, void *display, void *draw,
                                                 void *read, void *context) {
    unsigned int result;
    while (__sync_lock_test_and_set(&egl_mc_base_lock, 1)) { }
    patch(&egl_make_current_base_hook, 0);
    if (!set_ctx_installed) {
        unsigned long gles = find_image_base("libGLESv2.dylib");
        unsigned long eglb = find_image_base("libEGL.dylib");
        if (gles) {
            set_ctx_installed = 1;
            dump_gl_images();
            write_marker_value("SCC_HOOK_SETCURRENT", gles + 0x416f0);
            write_marker_value("SCC_HOOK_HELPER", gles + 0x2e4c0);
            write_marker_value("SCC_HOOK_THREADMC", gles + 0x9e10);
            if (eglb)
                write_marker_value("SCC_LIBEGL_DISPATCH",
                                   *(unsigned long *)(eglb + 0x30d20));
            install_late_hook(&set_current_context_hook, gles + 0x416f0,
                              (unsigned long)&traced_set_current_context);
            install_late_hook(&set_ctx_helper_hook, gles + 0x2e4c0,
                              (unsigned long)&traced_set_ctx_helper);
            install_late_hook(&thread_make_current_hook, gles + 0x9e10,
                              (unsigned long)&traced_thread_make_current);
        }
    }
    result = ((unsigned int (*)(void *, void *, void *, void *, void *))
                  egl_make_current_base_hook.target)(self, display, draw, read, context);
    egl_make_current_log("EGL_MAKE_CURRENT_BASE", self, display, draw, read, context, result);
    patch(&egl_make_current_base_hook, 1);
    __sync_lock_release(&egl_mc_base_lock);
    return result;
}

static unsigned int traced_egl_make_current_trace(void *self, void *display, void *draw,
                                                  void *read, void *context) {
    unsigned int result;
    while (__sync_lock_test_and_set(&egl_mc_trace_lock, 1)) { }
    patch(&egl_make_current_trace_hook, 0);
    if (!set_ctx_installed) {
        unsigned long gles = find_image_base("libGLESv2.dylib");
        unsigned long eglb = find_image_base("libEGL.dylib");
        if (gles) {
            set_ctx_installed = 1;
            dump_gl_images();
            write_marker_value("SCC_HOOK_SETCURRENT", gles + 0x416f0);
            write_marker_value("SCC_HOOK_HELPER", gles + 0x2e4c0);
            write_marker_value("SCC_HOOK_THREADMC", gles + 0x9e10);
            if (eglb)
                write_marker_value("SCC_LIBEGL_DISPATCH",
                                   *(unsigned long *)(eglb + 0x30d20));
            install_late_hook(&set_current_context_hook, gles + 0x416f0,
                              (unsigned long)&traced_set_current_context);
            install_late_hook(&set_ctx_helper_hook, gles + 0x2e4c0,
                              (unsigned long)&traced_set_ctx_helper);
            install_late_hook(&thread_make_current_hook, gles + 0x9e10,
                              (unsigned long)&traced_thread_make_current);
        }
    }
    result = ((unsigned int (*)(void *, void *, void *, void *, void *))
                  egl_make_current_trace_hook.target)(self, display, draw, read, context);
    egl_make_current_log("EGL_MAKE_CURRENT_TRACE", self, display, draw, read, context, result);
    patch(&egl_make_current_trace_hook, 1);
    __sync_lock_release(&egl_mc_trace_lock);
    return result;
}

__attribute__((constructor)) static void install_hook(void) {
    unsigned i, j;
    if (getenv("M57_NO_HOOKS")) {
        printf("M57IPCZ disabled (M57_NO_HOOKS) pid=%d\n", getpid());
        fflush(0);
        return;
    }
    printf("M57IPCZ loaded pid=%d images=%u\n", getpid(), _dyld_image_count());
    fflush(0);
    status(1, _dyld_image_count());
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            framework_base = (unsigned char *)_dyld_get_image_header(i);
            transmit_hook.target = framework_base + TRANSMIT_VA;
            transmit_hook.destination = (unsigned long)&traced_transmit;
            accept_hook.target = framework_base + ACCEPT_EVENT_VA;
            accept_hook.destination = (unsigned long)&traced_accept_event;
            internal_hook.target = framework_base + ACCEPT_INTERNAL_VA;
            internal_hook.destination = (unsigned long)&traced_accept_internal;
            user_message_hook.target = framework_base + ON_USER_MESSAGE_VA;
            user_message_hook.destination = (unsigned long)&traced_user_message;
            get_port_hook.target = framework_base + GET_PORT_VA;
            get_port_hook.destination = (unsigned long)&traced_get_port;
            accept_message_hook.target = framework_base + ACCEPT_MESSAGE_VA;
            accept_message_hook.destination = (unsigned long)&traced_accept_message;
            forward_proxy_hook.target = framework_base + FORWARD_PROXY_VA;
            forward_proxy_hook.destination = (unsigned long)&traced_forward_proxy;
            port_status_hook.target = framework_base + PORT_STATUS_CHANGED_VA;
            port_status_hook.destination = (unsigned long)&traced_port_status;
            pipe_observer_hook.target = framework_base + PIPE_OBSERVER_VA;
            pipe_observer_hook.destination = (unsigned long)&traced_pipe_observer;
            watcher_notify_hook.target = framework_base + WATCHER_NOTIFY_VA;
            watcher_notify_hook.destination = (unsigned long)&traced_watcher_notify;
            dispatcher_notify_hook.target = framework_base + DISPATCHER_NOTIFY_VA;
            dispatcher_notify_hook.destination = (unsigned long)&traced_dispatcher_notify;
            watch_notify_hook.target = framework_base + WATCH_NOTIFY_VA;
            watch_notify_hook.destination = (unsigned long)&traced_watch_notify;
            watch_callback_hook.target = framework_base + WATCH_CALLBACK_VA;
            watch_callback_hook.destination = (unsigned long)&traced_watch_callback;
            watcher_add_hook.target = framework_base + WATCHER_ADD_VA;
            watcher_add_hook.destination = (unsigned long)&traced_watcher_add;
            watcher_remove_hook.target = framework_base + WATCHER_REMOVE_VA;
            watcher_remove_hook.destination = (unsigned long)&traced_watcher_remove;
            pipe_ctor_hook.target = framework_base + PIPE_DISPATCHER_CTOR_VA;
            pipe_ctor_hook.destination = (unsigned long)&traced_pipe_ctor;
            gpu_client_add_hook.target = framework_base + GPU_CLIENT_ADD_VA;
            gpu_client_add_hook.destination = (unsigned long)&traced_gpu_client_add;
            gpu_receiver_add_hook.target = framework_base + GPU_RECEIVER_ADD_VA;
            gpu_receiver_add_hook.destination = (unsigned long)&traced_gpu_receiver_add;
            gpu_receiver_ctor_hook.target = framework_base + GPU_RECEIVER_CTOR_VA;
            gpu_receiver_ctor_hook.destination = (unsigned long)&traced_gpu_receiver_ctor;
            gpu_stub_accept_hook.target = framework_base + GPU_STUB_ACCEPT_VA;
            gpu_stub_accept_hook.destination = (unsigned long)&traced_gpu_stub_accept;
            core_add_hook.target = framework_base + CORE_ADD_DISPATCHER_VA;
            core_add_hook.destination = (unsigned long)&traced_core_add;
            pipe_read_hook.target = framework_base + PIPE_READ_VA;
            pipe_read_hook.destination = (unsigned long)&traced_pipe_read;
            pipe_add_watcher_hook.target = framework_base + PIPE_ADD_WATCHER_VA;
            pipe_add_watcher_hook.destination = (unsigned long)&traced_pipe_add_watcher;
            node_ctor_hook.target = framework_base + NODE_CTOR_VA;
            node_ctor_hook.destination = (unsigned long)&traced_node_ctor;
            add_peer_hook.target = framework_base + ADD_PEER_VA;
            add_peer_hook.destination = (unsigned long)&traced_add_peer;
            accept_port_hook.target = framework_base + ACCEPT_PORT_VA;
            accept_port_hook.destination = (unsigned long)&traced_accept_port;
            on_accept_peer_hook.target = framework_base + ON_ACCEPT_PEER_VA;
            on_accept_peer_hook.destination = (unsigned long)&traced_on_accept_peer;
            on_request_port_merge_hook.target = framework_base + ON_REQUEST_PORT_MERGE_VA;
            on_request_port_merge_hook.destination = (unsigned long)&traced_on_request_port_merge;
            gpu_client_ctor_hook.target = framework_base + GPU_CLIENT_CTOR_VA;
            gpu_client_ctor_hook.destination = (unsigned long)&traced_gpu_client_ctor;
            gpu_client_establish_hook.target = framework_base + GPU_CLIENT_ESTABLISH_VA;
            gpu_client_establish_hook.destination = (unsigned long)&traced_gpu_client_establish;
            gpu_host_establish_hook.target = framework_base + GPU_HOST_ESTABLISH_VA;
            gpu_host_establish_hook.destination = (unsigned long)&traced_gpu_host_establish;
            gpu_host_onestab_hook.target = framework_base + GPU_HOST_ON_ESTABLISHED_VA;
            gpu_host_onestab_hook.destination = (unsigned long)&traced_gpu_host_onestab;
            browser_delegate_ensure_hook.target = framework_base + BROWSER_DELEGATE_ENSURE_VA;
            browser_delegate_ensure_hook.destination = (unsigned long)&traced_browser_delegate_ensure;
            rp_add_ui_gpu_hook.target = framework_base + RP_ADD_UI_GPU_VA;
            rp_add_ui_gpu_hook.destination = (unsigned long)&traced_rp_add_ui_gpu;
            binder_add_gpu_hook.target = framework_base + BINDER_ADD_GPU_VA;
            binder_add_gpu_hook.destination = (unsigned long)&traced_binder_add_gpu;
            try_bind_interface_hook.target = framework_base + TRY_BIND_INTERFACE_VA;
            try_bind_interface_hook.destination = (unsigned long)&traced_try_bind_interface;
            gpu_proxy_establish_hook.target = framework_base + GPU_PROXY_ESTABLISH_VA;
            gpu_proxy_establish_hook.destination = (unsigned long)&traced_gpu_proxy_establish;
            registry_bind_hook.target = framework_base + REGISTRY_BIND_VA;
            registry_bind_hook.destination = (unsigned long)&traced_registry_bind;
            callback_binder_gpu_hook.target = framework_base + CALLBACK_BINDER_GPU_VA;
            callback_binder_gpu_hook.destination = (unsigned long)&traced_callback_binder_gpu;
            run_callback_hook.target = framework_base + RUN_CALLBACK_VA;
            run_callback_hook.destination = (unsigned long)&traced_run_callback;
            post_task_hook.target = framework_base + POST_TASK_VA;
            post_task_hook.destination = (unsigned long)&traced_post_task;
            is_shm_acceptable_hook.target = framework_base + IS_SHM_ACCEPTABLE_VA;
            is_shm_acceptable_hook.destination = (unsigned long)&traced_is_shm_acceptable;
            wsr_create_hook.target = framework_base + WSR_CREATE_VA;
            wsr_create_hook.destination = (unsigned long)&traced_wsr_create;
            wsr_map_hook.target = framework_base + WSR_MAP_VA;
            wsr_map_hook.destination = (unsigned long)&traced_wsr_map;
            persist_allocate_hook.target = framework_base + PERSIST_ALLOCATE_VA;
            persist_allocate_hook.destination = (unsigned long)&traced_persist_allocate;
            persist_ctor_hook.target = framework_base + PERSIST_CTOR_VA;
            persist_ctor_hook.destination = (unsigned long)&traced_persist_ctor;
            display_update_layer_tree_hook.target = framework_base + DISPLAY_UPDATE_LAYER_TREE_VA;
            display_update_layer_tree_hook.destination = (unsigned long)&traced_display_update_layer_tree;
            display_got_layer_frame_hook.target = framework_base + DISPLAY_GOT_LAYER_FRAME_VA;
            display_got_layer_frame_hook.destination = (unsigned long)&traced_display_got_layer_frame;
            compositor_set_visible_hook.target = framework_base + COMPOSITOR_SET_VISIBLE_VA;
            compositor_set_visible_hook.destination = (unsigned long)&traced_compositor_set_visible;
            compositor_set_frame_sink_hook.target = framework_base + COMPOSITOR_SET_FRAME_SINK_VA;
            compositor_set_frame_sink_hook.destination = (unsigned long)&traced_compositor_set_frame_sink;
            display_draw_and_swap_hook.target = framework_base + DISPLAY_DRAW_AND_SWAP_VA;
            display_draw_and_swap_hook.destination = (unsigned long)&traced_display_draw_and_swap;
            display_scheduler_on_begin_frame_hook.target = framework_base + DISPLAY_SCHEDULER_ON_BEGIN_FRAME_VA;
            display_scheduler_on_begin_frame_hook.destination = (unsigned long)&traced_display_scheduler_on_begin_frame;
            native_widget_on_visibility_hook.target = framework_base + NATIVE_WIDGET_ON_VISIBILITY_VA;
            native_widget_on_visibility_hook.destination = (unsigned long)&traced_native_widget_on_visibility;
            native_widget_mac_show_hook.target = framework_base + NATIVE_WIDGET_MAC_SHOW_VA;
            native_widget_mac_show_hook.destination = (unsigned long)&traced_native_widget_mac_show;
            rwhv_show_with_visibility_hook.target = framework_base + RWHV_SHOW_WITH_VISIBILITY_VA;
            rwhv_show_with_visibility_hook.destination = (unsigned long)&traced_rwhv_show_with_visibility;
            recyclable_suspend_hook.target = framework_base + RECYCLABLE_SUSPEND_VA;
            recyclable_suspend_hook.destination = (unsigned long)&traced_recyclable_suspend;
            recyclable_unsuspend_hook.target = framework_base + RECYCLABLE_UNSUSPEND_VA;
            recyclable_unsuspend_hook.destination = (unsigned long)&traced_recyclable_unsuspend;
            viz_display_set_visible_hook.target = framework_base + VIZ_DISPLAY_SET_VISIBLE_VA;
            viz_display_set_visible_hook.destination = (unsigned long)&traced_viz_display_set_visible;
            viz_display_scheduler_set_visible_hook.target = framework_base + VIZ_DISPLAY_SCHEDULER_SET_VISIBLE_VA;
            viz_display_scheduler_set_visible_hook.destination = (unsigned long)&traced_viz_display_scheduler_set_visible;
            viz_root_set_display_visible_hook.target = framework_base + VIZ_ROOT_SET_DISPLAY_VISIBLE_VA;
            viz_root_set_display_visible_hook.destination = (unsigned long)&traced_viz_root_set_display_visible;
            electron_occlusion_hook.target = framework_base + ELECTRON_WINDOW_OCCLUSION_VA;
            electron_occlusion_hook.destination = (unsigned long)&traced_electron_occlusion;
            webcontents_visibility_hook.target = framework_base + WEBCONTENTS_VIEW_VISIBILITY_VA;
            webcontents_visibility_hook.destination = (unsigned long)&traced_webcontents_visibility;
            native_widget_set_visibility_hook.target = framework_base + NATIVE_WIDGET_SET_VISIBILITY_VA;
            native_widget_set_visibility_hook.destination = (unsigned long)&traced_native_widget_set_visibility;
            nativewindowmac_show_hook.target = framework_base + NATIVEWINDOWMAC_SHOW_VA;
            nativewindowmac_show_hook.destination = (unsigned long)&traced_nativewindowmac_show;
            nativewindowmac_show_inactive_hook.target = framework_base + NATIVEWINDOWMAC_SHOW_INACTIVE_VA;
            nativewindowmac_show_inactive_hook.destination = (unsigned long)&traced_nativewindowmac_show_inactive;
            nativewidgetmac_nswindow_order_front_hook.target = framework_base + NATIVEWIDGETMAC_NSWINDOW_ORDER_FRONT_VA;
            nativewidgetmac_nswindow_order_front_hook.destination = (unsigned long)&traced_nativewidgetmac_nswindow_order_front;
            nativewindowmac_ctor_hook.target = framework_base + NATIVEWINDOWMAC_CTOR_VA;
            nativewindowmac_ctor_hook.destination = (unsigned long)&traced_nativewindowmac_ctor;
            browserwindow_ctor_hook.target = framework_base + BROWSERWINDOW_CTOR_VA;
            browserwindow_ctor_hook.destination = (unsigned long)&traced_browserwindow_ctor;
            basewindow_ctor_hook.target = framework_base + BASEWINDOW_CTOR_VA;
            basewindow_ctor_hook.destination = (unsigned long)&traced_basewindow_ctor;
            nativewindow_create_hook.target = framework_base + NATIVEWINDOW_CREATE_VA;
            nativewindow_create_hook.destination = (unsigned long)&traced_nativewindow_create;
            webcontents_ctor_hook.target = framework_base + WEBCONTENTS_CTOR_VA;
            webcontents_ctor_hook.destination = (unsigned long)&traced_webcontents_ctor;
            webcontents_from_prefs_hook.target = framework_base + WEBCONTENTS_FROM_PREFS_VA;
            webcontents_from_prefs_hook.destination = (unsigned long)&traced_webcontents_from_prefs;
            gin_get_bool_hook.target = framework_base + GIN_GET_BOOL_VA;
            gin_get_bool_hook.destination = (unsigned long)&traced_gin_get_bool;
            gin_set_bool_hook.target = framework_base + GIN_SET_BOOL_VA;
            gin_set_bool_hook.destination = (unsigned long)&traced_gin_set_bool;
            gin_get_string_hook.target = framework_base + GIN_GET_STRING_VA;
            gin_get_string_hook.destination = (unsigned long)&traced_gin_get_string;
            v8_private_forapi_hook.target = framework_base + V8_PRIVATE_FORAPI_VA;
            v8_private_forapi_hook.destination = (unsigned long)&traced_v8_private_forapi;
            v8_set_private_hook.target = framework_base + V8_SET_PRIVATE_VA;
            v8_set_private_hook.destination = (unsigned long)&traced_v8_set_private;
            webcontents_set_owner_hook.target = framework_base + WEBCONTENTS_SET_OWNER_VA;
            webcontents_set_owner_hook.destination = (unsigned long)&traced_webcontents_set_owner;
            basewindow_set_contentview_hook.target = framework_base + BASEWINDOW_SET_CONTENTVIEW_VA;
            basewindow_set_contentview_hook.destination = (unsigned long)&traced_basewindow_set_contentview;
            browserwindow_override_contentview_hook.target = framework_base + BROWSERWINDOW_OVERRIDE_CONTENTVIEW_VA;
            browserwindow_override_contentview_hook.destination = (unsigned long)&traced_browserwindow_override_contentview;
            nativewindow_initfromoptions_hook.target = framework_base + NATIVEWINDOW_INITFROMOPTIONS_VA;
            nativewindow_initfromoptions_hook.destination = (unsigned long)&traced_nativewindow_initfromoptions;
            /* Left unarmed by default, like accept_port/on_accept_peer below:
             * patching this hot allocator during boot perturbs startup (M57bc
             * — the run truncated at 14 records with no GPU phase), and the
             * pre-gpu_init corruption is not guest-traceable (M57bk/M57bl
             * moved that to host-side tracing). Re-enable manually for a
             * targeted run only. */
            gl_ctx_init_hook.target = framework_base + GL_CTX_INIT_VA;
            gl_ctx_init_hook.destination = (unsigned long)&traced_gl_ctx_init;
            egl_ext_settings_hook.target = framework_base + EGL_EXT_SETTINGS_VA;
            egl_ext_settings_hook.destination = (unsigned long)&traced_egl_ext_settings;
            gfx_has_extension_hook.target = framework_base + GFX_HAS_EXTENSION_VA;
            gfx_has_extension_hook.destination = (unsigned long)&traced_gfx_has_extension;
            egl_create_context_base_hook.target = framework_base + EGL_CREATE_CONTEXT_BASE_VA;
            egl_create_context_base_hook.destination = (unsigned long)&traced_egl_create_context_base;
            egl_create_context_trace_hook.target = framework_base + EGL_CREATE_CONTEXT_TRACE_VA;
            egl_create_context_trace_hook.destination = (unsigned long)&traced_egl_create_context_trace;
            gla_getintegerv_base_hook.target = framework_base + GLA_GETINTEGERV_BASE_VA;
            gla_getintegerv_base_hook.destination = (unsigned long)&traced_gla_getintegerv_base;
            gla_getintegerv_nocontext_hook.target = framework_base + GLA_GETINTEGERV_NOCONTEXT_VA;
            gla_getintegerv_nocontext_hook.destination = (unsigned long)&traced_gla_getintegerv_nocontext;
            gla_getintegerv_stub_hook.target = framework_base + GLA_GETINTEGERV_STUB_VA;
            gla_getintegerv_stub_hook.destination = (unsigned long)&traced_gla_getintegerv_stub;
            egl_make_current_base_hook.target = framework_base + EGL_MAKE_CURRENT_BASE_VA;
            egl_make_current_base_hook.destination = (unsigned long)&traced_egl_make_current_base;
            egl_make_current_trace_hook.target = framework_base + EGL_MAKE_CURRENT_TRACE_VA;
            egl_make_current_trace_hook.destination = (unsigned long)&traced_egl_make_current_trace;
            post_delayed_hook.target = framework_base + POST_DELAYED_TASK_VA;
            post_delayed_hook.destination = (unsigned long)&traced_post_delayed;
            thread_schedule_hook.target = framework_base + THREAD_CTRL_SCHEDULE_VA;
            thread_schedule_hook.destination = (unsigned long)&traced_thread_schedule;
            pump_default_schedule_hook.target = framework_base + PUMP_DEFAULT_SCHEDULE_VA;
            pump_default_schedule_hook.destination = (unsigned long)&traced_pump_default_schedule;
            pump_cf_schedule_hook.target = framework_base + PUMP_CF_SCHEDULE_VA;
            pump_cf_schedule_hook.destination = (unsigned long)&traced_pump_cf_schedule;
            for (j = 0; j < 12; ++j) {
                transmit_hook.saved[j] = transmit_hook.target[j];
                accept_hook.saved[j] = accept_hook.target[j];
                internal_hook.saved[j] = internal_hook.target[j];
                user_message_hook.saved[j] = user_message_hook.target[j];
                get_port_hook.saved[j] = get_port_hook.target[j];
                accept_message_hook.saved[j] = accept_message_hook.target[j];
                forward_proxy_hook.saved[j] = forward_proxy_hook.target[j];
                port_status_hook.saved[j] = port_status_hook.target[j];
                pipe_observer_hook.saved[j] = pipe_observer_hook.target[j];
                watcher_notify_hook.saved[j] = watcher_notify_hook.target[j];
                dispatcher_notify_hook.saved[j] = dispatcher_notify_hook.target[j];
                watch_notify_hook.saved[j] = watch_notify_hook.target[j];
                watch_callback_hook.saved[j] = watch_callback_hook.target[j];
                watcher_add_hook.saved[j] = watcher_add_hook.target[j];
                watcher_remove_hook.saved[j] = watcher_remove_hook.target[j];
                pipe_ctor_hook.saved[j] = pipe_ctor_hook.target[j];
                gpu_client_add_hook.saved[j] = gpu_client_add_hook.target[j];
                gpu_receiver_add_hook.saved[j] = gpu_receiver_add_hook.target[j];
                gpu_receiver_ctor_hook.saved[j] = gpu_receiver_ctor_hook.target[j];
                gpu_stub_accept_hook.saved[j] = gpu_stub_accept_hook.target[j];
                core_add_hook.saved[j] = core_add_hook.target[j];
                pipe_read_hook.saved[j] = pipe_read_hook.target[j];
                pipe_add_watcher_hook.saved[j] = pipe_add_watcher_hook.target[j];
                node_ctor_hook.saved[j] = node_ctor_hook.target[j];
                add_peer_hook.saved[j] = add_peer_hook.target[j];
                accept_port_hook.saved[j] = accept_port_hook.target[j];
                on_accept_peer_hook.saved[j] = on_accept_peer_hook.target[j];
                on_request_port_merge_hook.saved[j] = on_request_port_merge_hook.target[j];
                gpu_client_ctor_hook.saved[j] = gpu_client_ctor_hook.target[j];
                gpu_client_establish_hook.saved[j] = gpu_client_establish_hook.target[j];
                gpu_host_establish_hook.saved[j] = gpu_host_establish_hook.target[j];
                gpu_host_onestab_hook.saved[j] = gpu_host_onestab_hook.target[j];
                browser_delegate_ensure_hook.saved[j] = browser_delegate_ensure_hook.target[j];
                rp_add_ui_gpu_hook.saved[j] = rp_add_ui_gpu_hook.target[j];
                binder_add_gpu_hook.saved[j] = binder_add_gpu_hook.target[j];
                try_bind_interface_hook.saved[j] = try_bind_interface_hook.target[j];
                gpu_proxy_establish_hook.saved[j] = gpu_proxy_establish_hook.target[j];
                registry_bind_hook.saved[j] = registry_bind_hook.target[j];
                callback_binder_gpu_hook.saved[j] = callback_binder_gpu_hook.target[j];
                run_callback_hook.saved[j] = run_callback_hook.target[j];
                post_task_hook.saved[j] = post_task_hook.target[j];
                is_shm_acceptable_hook.saved[j] = is_shm_acceptable_hook.target[j];
                wsr_create_hook.saved[j] = wsr_create_hook.target[j];
                wsr_map_hook.saved[j] = wsr_map_hook.target[j];
                persist_allocate_hook.saved[j] = persist_allocate_hook.target[j];
                persist_ctor_hook.saved[j] = persist_ctor_hook.target[j];
                display_update_layer_tree_hook.saved[j] = display_update_layer_tree_hook.target[j];
                display_got_layer_frame_hook.saved[j] = display_got_layer_frame_hook.target[j];
                compositor_set_visible_hook.saved[j] = compositor_set_visible_hook.target[j];
                compositor_set_frame_sink_hook.saved[j] = compositor_set_frame_sink_hook.target[j];
                display_draw_and_swap_hook.saved[j] = display_draw_and_swap_hook.target[j];
                display_scheduler_on_begin_frame_hook.saved[j] = display_scheduler_on_begin_frame_hook.target[j];
                native_widget_on_visibility_hook.saved[j] = native_widget_on_visibility_hook.target[j];
                native_widget_mac_show_hook.saved[j] = native_widget_mac_show_hook.target[j];
                rwhv_show_with_visibility_hook.saved[j] = rwhv_show_with_visibility_hook.target[j];
                recyclable_suspend_hook.saved[j] = recyclable_suspend_hook.target[j];
                recyclable_unsuspend_hook.saved[j] = recyclable_unsuspend_hook.target[j];
                viz_display_set_visible_hook.saved[j] = viz_display_set_visible_hook.target[j];
                viz_display_scheduler_set_visible_hook.saved[j] = viz_display_scheduler_set_visible_hook.target[j];
                viz_root_set_display_visible_hook.saved[j] = viz_root_set_display_visible_hook.target[j];
                electron_occlusion_hook.saved[j] = electron_occlusion_hook.target[j];
                webcontents_visibility_hook.saved[j] = webcontents_visibility_hook.target[j];
                native_widget_set_visibility_hook.saved[j] = native_widget_set_visibility_hook.target[j];
                nativewindowmac_show_hook.saved[j] = nativewindowmac_show_hook.target[j];
                nativewindowmac_show_inactive_hook.saved[j] = nativewindowmac_show_inactive_hook.target[j];
                nativewidgetmac_nswindow_order_front_hook.saved[j] = nativewidgetmac_nswindow_order_front_hook.target[j];
                nativewindowmac_ctor_hook.saved[j] = nativewindowmac_ctor_hook.target[j];
                browserwindow_ctor_hook.saved[j] = browserwindow_ctor_hook.target[j];
                basewindow_ctor_hook.saved[j] = basewindow_ctor_hook.target[j];
                nativewindow_create_hook.saved[j] = nativewindow_create_hook.target[j];
                webcontents_ctor_hook.saved[j] = webcontents_ctor_hook.target[j];
                webcontents_from_prefs_hook.saved[j] = webcontents_from_prefs_hook.target[j];
                gin_get_bool_hook.saved[j] = gin_get_bool_hook.target[j];
                gin_set_bool_hook.saved[j] = gin_set_bool_hook.target[j];
                gin_get_string_hook.saved[j] = gin_get_string_hook.target[j];
                v8_private_forapi_hook.saved[j] = v8_private_forapi_hook.target[j];
                v8_set_private_hook.saved[j] = v8_set_private_hook.target[j];
                webcontents_set_owner_hook.saved[j] = webcontents_set_owner_hook.target[j];
                basewindow_set_contentview_hook.saved[j] = basewindow_set_contentview_hook.target[j];
                browserwindow_override_contentview_hook.saved[j] = browserwindow_override_contentview_hook.target[j];
                nativewindow_initfromoptions_hook.saved[j] = nativewindow_initfromoptions_hook.target[j];
                gl_ctx_init_hook.saved[j] = gl_ctx_init_hook.target[j];
                egl_ext_settings_hook.saved[j] = egl_ext_settings_hook.target[j];
                gfx_has_extension_hook.saved[j] = gfx_has_extension_hook.target[j];
                egl_create_context_base_hook.saved[j] = egl_create_context_base_hook.target[j];
                egl_create_context_trace_hook.saved[j] = egl_create_context_trace_hook.target[j];
                gla_getintegerv_base_hook.saved[j] = gla_getintegerv_base_hook.target[j];
                gla_getintegerv_nocontext_hook.saved[j] = gla_getintegerv_nocontext_hook.target[j];
                gla_getintegerv_stub_hook.saved[j] = gla_getintegerv_stub_hook.target[j];
                egl_make_current_base_hook.saved[j] = egl_make_current_base_hook.target[j];
                egl_make_current_trace_hook.saved[j] = egl_make_current_trace_hook.target[j];
                post_delayed_hook.saved[j] = post_delayed_hook.target[j];
                thread_schedule_hook.saved[j] = thread_schedule_hook.target[j];
                pump_default_schedule_hook.saved[j] = pump_default_schedule_hook.target[j];
                pump_cf_schedule_hook.saved[j] = pump_cf_schedule_hook.target[j];
            }
            patch(&transmit_hook, 1);
            /* Persistent, self-filtering: only emits after tracked_watcher_set
             * is known, so it can catch an async connector bind that the
             * request-scoped window closes before. */
            patch(&watcher_add_hook, 1);
            /* Very low frequency; identify our own node and our peers. */
            patch(&node_ctor_hook, 1);
            patch(&add_peer_hook, 1);
            /* accept_port fires on the hot handle-transfer path; arming it
             * every run truncated startup (run 4/5, 86/59 records, no GPU
             * phase). The destination port's locality is already proven by the
             * local GetPort success in the request-scoped trace, so leave it
             * off by default. */
            /* patch(&accept_port_hook, 1); */
            /* Kept out of the persistent set: these two also perturbed startup
             * in run 4. Re-arm manually if a control-handshake trace is
             * needed. */
            /* patch(&on_accept_peer_hook, 1); */
            /* patch(&on_request_port_merge_hook, 1); */
            /* Browser-side Gpu host chain: low frequency, safe to persist. */
            patch(&gpu_client_add_hook, 1);
            patch(&gpu_client_ctor_hook, 1);
            patch(&gpu_client_establish_hook, 1);
            patch(&gpu_host_establish_hook, 1);
            patch(&gpu_host_onestab_hook, 1);
            patch(&browser_delegate_ensure_hook, 1);
            /* Internal points: AddImpl / GpuStub, in case GpuClient::Add was
             * inlined away by LTO. */
            patch(&gpu_receiver_add_hook, 1);
            patch(&gpu_stub_accept_hook, 1);
            /* Binder registration + dispatch + renderer proxy. Signatures now
             * preserve the hidden third runner arg. */
            patch(&rp_add_ui_gpu_hook, 1);
            patch(&binder_add_gpu_hook, 1);
            patch(&try_bind_interface_hook, 1);
            patch(&gpu_proxy_establish_hook, 1);
            patch(&is_shm_acceptable_hook, 1);
            patch(&wsr_create_hook, 1);
            patch(&wsr_map_hook, 1);
            /* Both are opt-in: the allocator path perturbs GPU boot (M57bc). */
            /* patch(&persist_ctor_hook, 1); */
            /* patch(&persist_allocate_hook, 1); */
            /* Present-path probes (M57bp); low frequency, safe at load. */
            patch(&display_update_layer_tree_hook, 1);
            patch(&display_got_layer_frame_hook, 1);
            patch(&compositor_set_visible_hook, 1);
            patch(&compositor_set_frame_sink_hook, 1);
            patch(&display_draw_and_swap_hook, 1);
            patch(&display_scheduler_on_begin_frame_hook, 1);
            patch(&native_widget_on_visibility_hook, 1);
            patch(&native_widget_mac_show_hook, 1);
            patch(&rwhv_show_with_visibility_hook, 1);
            patch(&recyclable_suspend_hook, 1);
            patch(&recyclable_unsuspend_hook, 1);
            patch(&viz_display_set_visible_hook, 1);
            patch(&viz_display_scheduler_set_visible_hook, 1);
            patch(&viz_root_set_display_visible_hook, 1);
            patch(&electron_occlusion_hook, 1);
            patch(&webcontents_visibility_hook, 1);
            patch(&native_widget_set_visibility_hook, 1);
            patch(&nativewindowmac_show_hook, 1);
            patch(&nativewindowmac_show_inactive_hook, 1);
            patch(&nativewidgetmac_nswindow_order_front_hook, 1);
            patch(&nativewindowmac_ctor_hook, 1);
            patch(&browserwindow_ctor_hook, 1);
            patch(&basewindow_ctor_hook, 1);
            patch(&nativewindow_create_hook, 1);
            patch(&webcontents_ctor_hook, 1);
            patch(&webcontents_from_prefs_hook, 1);
            patch(&gin_get_bool_hook, 1);
            patch(&gin_set_bool_hook, 1);
            patch(&gin_get_string_hook, 1);
            patch(&v8_private_forapi_hook, 1);
            patch(&v8_set_private_hook, 1);
            patch(&webcontents_set_owner_hook, 1);
            patch(&basewindow_set_contentview_hook, 1);
            patch(&browserwindow_override_contentview_hook, 1);
            patch(&nativewindow_initfromoptions_hook, 1);
            /* Chromium-side EGL/ANGLE extension divergence (M57s/M57t): both
             * are low frequency (context/display init), so safe at load.
             * gfx_has_extension is NOT armed here; it is armed only for the
             * duration of egl_ext_settings to keep the general-purpose helper
             * out of the boot path. */
            patch(&gl_ctx_init_hook, 1);
            patch(&egl_ext_settings_hook, 1);
            /* Only one of the two wrappers is the vtable target; arming both is
             * harmless and low frequency (context creation only). */
            patch(&egl_create_context_base_hook, 1);
            patch(&egl_create_context_trace_hook, 1);
            /* GL_MAX_VERTEX_ATTRIBS query (M57bn); filtered to that pname. */
            patch(&gla_getintegerv_base_hook, 1);
            patch(&gla_getintegerv_nocontext_hook, 1);
            patch(&gla_getintegerv_stub_hook, 1);
            patch(&egl_make_current_base_hook, 1);
            patch(&egl_make_current_trace_hook, 1);
            patch(&registry_bind_hook, 1);
            patch(&callback_binder_gpu_hook, 1);
            patch(&run_callback_hook, 1);
            printf("M57IPCZ hooked target=%p accept=%p\n",
                   transmit_hook.target, accept_hook.target); fflush(0);
            status(2, (unsigned long)transmit_hook.target);
            break;
        }
    }
    if (!transmit_hook.target) { status(3, 0); printf("M57IPCZ framework-not-found\n"); fflush(0); }
}
