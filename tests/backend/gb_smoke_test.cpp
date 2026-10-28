// strata::gb smoke test: c = a + b on the selected backend, checked against the expected values.
// Args: cpu | vulkan | auto (default auto).  Exit 0 = ok.
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "ggml-backend.h"
#include "ggml.h"
#include "strata/backend/ggml_backend.hpp"

int main(int argc, char** argv) {
  using namespace strata::gb;
  Options o;
  if (argc > 1 && !std::strcmp(argv[1], "cpu")) o.kind = Kind::Cpu;
  if (argc > 1 && !std::strcmp(argv[1], "vulkan")) o.kind = Kind::Vulkan;
  std::string err;
  auto b = init(o, &err);
  if (!b) { std::fprintf(stderr, "init: %s\n", err.c_str()); return 1; }
  std::printf("vulkan_compiled=%d device=%s kind=%s\n", vulkan_compiled(), device(*b).name.c_str(),
              device(*b).kind == Kind::Vulkan ? "vulkan" : "cpu");
  const int n = 1024;
  ggml_init_params wp{ggml_tensor_overhead() * 4, nullptr, true};
  ggml_context* w = ggml_init(wp);
  ggml_tensor* a = ggml_new_tensor_1d(w, GGML_TYPE_F32, n);
  ggml_tensor* c = ggml_new_tensor_1d(w, GGML_TYPE_F32, n);
  if (!alloc_ctx(*b, w, Pool::Weights, true)) { std::fprintf(stderr, "alloc_ctx failed\n"); return 1; }
  std::vector<float> va(n), vc(n);
  for (int i = 0; i < n; ++i) va[i] = 0.5f * i, vc[i] = 2.0f;
  upload(a, va.data(), 0, n * sizeof(float));
  upload(c, vc.data(), 0, n * sizeof(float));
  ggml_init_params gp{ggml_tensor_overhead() * 8 + ggml_graph_overhead(), nullptr, true};
  ggml_context* gctx = ggml_init(gp);
  ggml_tensor* out = ggml_add(gctx, a, c);
  ggml_cgraph* g = ggml_new_graph(gctx);
  ggml_build_forward_expand(g, out);
  if (!compute(*b, g, &err)) { std::fprintf(stderr, "compute: %s\n", err.c_str()); return 1; }
  std::vector<float> r(n);
  ggml_backend_tensor_get(out, r.data(), 0, n * sizeof(float));
  for (int i = 0; i < n; ++i)
    if (std::fabs(r[i] - (0.5f * i + 2.0f)) > 1e-5f) { std::fprintf(stderr, "mismatch at %d\n", i); return 1; }
  std::printf("ok\n");
  ggml_free(gctx);
  b.reset();
  ggml_free(w);
  return 0;
}
