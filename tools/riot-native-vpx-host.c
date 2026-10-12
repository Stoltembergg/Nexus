/* Linux codec factory; guest high-level wrappers keep their existing ABI. */
#include <vpx/vp8dx.h>
#include <vpx/vpx_decoder.h>
#if VPX_IMAGE_ABI_VERSION != 5 || VPX_DECODER_ABI_VERSION != 12
#error Native VP9 public ABI differs from the verified guest interface
#endif
const void *RiotNativeVpxInterface(void) { return vpx_codec_vp9_dx(); }
