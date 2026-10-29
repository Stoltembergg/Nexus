/* SPDX-License-Identifier: GPL-3.0-only
 * Isolated fake panel. Never run this on a user's desktop session bus.
 */
#include <gio/gio.h>
#include <stdio.h>

static const char xml[] =
    "<node><interface name='org.kde.StatusNotifierWatcher'>"
    "<method name='RegisterStatusNotifierItem'><arg type='s' direction='in'/></method>"
    "</interface></node>";

static void menu_changed(GDBusConnection *bus, const gchar *sender, const gchar *path,
                          const gchar *interface, const gchar *signal,
                          GVariant *args, gpointer data) {
    (void)bus; (void)path; (void)interface; (void)signal; (void)args; (void)data;
    printf("NEW_MENU %s\n", sender);
    fflush(stdout);
}

static void called(GDBusConnection *bus, const gchar *sender, const gchar *path,
                    const gchar *interface, const gchar *method, GVariant *args,
                    GDBusMethodInvocation *invocation, gpointer data) {
    (void)bus; (void)sender; (void)path; (void)interface; (void)method; (void)data;
    const gchar *name;
    g_variant_get(args, "(&s)", &name);
    g_dbus_connection_signal_subscribe(bus, name, "org.kde.StatusNotifierItem", "NewMenu",
        "/StatusNotifierItem", NULL, G_DBUS_SIGNAL_FLAGS_NONE, menu_changed, NULL, NULL);
    printf("REGISTER %s\n", name);
    fflush(stdout);
    g_dbus_method_invocation_return_value(invocation, NULL);
}

static const GDBusInterfaceVTable vtable = {.method_call = called};

static void acquired(GDBusConnection *bus, const gchar *name, gpointer data) {
    (void)bus; (void)name; (void)data;
    puts("READY");
    fflush(stdout);
}

int main(void) {
    GError *error = NULL;
    GDBusConnection *bus = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, &error);
    if (!bus) return 1;
    GDBusNodeInfo *node = g_dbus_node_info_new_for_xml(xml, &error);
    if (!node || !g_dbus_connection_register_object(bus, "/StatusNotifierWatcher",
            node->interfaces[0], &vtable, NULL, NULL, &error)) return 2;
    g_bus_own_name_on_connection(bus, "org.kde.StatusNotifierWatcher",
        G_BUS_NAME_OWNER_FLAGS_NONE, acquired, NULL, NULL, NULL);
    g_main_loop_run(g_main_loop_new(NULL, FALSE));
    return 0;
}
