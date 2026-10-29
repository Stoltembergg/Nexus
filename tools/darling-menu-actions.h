/* SPDX-License-Identifier: GPL-3.0-only
 * Host-side actions for the exported tray menu.
 *
 * The menu itself is produced by the guest application. Two actions cannot be
 * implemented by the guest in this compatibility layer: ending every process
 * of the game tree, and bringing the client window back after it was closed.
 * They are therefore handled here, on the host, by a project-owned helper.
 *
 * The feature is opt-in: without DARLING_STATUS_MENU_ACTION_SCRIPT the menu
 * keeps exactly the guest entries and every click is forwarded unchanged.
 */
#ifndef DARLING_MENU_ACTIONS_H
#define DARLING_MENU_ACTIONS_H
#include <gio/gio.h>
#include "darling-status-notifier.h"

enum DarlingMenuAction {
    DARLING_MENU_ACTION_NONE = 0,
    DARLING_MENU_ACTION_QUIT = 1,
    DARLING_MENU_ACTION_REOPEN = 2
};

/* Reserved IDs for the synthetic entries. They are far above the range the
 * guest can use, so a guest snapshot never collides with them. */
#define DARLING_MENU_ACTION_SEPARATOR_ID 1000000
#define DARLING_MENU_ACTION_QUIT_ID 1000001
#define DARLING_MENU_ACTION_REOPEN_ID 1000002

/* The action a menu label stands for, or DARLING_MENU_ACTION_NONE. */
int darling_menu_action_for_label(const char *label);
/* The label of an action, or NULL when it has none. */
const char *darling_menu_action_label(int action);
/* Whether a host action helper is configured. */
gboolean darling_menu_actions_enabled(void);
/* Run the configured helper for an action. Returns TRUE when it was started. */
gboolean darling_menu_action_run(int action);
/* The entries this project adds to the guest snapshot: a separator and the
 * two host actions. An action whose label the guest already uses is not added
 * twice; that guest entry is handled by the host instead. Writes at most
 * *max* entries and returns how many were written. */
guint darling_menu_action_entries(const DarlingStatusMenuEntry *entries, guint count,
                                   DarlingStatusMenuEntry *out, guint max);
#endif
