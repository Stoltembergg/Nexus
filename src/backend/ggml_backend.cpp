// strata::gb implementation (PR 1: minimal; device probing, memory budget and telemetry arrive in PRs 2-4).
#include "strata/backend/ggml_backend.hpp"

#include <algorithm>
#include <cstdlib>
#include <thread>
#include <vector>

#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#ifdef STRATA_GB_VULKAN
#include "ggml-vulkan.h"  // the only include of ggml-vulkan.h in the tree
#endif

namespace strata::gb {

struct Backend {
  DeviceInfo info;
  ggml_backend_t gpu = nullptr;
  ggml_backend_t cpu = nullptr;
  ggml_backend_sched_t sched = nullptr;
  std::vector<ggml_backend_buffer_t> buffers;
};

void BackendDeleter::operator()(Backend* b) const noexcept {
  if (!b) return;
  if (b->sched) ggml_backend_sched_free(b->sched);
  for (auto* buf : b->buffers) ggml_backend_buffer_free(buf);
  if (b->gpu) ggml_backend_free(b->gpu);
  if (b->cpu) ggml_backend_free(b->cpu);
  delete b;
}

bool vulkan_compiled() {
#ifdef STRATA_GB_VULKAN
  return true;
#else
  return false;
#endif
}

static void set_err(std::string* err, std::string msg) { if (err) *err = std::move(msg); }

#ifdef STRATA_GB_VULKAN
static bool init_vulkan(Backend& b, const Options& o, std::string* err) {
  int n = ggml_backend_vk_get_device_count();
  if (n <= 0) { set_err(err, "strata::gb: no Vulkan device found"); return false; }
  int dev = o.vk_device;
  if (const char* e = std::getenv("STRATA_VK_DEVICE")) dev = std::atoi(e);
  if (dev < 0) dev = 0;
  if (dev >= n) { set_err(err, "strata::gb: Vulkan device index out of range"); return false; }
  b.gpu = ggml_backend_vk_init(static_cast<size_t>(dev));
  if (!b.gpu) { set_err(err, "strata::gb: ggml_backend_vk_init failed"); return false; }
  char desc[256] = {};
  ggml_backend_vk_get_device_description(dev, desc, sizeof desc);
  b.info.name = desc;
  b.info.kind = Kind::Vulkan;
  ggml_backend_vk_get_device_memory(dev, &b.info.mem_free, &b.info.mem_total);
  b.info.mem_free = b.info.mem_free > o.vram_reserve ? b.info.mem_free - o.vram_reserve : 0;
  return true;
}
#endif

BackendPtr init(const Options& o, std::string* err) {
  BackendPtr b(new (std::nothrow) Backend);
  if (!b) { set_err(err, "strata::gb: out of memory"); return nullptr; }
  if (o.kind == Kind::Vulkan || o.kind == Kind::Auto) {
#ifdef STRATA_GB_VULKAN
    std::string vk_err;
    if (!init_vulkan(*b, o, &vk_err) && o.kind == Kind::Vulkan) { set_err(err, vk_err); return nullptr; }
#else
    if (o.kind == Kind::Vulkan) {
      set_err(err, "strata::gb: Vulkan requested but this build has STRATA_ENABLE_VULKAN=OFF");
      return nullptr;
    }
#endif
  }
  b->cpu = ggml_backend_cpu_init();
  if (!b->cpu) { set_err(err, "strata::gb: ggml_backend_cpu_init failed"); return nullptr; }
  int threads = o.cpu_threads > 0 ? o.cpu_threads : static_cast<int>(std::max(1u, std::thread::hardware_concurrency()));
  ggml_backend_cpu_set_n_threads(b->cpu, threads);
  if (!b->gpu) b->info.name = "CPU", b->info.kind = Kind::Cpu;
  ggml_backend_t list[2];
  int n = 0;
  if (b->gpu) list[n++] = b->gpu;
  list[n++] = b->cpu;  // the CPU goes last, as ggml_backend_sched requires
  b->sched = ggml_backend_sched_new(list, nullptr, n, GGML_DEFAULT_GRAPH_SIZE, false, true);
  if (!b->sched) { set_err(err, "strata::gb: ggml_backend_sched_new failed"); return nullptr; }
  return b;
}

const DeviceInfo& device(const Backend& b) { return b.info; }
ggml_backend_t gpu(const Backend& b) { return b.gpu; }
ggml_backend_t cpu(const Backend& b) { return b.cpu; }
ggml_backend_sched_t sched(const Backend& b) { return b.sched; }

ggml_backend_buffer_t alloc_ctx(Backend& b, ggml_context* ctx, Pool, bool host_fallback) {
  ggml_backend_buffer_t buf = nullptr;
  if (b.gpu) buf = ggml_backend_alloc_ctx_tensors(ctx, b.gpu);
  if (!buf && (!b.gpu || host_fallback)) buf = ggml_backend_alloc_ctx_tensors(ctx, b.cpu);
  if (buf) b.buffers.push_back(buf);
  return buf;
}

void upload(ggml_tensor* t, const void* src, size_t off, size_t n) { ggml_backend_tensor_set(t, src, off, n); }

bool compute(Backend& b, ggml_cgraph* g, std::string* err) {
  ggml_backend_sched_reset(b.sched);
  if (!ggml_backend_sched_alloc_graph(b.sched, g)) { set_err(err, "strata::gb: graph allocation failed"); return false; }
  if (ggml_backend_sched_graph_compute(b.sched, g) != GGML_STATUS_SUCCESS) {
    set_err(err, "strata::gb: graph compute failed");
    return false;
  }
  return true;
}

}  // namespace strata::gb
