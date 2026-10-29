/* SPDX-License-Identifier: GPL-3.0-only
 * Host-side actions for the exported tray menu. See darling-menu-actions.h.
 *
 * Nothing here inspects or drives the client: the helper script is a
 * project-owned program that only acts on the Darling prefix of this
 * session.
 */
#include "darling-menu-actions.h"
#include <stdlib.h>
#include <string.h>

#define ACTION_SCRIPT_ENV "DARLING_STATUS_MENU_ACTION_SCRIPT"
#define QUIT_LABEL_ENV "DARLING_STATUS_MENU_QUIT_LABEL"
#define REOPEN_LABEL_ENV "DARLING_STATUS_MENU_REOPEN_LABEL"

#define DEFAULT_QUIT_LABEL "Sair"
#define DEFAULT_REOPEN_LABEL "Riot Games"

static gchar *action_script;
static gchar *quit_label;
static gchar *reopen_label;
static gboolean configured;

/* Read the configuration once. The environment belongs to the session that
 * loaded this library, so it cannot change under the menu. */
static void configure(void) {
    if (configured) return;
    configured = TRUE;
    const char *script = getenv(ACTION_SCRIPT_ENV);
    const char *quit = getenv(QUIT_LABEL_ENV);
    const char *reopen = getenv(REOPEN_LABEL_ENV);
    if (script && script[0] == '/') action_script = g_strdup(script);
    quit_label = g_strdup(quit && quit[0] ? quit : DEFAULT_QUIT_LABEL);
    reopen_label = g_strdup(reopen && reopen[0] ? reopen : DEFAULT_REOPEN_LABEL);
}

gboolean darling_menu_actions_enabled(void) {
    configure();
    return action_script != NULL;
}

const char *darling_menu_action_label(int action) {
    configure();
    if (action == DARLING_MENU_ACTION_QUIT) return quit_label;
    if (action == DARLING_MENU_ACTION_REOPEN) return reopen_label;
    return NULL;
}

int darling_menu_action_for_label(const char *label) {
    configure();
    if (!label || !action_script) return DARLING_MENU_ACTION_NONE;
    if (!strcmp(label, quit_label)) return DARLING_MENU_ACTION_QUIT;
    if (!strcmp(label, reopen_label)) return DARLING_MENU_ACTION_REOPEN;
    return DARLING_MENU_ACTION_NONE;
}

static void reaped(gint pid, gint status, gpointer data) {
    (void)status;
    (void)data;
    g_spawn_close_pid(pid);
}

guint darling_menu_action_entries(const DarlingStatusMenuEntry *entries, guint count,
                                   DarlingStatusMenuEntry *out, guint max) {
    if (!darling_menu_actions_enabled() || max < 1) return 0;
    gboolean have_quit = FALSE, have_reopen = FALSE;
    for (guint i = 0; i < count; i++) {
        int action = darling_menu_action_for_label(entries[i].label);
        if (action == DARLING_MENU_ACTION_QUIT) have_quit = TRUE;
        else if (action == DARLING_MENU_ACTION_REOPEN) have_reopen = TRUE;
    }
    if (have_quit && have_reopen) return 0;
    guint n = 0;
    out[n].id = DARLING_MENU_ACTION_SEPARATOR_ID;
    out[n].parent = 0;
    out[n].label = "";
    out[n].flags = DARLING_MENU_SEPARATOR;
    out[n].toggle_state = -1;
    n++;
    if (!have_quit) {
        out[n].id = DARLING_MENU_ACTION_QUIT_ID;
        out[n].parent = 0;
        out[n].label = darling_menu_action_label(DARLING_MENU_ACTION_QUIT);
        out[n].flags = DARLING_MENU_ENABLED | DARLING_MENU_VISIBLE;
        out[n].toggle_state = -1;
        n++;
    }
    if (!have_reopen) {
        out[n].id = DARLING_MENU_ACTION_REOPEN_ID;
        out[n].parent = 0;
        out[n].label = darling_menu_action_label(DARLING_MENU_ACTION_REOPEN);
        out[n].flags = DARLING_MENU_ENABLED | DARLING_MENU_VISIBLE;
        out[n].toggle_state = -1;
        n++;
    }
    return n;
}

gboolean darling_menu_action_run(int action) {
    configure();
    if (!action_script) return FALSE;
    const char *name = action == DARLING_MENU_ACTION_QUIT ? "quit"
                      : action == DARLING_MENU_ACTION_REOPEN ? "reopen" : NULL;
    if (!name) return FALSE;
    char *argv[] = {action_script, (char *)name, NULL};
    GPid pid = 0;
    /* The helper outlives this call: it asks the session to stop, which takes
     * longer than a menu interaction. It is reaped by the default context so
     * no zombie is left behind. */
    if (!g_spawn_async(NULL, argv, NULL, G_SPAWN_DO_NOT_REAP_CHILD, NULL, NULL,
                       &pid, NULL)) return FALSE;
    g_child_watch_add(pid, reaped, NULL);
    return TRUE;
}
