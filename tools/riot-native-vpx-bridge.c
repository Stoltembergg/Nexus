/* Guarded Electron and League CEF VP9 algorithm interface replacement.
 * Changes a private data page, never the application on disk. The ABI-5
 * decoder prefix is stable between libvpx 1.12 and 1.17; the unused encoder
 * tail stays untouched. Native workers perform no guest callbacks.
 */
#include <elfcalls.h>
extern struct elf_calls *_elfcalls;
extern void _dyld_register_func_for_add_image(void (*)(const void*,intptr_t));
extern int mprotect(void*,size_t,int);
extern void *memcpy(void*,const void*,size_t);
extern int memcmp(const void*,const void*,size_t);
extern long write(int,const void*,size_t);
#ifndef RIOT_NATIVE_VPX_HOST
#error RIOT_NATIVE_VPX_HOST must identify the native library
#endif
struct decoder_prefix {
 const char*name;int abi;int padding;unsigned long caps;
 void*init;void*destroy;void*controls;
 void*peek;void*info;void*decode;void*frame;void*buffers;
};
_Static_assert(sizeof(struct decoder_prefix)==88,"Codec prefix ABI mismatch");
struct codec_build {
 unsigned char uuid[16];
 uintptr_t getter, interface, init, destroy, decode, buffers;
 unsigned char getter_code[13];
};
static const struct codec_build builds[] = {
 {{0x4c,0x4c,0x44,0x72,0x55,0x55,0x31,0x44,0xa1,0x43,0x03,0xd0,0x05,0xe4,0x38,0xed},
  0x4055440,0x8c54730,0x4055450,0x40554d0,0x4055550,0x4055a70,
  {0x55,0x48,0x89,0xe5,0x48,0x8d,0x05,0xe5,0xf2,0xbf,0x04,0x5d,0xc3}},
 {{0x4c,0x4c,0x44,0xa9,0x55,0x55,0x31,0x44,0xa1,0x9c,0x08,0x3d,0x94,0xf1,0x82,0x4d},
  0x43e2a20,0xa652ba0,0x43e2a30,0x43e2ab0,0x43e2b30,0x43e3050,
  {0x55,0x48,0x89,0xe5,0x48,0x8d,0x05,0x75,0x01,0x27,0x06,0x5d,0xc3}}
};
static void add_image(const void*header,intptr_t slide) {
 (void)slide;static int installed;
 if(installed)return;
 const unsigned*h=header;if(h[0]!=0xfeedfacf||h[1]!=0x01000007)return;
 const unsigned char*command=(const unsigned char*)header+32;
 const struct codec_build*build=0;
 for(unsigned i=0;i<h[4];i++) {
  const unsigned*c=(const unsigned*)command;if(c[1]<8)return;
  if(c[0]==0x1b&&c[1]==24)
   for(unsigned j=0;j<sizeof(builds)/sizeof(builds[0]);j++)
    if(!memcmp(command+8,builds[j].uuid,16))build=&builds[j];
  command+=c[1];
 }
 if(!build)return;
 const unsigned char*base=header;
 if(memcmp(base+build->getter,build->getter_code,sizeof(build->getter_code)))return;
 struct decoder_prefix*guest=(void*)(base+build->interface);
 if(guest->abi!=5||guest->caps!=0x440005||guest->init!=(void*)(base+build->init)||guest->destroy!=(void*)(base+build->destroy)||guest->decode!=(void*)(base+build->decode)||guest->buffers!=(void*)(base+build->buffers))return;
 void*lib=_elfcalls->dlopen(RIOT_NATIVE_VPX_HOST);if(!lib)return;
 const struct decoder_prefix*(*factory)(void)=_elfcalls->dlsym(lib,"RiotNativeVpxInterface");
 const struct decoder_prefix*native=factory?factory():0;
 if(!native||native->abi!=5||(native->caps&0x400005)!=0x400005||!native->init||!native->destroy||!native->controls||!native->decode||!native->frame||!native->buffers){_elfcalls->dlclose(lib);return;}
 void*page=(void*)((uintptr_t)guest&~(uintptr_t)4095);
 if(mprotect(page,4096,3)){_elfcalls->dlclose(lib);return;}
 memcpy(guest,native,sizeof(*guest));mprotect(page,4096,1);installed=1;
 const char message[]="NATIVE_VPX guarded ABI-5 decoder installed\n";write(2,message,sizeof(message)-1);
}
__attribute__((constructor)) static void initialize(void) {
 _dyld_register_func_for_add_image(add_image);
}
