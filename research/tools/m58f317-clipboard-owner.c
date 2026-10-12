/* Own only an isolated Xvfb clipboard; never reads the user's clipboard. */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    int latin1=argc>1 && !strcmp(argv[1],"--latin1");
    Display *d=XOpenDisplay(":99");
    if (!d) return 1;
    Window w=XCreateSimpleWindow(d,DefaultRootWindow(d),0,0,1,1,0,0,0);
    Atom clip=XInternAtom(d,"CLIPBOARD",False),utf8=XInternAtom(d,"UTF8_STRING",False),targets=XInternAtom(d,"TARGETS",False);
    XSetSelectionOwner(d,clip,w,CurrentTime);XFlush(d);
    puts("CLIPBOARD_OWNER ready");fflush(stdout);
    for (;;) {
        XEvent e;XNextEvent(d,&e);
        if(e.type!=SelectionRequest)continue;
        XSelectionRequestEvent *r=&e.xselectionrequest;
        Atom prop=r->property==None?r->target:r->property;
        XEvent reply={0};reply.xselection=(XSelectionEvent){.type=SelectionNotify,.display=d,.requestor=r->requestor,.selection=r->selection,.target=r->target,.property=prop,.time=r->time};
        if(r->target==targets){Atom a[]={targets,latin1?XA_STRING:utf8,XA_STRING};XChangeProperty(d,r->requestor,prop,XA_ATOM,32,PropModeReplace,(unsigned char*)a,latin1?2:3);}
        else if((!latin1 && r->target==utf8)||r->target==XA_STRING){const char *s=latin1?"darling_past\xe9":"darling_paste";XChangeProperty(d,r->requestor,prop,r->target,8,PropModeReplace,(unsigned char*)s,strlen(s));}
        else reply.xselection.property=None;
        XSendEvent(d,r->requestor,False,0,&reply);XFlush(d);
    }
}
