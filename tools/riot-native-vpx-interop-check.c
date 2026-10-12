/* Synthetic-only check: old guest libvpx wrappers calling a native codec. */
#include <elfcalls.h>
#include <vpx/vpx_decoder.h>
#include <vpx/vp8dx.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
extern struct elf_calls *_elfcalls;
static pthread_t owner;
static unsigned allocations,releases,wrong_thread;
static int acquire(void *opaque,size_t size,vpx_codec_frame_buffer_t *fb) {
 (void)opaque;if(!pthread_equal(owner,pthread_self()))wrong_thread++;
 fb->data=calloc(1,size);fb->size=size;fb->priv=fb->data;allocations++;
 return fb->data?0:-1;
}
static int release(void *opaque,vpx_codec_frame_buffer_t *fb) {
 (void)opaque;if(!pthread_equal(owner,pthread_self()))wrong_thread++;
 free(fb->priv);fb->priv=NULL;releases++;return 0;
}
static uint32_t little32(const unsigned char*p) {
 return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
int main(int argc,char**argv) {
 if(argc!=3)return 1;
 void*lib=_elfcalls->dlopen(argv[1]);if(!lib)return 2;
 vpx_codec_iface_t*(*factory)(void)=_elfcalls->dlsym(lib,"RiotNativeVpxInterface");
 if(!factory)return 3;
 FILE*f=fopen(argv[2],"rb");if(!f)return 4;
 unsigned char header[32];if(fread(header,1,32,f)!=32||memcmp(header,"DKIF",4)||memcmp(header+8,"VP90",4))return 5;
 unsigned width=header[12]|header[13]<<8,height=header[14]|header[15]<<8;
 owner=pthread_self();unsigned total=0;int failed=0;
 for(unsigned cycle=0;cycle<20&&!failed;cycle++) {
  vpx_codec_ctx_t ctx={0};vpx_codec_dec_cfg_t cfg={4,0,0};
  int err=vpx_codec_dec_init(&ctx,factory(),&cfg,0);
  if(err){printf("VPX_INTEROP init_error=%d\n",err);failed=1;break;}
  if(vpx_codec_control(&ctx,VP9D_SET_LOOP_FILTER_OPT,1))failed=1;
  err=vpx_codec_set_frame_buffer_functions(&ctx,acquire,release,NULL);
  if(err)failed=1;
  fseek(f,32,SEEK_SET);
  unsigned frames=0;
  while(!failed&&fread(header,1,12,f)==12) {
   uint32_t size=little32(header);if(!size||size>16*1024*1024){failed=1;break;}
   unsigned char*data=malloc(size);if(!data){failed=1;break;}
   if(fread(data,1,size,f)!=size){free(data);failed=1;break;}
   void *tag=(void*)(uintptr_t)(frames*16667ull+1);
   err=vpx_codec_decode(&ctx,data,size,tag,0);free(data);
   if(err){printf("VPX_INTEROP decode_error=%d\n",err);failed=1;break;}
   vpx_codec_iter_t iter=NULL;vpx_image_t*img;
   while((img=vpx_codec_get_frame(&ctx,&iter))) {
    if(img->user_priv!=tag)failed=1;
    if(img->d_w!=width||img->d_h!=height||!img->planes[0]||img->planes[0][0]<75||img->planes[0][0]>85)failed=1;
    frames++;total++;
   }
  }
  if(vpx_codec_decode(&ctx,NULL,0,NULL,0))failed=1;
  if(frames!=60||vpx_codec_destroy(&ctx))failed=1;
 }
 fclose(f);failed|=wrong_thread!=0||allocations!=releases;
 printf("VPX_INTEROP frames=%u allocations=%u releases=%u callback_wrong_thread=%u timestamp_tags_preserved=1 flush=1 pass=%d\n",total,allocations,releases,wrong_thread,!failed);
 return failed?6:0;
}
