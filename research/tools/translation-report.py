#!/usr/bin/env python3
"""Main-thread time per frame spent in the translation layer, from a user-space perf capture folded by analyze-profile.py.
  translation-report.py <capture dir> <mean frame ms> [capture seconds=10] [sample Hz=2999]
Splits it into the Vulkan driver (below a DynamicVK call) and everything else, grouped by the entry point the game called."""
import collections, re, sys
d, frame_ms = sys.argv[1], float(sys.argv[2])
dur = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
hz = float(sys.argv[4]) if len(sys.argv) > 4 else 2999.0
k = frame_ms / (dur * hz)
groups = [('draws', ['drawIndexedPrimitives', 'PrivateRenderCommandEncoder::drawPrimitives', 'MTLRenderCommandEncoderInternal drawPrimitives']),
          ('new encoder', ['renderCommandEncoderWithDescriptor']), ('commit', ['MTLCommandBufferInternal commit]']),
          ('setters', ['setVertexBuffer', 'setFragmentTexture', 'setFragmentSamplerState', 'setRenderPipelineState', 'setFragmentBuffer', 'setDepthStencilState', 'setVertexTexture', 'setVertexSamplerState']),
          ('vertex descriptor', ['MTLVertexDescriptor', 'DescriptorArray resetAll]', 'MTLVertexAttributeDescriptorArray', 'MTLVertexBufferLayoutDescriptorArray']),
          ('pass descriptor', ['MTLRenderPassColorAttachmentDescriptorArray', 'MTLRenderPassDescriptor']),
          ('new command buffer', ['MTLCommandQueueInternal commandBuffer]']), ('event pump', ['NSApplication nextEventMatchingMask']),
          ('end encoding', ['endEncoding'])]
total = game = driver = 0
out = collections.Counter(); drv = collections.Counter()
for line in open(d + '/oncpu.folded'):
    st, n = line.rsplit(' ', 1); n = int(n); total += n
    fr = st.split(';')
    idx = [i for i, x in enumerate(fr) if x.startswith('-[') or x.startswith('+[') or 'Indium::' in x]
    if not idx: game += n; continue
    first = fr[idx[0]]
    name = next((g for g, pats in groups if any(p in first for p in pats)), 'other')
    dv = [i for i, x in enumerate(fr) if 'DynamicVK::DynamicFunction' in x]
    if dv and dv[-1] < len(fr) - 1: driver += n; drv[name] += n
    else: out[name] += n
print(f'frame {frame_ms:.2f} ms | main thread user {total*k:.2f} | game code {game*k:.2f} | driver {driver*k:.2f} | translation outside driver {sum(out.values())*k:.2f}')
for g in sorted(set(out) | set(drv), key=lambda g: -(out[g] + drv[g])):
    print(f'  {g:20s} outside driver {out[g]*k:5.3f} ms   driver {drv[g]*k:5.3f} ms')
