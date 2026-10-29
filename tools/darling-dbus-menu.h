/* SPDX-License-Identifier: GPL-3.0-only -- private native-only interface. */
#ifndef DARLING_DBUS_MENU_H
#define DARLING_DBUS_MENU_H
#include <gio/gio.h>
#include "darling-status-notifier.h"

typedef struct DarlingDBusMenu DarlingDBusMenu;
DarlingDBusMenu *darling_menu_create(GDBusConnection *bus, GAsyncQueue *events);
int darling_menu_set(DarlingDBusMenu *menu, const DarlingStatusMenuEntry *entries, guint count);
gboolean darling_menu_active(DarlingDBusMenu *menu);
void darling_menu_destroy(DarlingDBusMenu *menu);
#endif
