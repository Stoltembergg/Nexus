/* Observe X11 paint notifications without modifying or sampling game memory.
 * These are window updates, not display scanout events. Cross-check their rate
 * against the game's FPS HUD before using them for a renderer comparison. */
#include <X11/Xlib.h>
#include <X11/extensions/Xdamage.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s window-id seconds output.csv\n", argv[0]);
        return 1;
    }
    double seconds = strtod(argv[2], NULL);
    if (seconds < 1 || seconds > 600) return 2;
    Display *display = XOpenDisplay(NULL);
    if (!display) return 3;
    int event_base, error_base;
    if (!XDamageQueryExtension(display, &event_base, &error_base)) return 4;
    Window window = strtoul(argv[1], NULL, 0);
    Damage damage = XDamageCreate(display, window, XDamageReportNonEmpty);
    XFlush(display);
    FILE *output = fopen(argv[3], "w");
    if (!output) return 5;
    fprintf(output, "arrival_ns,server_ms,x,y,width,height,window_width,window_height\n");
    uint64_t start = now_ns(), end = start + (uint64_t)(seconds * 1e9);
    unsigned count = 0;
    struct pollfd fd = {ConnectionNumber(display), POLLIN, 0};
    while (now_ns() < end) {
        if (!XPending(display)) {
            if (poll(&fd, 1, 20) < 0) break;
            if (!XPending(display)) continue;
        }
        XEvent event;
        XNextEvent(display, &event);
        if (event.type != event_base + XDamageNotify) continue;
        XDamageNotifyEvent *update = (XDamageNotifyEvent *)&event;
        uint64_t timestamp = now_ns();
        XDamageSubtract(display, damage, None, None);
        XFlush(display);
        if (timestamp - start < 500000000) continue;
        fprintf(output, "%llu,%lu,%d,%d,%u,%u,%u,%u\n",
                (unsigned long long)timestamp, update->timestamp,
                update->area.x, update->area.y, update->area.width,
                update->area.height, update->geometry.width, update->geometry.height);
        ++count;
    }
    fclose(output);
    XDamageDestroy(display, damage);
    XCloseDisplay(display);
    printf("Window updates: %u events, %.1f seconds\n", count, seconds);
    return count > 1 ? 0 : 6;
}
