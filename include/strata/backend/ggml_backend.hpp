// strata::gb - the one place that owns ggml backends (CPU, Vulkan) for engines built as ggml graphs.
// Contract: /workspace/strata-notes/vulkan-backend-plan.md section 3 (Nix <-> Nex).  Engines never call
// ggml_backend_vk_* / ggml_backend_cpu_* nor pick a device: only src/backend/ggml_backend.cpp includes ggml-vulkan.h.
#pragma once
#include <cstddef>
#include <memory>
#include <string>

struct ggml_context;
struct ggml_tensor;
struct ggml_cgraph;
typedef struct ggml_backend* ggml_backend_t;
typedef struct ggml_backend_sched* ggml_backend_sched_t;
typedef struct ggml_backend_buffer* ggml_backend_buffer_t;

namespace strata::gb {

enum class Kind { Auto, Vulkan, Cpu };

struct Options {
  Kind kind = Kind::Auto;            // Auto: Vulkan if a device exists, otherwise CPU
  int vk_device = -1;                // -1: first device; env STRATA_VK_DEVICE overrides
  size_t vram_reserve = 256u << 20;  // margin kept free on the GPU
  int cpu_threads = 0;               // 0: hardware concurrency
};

struct DeviceInfo {
  std::string name;
  Kind kind = Kind::Cpu;
  size_t mem_total = 0, mem_free = 0;
  bool fp16 = false, int_dot = false;  // filled in by PR 2 (device feature probe); false until then
};

struct Backend;  // opaque: owns backends, sched, buffers
struct BackendDeleter { void operator()(Backend*) const noexcept; };
using BackendPtr = std::unique_ptr<Backend, BackendDeleter>;

// True when this build was compiled with STRATA_ENABLE_VULKAN.
bool vulkan_compiled();

BackendPtr init(const Options&, std::string* err);  // never throws; nullptr + err
const DeviceInfo& device(const Backend&);
ggml_backend_t gpu(const Backend&);  // nullptr in CPU mode
ggml_backend_t cpu(const Backend&);
ggml_backend_sched_t sched(const Backend&);  // gpu+cpu, op offload on

enum class Pool { Weights, Kv, Scratch };
// Allocates every tensor of a no_alloc context.  host_fallback: use the CPU when the GPU allocation fails.
ggml_backend_buffer_t alloc_ctx(Backend&, ggml_context* ctx, Pool, bool host_fallback);
void upload(ggml_tensor* t, const void* src, size_t off, size_t n);

bool compute(Backend&, ggml_cgraph* g, std::string* err);  // reset + alloc + compute on the sched

}  // namespace strata::gb
