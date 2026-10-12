/* Native control: can XGetImage observe Mesa EGL window presentation? */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <EGL/egl.h>
#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>
#include <GL/glext.h>
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/mman.h>
#include "../build/darling-src/src/frameworks/OpenGL/include/OpenGL/DarlingNativePresent.h"
extern void *DarlingXShmCreate(Display*,Visual*,unsigned,unsigned,unsigned);
extern int DarlingXShmStart(void*,Drawable,GC,const char*);
extern void DarlingXShmDestroy(void*);
int main(void){
 Display*d=XOpenDisplay(NULL);if(!d)return 1;EGLDisplay e=getenv("M366_DEFAULT_EGL")?eglGetPlatformDisplay(0x31D5,EGL_DEFAULT_DISPLAY,NULL):eglGetDisplay(d);EGLint major,minor;if(!eglInitialize(e,&major,&minor)||!eglBindAPI(EGL_OPENGL_API))return 2;
 EGLint attrs[]={EGL_SURFACE_TYPE,EGL_WINDOW_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};EGLConfig c;EGLint n,visual;
 if(!eglChooseConfig(e,attrs,&c,1,&n)||!n||!eglGetConfigAttrib(e,c,EGL_NATIVE_VISUAL_ID,&visual))return 3;
 XVisualInfo q={.visualid=visual};XVisualInfo*v=XGetVisualInfo(d,VisualIDMask,&q,&n);if(!v)return 4;
 Colormap cmap=XCreateColormap(d,DefaultRootWindow(d),v->visual,AllocNone);XSetWindowAttributes a={.colormap=cmap,.border_pixel=0,.background_pixel=0,.override_redirect=True};
 Window w=XCreateWindow(d,DefaultRootWindow(d),20,20,1024,640,0,v->depth,InputOutput,v->visual,CWColormap|CWBorderPixel|CWBackPixel|CWOverrideRedirect,&a);XStoreName(d,w,"Native EGL control");XMapRaised(d,w);XSync(d,False);usleep(100000);
 EGLSurface s=eglCreateWindowSurface(e,c,w,NULL);EGLContext ctx=eglCreateContext(e,c,EGL_NO_CONTEXT,NULL);if(s==EGL_NO_SURFACE||ctx==EGL_NO_CONTEXT||!eglMakeCurrent(e,s,s,ctx))return 5;
 void *helper=NULL;DarlingNativePresentTarget *target=NULL;
 if(getenv("M370_XSHM_CONTROL")){
  size_t bytes=32+1024*640*4;int fd=open("/tmp/m370-control-slot",O_CREAT|O_RDWR,0600);ftruncate(fd,bytes);
  uint32_t*h=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);h[0]=0x43414652;h[1]=2;h[2]=1024;h[3]=640;h[4]=4096;h[5]=0;((uint64_t*)h)[3]=1024*640*4;
  helper=DarlingXShmCreate(d,v->visual,v->depth,1024,640);if(!helper||!DarlingXShmStart(helper,w,DefaultGC(d,DefaultScreen(d)),"/tmp/m370-control-slot"))return 6;
  char path[128];snprintf(path,sizeof(path),"/dev/shm/darling-ca-gpu-target-%u-1024-640",getuid());fd=open(path,O_RDWR);if(fd<0)return 7;
  target=mmap(NULL,sizeof(*target),PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);__atomic_store_n(&target->ready,1,__ATOMIC_RELEASE);
  for(int j=0;j<40&&target->ready==1;j++)usleep(500);printf("NATIVE_EGL helper_ack=%u\n",target->ready);
 }
 GLuint tex=0,fbo=0;
 if(getenv("M372_BLIT_CONTROL")){glGenTextures(1,&tex);glBindTexture(GL_TEXTURE_2D,tex);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,1024,640,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,tex,0);}
 glClearColor(33/255.f,100/255.f,200/255.f,1);glClear(GL_COLOR_BUFFER_BIT);
 if(fbo){glBindFramebuffer(GL_DRAW_FRAMEBUFFER,0);glDrawBuffer(GL_BACK);glReadBuffer(GL_COLOR_ATTACHMENT0);glBlitFramebuffer(0,640,1024,0,0,0,1024,640,GL_COLOR_BUFFER_BIT,GL_NEAREST);}
 if(fbo)glBindFramebuffer(GL_READ_FRAMEBUFFER,0);
 eglSwapBuffers(e,s);if(target)__atomic_store_n(&target->ready,3,__ATOMIC_RELEASE);XSync(d,False);usleep(300000);
 XImage*i=XGetImage(d,w,510,50,1,1,~0L,ZPixmap);printf("NATIVE_EGL pixel=%#lx renderer=%s error=%u\n",i?XGetPixel(i,0,0):0,glGetString(GL_RENDERER),glGetError());if(i)XDestroyImage(i);
 if(helper)DarlingXShmDestroy(helper);if(target)munmap(target,sizeof(*target));
 eglMakeCurrent(e,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);eglDestroyContext(e,ctx);eglDestroySurface(e,s);eglTerminate(e);XDestroyWindow(d,w);XFree(v);XFreeColormap(d,cmap);XCloseDisplay(d);return 0;
}
