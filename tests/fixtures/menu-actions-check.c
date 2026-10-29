/* SPDX-License-Identifier: GPL-3.0-only
 * Offline check of the host-side menu actions. Prints one key=value line per
 * observation, so the test can assert on the behaviour without a desktop.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "darling-menu-actions.h"

static DarlingStatusMenuEntry guest[2];

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "disabled";
    if (!strcmp(mode, "enabled") || !strcmp(mode, "guest-has-quit") ||
        !strcmp(mode, "guest-has-both") || !strcmp(mode, "custom-labels")) {
        setenv("DARLING_STATUS_MENU_ACTION_SCRIPT", "/bin/true", 1);
    }
    if (!strcmp(mode, "custom-labels")) {
        setenv("DARLING_STATUS_MENU_QUIT_LABEL", "Encerrar", 1);
        setenv("DARLING_STATUS_MENU_REOPEN_LABEL", "Abrir Riot", 1);
    }
    printf("enabled=%d\n", darling_menu_actions_enabled() ? 1 : 0);
    printf("quit=%d\n", darling_menu_action_for_label("Sair"));
    printf("reopen=%d\n", darling_menu_action_for_label("Riot Games"));
    printf("other=%d\n", darling_menu_action_for_label("Configurações"));
    printf("custom_quit=%d\n", darling_menu_action_for_label("Encerrar"));
    printf("custom_reopen=%d\n", darling_menu_action_for_label("Abrir Riot"));
    printf("quit_label=%s\n", darling_menu_action_label(DARLING_MENU_ACTION_QUIT));
    printf("reopen_label=%s\n", darling_menu_action_label(DARLING_MENU_ACTION_REOPEN));

    guint count = 0;
    if (!strcmp(mode, "guest-has-quit")) {
        guest[0].id = 7;
        guest[0].parent = 0;
        guest[0].label = "Sair";
        guest[0].flags = DARLING_MENU_ENABLED | DARLING_MENU_VISIBLE;
        guest[0].toggle_state = -1;
        count = 1;
    } else if (!strcmp(mode, "guest-has-both")) {
        guest[0].id = 7;
        guest[0].parent = 0;
        guest[0].label = "Sair";
        guest[0].flags = DARLING_MENU_ENABLED | DARLING_MENU_VISIBLE;
        guest[0].toggle_state = -1;
        guest[1].id = 8;
        guest[1].parent = 0;
        guest[1].label = "Riot Games";
        guest[1].flags = DARLING_MENU_ENABLED | DARLING_MENU_VISIBLE;
        guest[1].toggle_state = -1;
        count = 2;
    }
    DarlingStatusMenuEntry out[4];
    guint written = darling_menu_action_entries(guest, count, out, 4);
    printf("written=%u\n", written);
    for (guint i = 0; i < written; i++)
        printf("entry=%u:%u:%u:%s\n", out[i].id, out[i].parent, out[i].flags,
               out[i].label ? out[i].label : "");
    return 0;
}
