/* SPDX-License-Identifier: GPL-3.0-only
 * Native Linux transport. No Objective-C objects or callbacks cross this ABI.
 */
#ifndef DARLING_STATUS_NOTIFIER_H
#define DARLING_STATUS_NOTIFIER_H
#include <stdint.h>

typedef struct DarlingStatusNotifier DarlingStatusNotifier;
enum DarlingStatusEventKind {
    DARLING_STATUS_ACTIVATE = 1,
    DARLING_STATUS_SECONDARY_ACTIVATE,
    DARLING_STATUS_CONTEXT_MENU,
    DARLING_STATUS_SCROLL,
    DARLING_STATUS_MENU_CLICK, /* x = stable menu item ID */
    DARLING_STATUS_MENU_OPEN,  /* x = submenu ID; refresh asynchronously */
    DARLING_STATUS_MENU_CLOSE  /* x = submenu ID; end guest tracking */
};
typedef struct {
    int32_t kind;
    int32_t x;
    int32_t y;
    int32_t delta;
    int32_t horizontal;
} DarlingStatusEvent;

/* Snapshot ABI: IDs are positive and stable, parent 0 is the virtual root.
 * A parent must precede its children. Labels are copied UTF-8 (max 4096 bytes).
 * Maximum 1024 entries, nesting 32. No pointers are kept after SetMenu returns.
 */
enum DarlingStatusMenuFlags {
    DARLING_MENU_ENABLED = 1,
    DARLING_MENU_VISIBLE = 2,
    DARLING_MENU_SEPARATOR = 4,
    DARLING_MENU_CHECK = 8,
    DARLING_MENU_RADIO = 16
};
typedef struct {
    int32_t id, parent;
    const char *label;
    uint32_t flags;
    int32_t toggle_state; /* -1 mixed, 0 unchecked, 1 checked */
} DarlingStatusMenuEntry;

/* Returns NULL on invalid UTF-8 or unavailable session bus. Must not abort the
 * guest. Calls on the same item must be serialized by its owner (AppKit main
 * thread). D-Bus work takes place on a private native GLib context/thread.
 */
DarlingStatusNotifier *DarlingStatusNotifierCreate(const char *id, const char *title,
                                                  const char *icon_name);
void DarlingStatusNotifierSetTitle(DarlingStatusNotifier *item, const char *title);
void DarlingStatusNotifierSetToolTip(DarlingStatusNotifier *item, const char *tooltip);
void DarlingStatusNotifierSetIconName(DarlingStatusNotifier *item, const char *name);
/* Zero entries removes the exported menu. Rejected snapshots leave it intact.
 * The owner must revalidate queued clicks against its current live menu before
 * dispatching an action. AboutToShow queues MENU_OPEN and returns immediately;
 * refreshing asynchronously emits LayoutUpdated, never calls guest code here.
 */
int DarlingStatusNotifierSetMenu(DarlingStatusNotifier *item,
                                const DarlingStatusMenuEntry *entries, uint32_t count);
/* Packed, row-major, network-byte-order ARGB, as required by StatusNotifierItem.
 * A NULL buffer with zero dimensions clears the pixmap. Maximum: 256 x 256.
 */
int DarlingStatusNotifierSetIcon(DarlingStatusNotifier *item, uint32_t width,
                                 uint32_t height, const uint8_t *argb);
/* Poll from the guest main loop and dispatch Cocoa actions there, never from a
 * Linux callback. Returns 1 for an event, 0 when empty. Queue is bounded.
 */
int DarlingStatusNotifierPoll(DarlingStatusNotifier *item, DarlingStatusEvent *event);
/* Borrowed immutable unique D-Bus name, valid until Destroy; useful for probes. */
const char *DarlingStatusNotifierBusName(DarlingStatusNotifier *item);
void DarlingStatusNotifierDestroy(DarlingStatusNotifier *item);
#endif
