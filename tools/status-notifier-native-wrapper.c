/* SPDX-License-Identifier: GPL-3.0-only
 * Mach-O entry points. Only POD data crosses the native ELF boundary.
 * All calls are serialized by the AppKit main thread, including first load.
 */
#include <elfcalls.h>
#include "darling-status-notifier.h"

extern struct elf_calls *_elfcalls;
#ifndef DARLING_STATUS_HOST_LIBRARY
#error DARLING_STATUS_HOST_LIBRARY must name the native transport library
#endif

static void *library;
static int attempted;
static DarlingStatusNotifier *(*create_item)(const char *, const char *, const char *);
static void (*set_title)(DarlingStatusNotifier *, const char *);
static void (*set_tooltip)(DarlingStatusNotifier *, const char *);
static void (*set_icon_name)(DarlingStatusNotifier *, const char *);
static int (*set_icon)(DarlingStatusNotifier *, uint32_t, uint32_t, const uint8_t *);
static int (*poll_item)(DarlingStatusNotifier *, DarlingStatusEvent *);
static int (*set_menu)(DarlingStatusNotifier *, const DarlingStatusMenuEntry *, uint32_t);
static const char *(*bus_name)(DarlingStatusNotifier *);
static void (*destroy_item)(DarlingStatusNotifier *);

static int load_library(void) {
    if (attempted) return library != NULL;
    attempted = 1;
    if (!_elfcalls || !_elfcalls->dlopen || !_elfcalls->dlsym) return 0;
    void *handle = _elfcalls->dlopen(DARLING_STATUS_HOST_LIBRARY);
    if (!handle) return 0;
#define RESOLVE(variable, symbol) variable = _elfcalls->dlsym(handle, symbol)
    RESOLVE(create_item, "DarlingStatusNotifierCreate");
    RESOLVE(set_title, "DarlingStatusNotifierSetTitle");
    RESOLVE(set_tooltip, "DarlingStatusNotifierSetToolTip");
    RESOLVE(set_icon_name, "DarlingStatusNotifierSetIconName");
    RESOLVE(set_icon, "DarlingStatusNotifierSetIcon");
    RESOLVE(poll_item, "DarlingStatusNotifierPoll");
    RESOLVE(set_menu, "DarlingStatusNotifierSetMenu");
    RESOLVE(bus_name, "DarlingStatusNotifierBusName");
    RESOLVE(destroy_item, "DarlingStatusNotifierDestroy");
#undef RESOLVE
    if (!create_item || !set_title || !set_tooltip || !set_icon_name ||
        !set_icon || !poll_item || !set_menu || !bus_name || !destroy_item) {
        if (_elfcalls->dlclose) _elfcalls->dlclose(handle);
        return 0;
    }
    library = handle; /* Keep loaded until process exit; item function pointers depend on it. */
    return 1;
}

DarlingStatusNotifier *DarlingStatusNotifierCreate(const char *id, const char *title,
                                                  const char *icon) {
    return load_library() ? create_item(id, title, icon) : NULL;
}
void DarlingStatusNotifierSetTitle(DarlingStatusNotifier *item, const char *title) {
    if (item && library) set_title(item, title);
}
void DarlingStatusNotifierSetToolTip(DarlingStatusNotifier *item, const char *tooltip) {
    if (item && library) set_tooltip(item, tooltip);
}
void DarlingStatusNotifierSetIconName(DarlingStatusNotifier *item, const char *name) {
    if (item && library) set_icon_name(item, name);
}
int DarlingStatusNotifierSetIcon(DarlingStatusNotifier *item, uint32_t width,
                                 uint32_t height, const uint8_t *argb) {
    return item && library ? set_icon(item, width, height, argb) : 0;
}
int DarlingStatusNotifierPoll(DarlingStatusNotifier *item, DarlingStatusEvent *event) {
    return item && library ? poll_item(item, event) : 0;
}
int DarlingStatusNotifierSetMenu(DarlingStatusNotifier *item,
                                const DarlingStatusMenuEntry *entries, uint32_t count) {
    return item && library ? set_menu(item, entries, count) : 0;
}
const char *DarlingStatusNotifierBusName(DarlingStatusNotifier *item) {
    return item && library ? bus_name(item) : NULL;
}
void DarlingStatusNotifierDestroy(DarlingStatusNotifier *item) {
    if (item && library) destroy_item(item);
}
