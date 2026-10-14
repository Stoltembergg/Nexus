// Passive cursor watcher: prints a line each time the X server's displayed
// cursor changes (XFixes CursorNotify on the root window). Reads nothing from
// any client; it only shows whether the X side (Darling -> Xwayland) changes the
// cursor. If lines keep appearing while the screen cursor stays stuck, the
// stall is after Xwayland, in the compositor.
// Build: cc -O2 -o build/riot-cursor-watch tools/riot-cursor-watch/cursor-watch.c -lX11 -lXfixes
#include <X11/Xlib.h>
#include <X11/extensions/Xfixes.h>
#include <stdio.h>
#include <time.h>

int main(void)
{
	Display *d = XOpenDisplay(NULL);
	if (!d) { fprintf(stderr, "cannot open display\n"); return 1; }
	int ev, err;
	if (!XFixesQueryExtension(d, &ev, &err)) { fprintf(stderr, "no XFixes\n"); return 1; }
	XFixesSelectCursorInput(d, DefaultRootWindow(d), XFixesDisplayCursorNotifyMask);
	for (;;) {
		XEvent e;
		XNextEvent(d, &e);
		if (e.type != ev + XFixesCursorNotify) continue;
		XFixesCursorNotifyEvent *c = (XFixesCursorNotifyEvent *)&e;
		XFixesCursorImage *img = XFixesGetCursorImage(d);
		struct timespec t; clock_gettime(CLOCK_REALTIME, &t);
		struct tm tm; localtime_r(&t.tv_sec, &tm);
		printf("%02d:%02d:%02d.%03ld serial %lu %ux%u hot %u,%u\n", tm.tm_hour, tm.tm_min, tm.tm_sec,
		       t.tv_nsec / 1000000, c->cursor_serial, img ? img->width : 0, img ? img->height : 0,
		       img ? img->xhot : 0, img ? img->yhot : 0);
		fflush(stdout);
		if (img) XFree(img);
	}
}
