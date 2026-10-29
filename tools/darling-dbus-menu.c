/* SPDX-License-Identifier: GPL-3.0-only
 * Native DBusMenu snapshots. All functions run on the item's GLib context.
 * No guest callbacks or client-specific menu items.
 */
#include "darling-dbus-menu.h"
#include <string.h>

#define MENU_IFACE "com.canonical.dbusmenu"
#define MENU_PATH "/Menu"
#define MAX_ENTRIES 1024
#define MAX_DEPTH 32

struct DarlingDBusMenu {
    GDBusConnection *bus; /* borrowed, outlives this object */
    GAsyncQueue *events;
    GDBusNodeInfo *node;
    guint registration, revision, count;
    DarlingStatusMenuEntry *entries;
};

static const char xml[] =
    "<node><interface name='com.canonical.dbusmenu'>"
    "<property name='Version' type='u' access='read'/>"
    "<property name='TextDirection' type='s' access='read'/>"
    "<property name='Status' type='s' access='read'/>"
    "<property name='IconThemePath' type='as' access='read'/>"
    "<method name='GetLayout'><arg type='i' direction='in'/><arg type='i' direction='in'/>"
    "<arg type='as' direction='in'/><arg type='u' direction='out'/><arg type='(ia{sv}av)' direction='out'/></method>"
    "<method name='GetGroupProperties'><arg type='ai' direction='in'/><arg type='as' direction='in'/>"
    "<arg type='a(ia{sv})' direction='out'/></method>"
    "<method name='GetProperty'><arg type='i' direction='in'/><arg type='s' direction='in'/>"
    "<arg type='v' direction='out'/></method>"
    "<method name='Event'><arg type='i' direction='in'/><arg type='s' direction='in'/>"
    "<arg type='v' direction='in'/><arg type='u' direction='in'/></method>"
    "<method name='EventGroup'><arg type='a(isvu)' direction='in'/><arg type='ai' direction='out'/></method>"
    "<method name='AboutToShow'><arg type='i' direction='in'/><arg type='b' direction='out'/></method>"
    "<method name='AboutToShowGroup'><arg type='ai' direction='in'/><arg type='ai' direction='out'/>"
    "<arg type='ai' direction='out'/></method>"
    "<signal name='LayoutUpdated'><arg type='u'/><arg type='i'/></signal>"
    "<signal name='ItemsPropertiesUpdated'><arg type='a(ia{sv})'/><arg type='a(ias)'/></signal>"
    "</interface></node>";

static DarlingStatusMenuEntry *find(DarlingDBusMenu *menu, gint id) {
    for (guint i = 0; i < menu->count; i++)
        if (menu->entries[i].id == id) return &menu->entries[i];
    return NULL;
}

static gboolean children(DarlingDBusMenu *menu, gint id) {
    for (guint i = 0; i < menu->count; i++)
        if (menu->entries[i].parent == id) return TRUE;
    return FALSE;
}

static GVariant *property(DarlingDBusMenu *menu, gint id, const char *key) {
    DarlingStatusMenuEntry *entry = find(menu, id);
    guint flags = entry ? entry->flags : 3;
    if (!strcmp(key, "label")) return g_variant_new_string(entry ? entry->label : "");
    if (!strcmp(key, "enabled")) return g_variant_new_boolean(!!(flags & DARLING_MENU_ENABLED));
    if (!strcmp(key, "visible")) return g_variant_new_boolean(!!(flags & DARLING_MENU_VISIBLE));
    if (!strcmp(key, "type")) return g_variant_new_string(flags & DARLING_MENU_SEPARATOR ? "separator" : "standard");
    if (!strcmp(key, "children-display") && children(menu, id)) return g_variant_new_string("submenu");
    if (!strcmp(key, "toggle-type") && (flags & (DARLING_MENU_CHECK | DARLING_MENU_RADIO)))
        return g_variant_new_string(flags & DARLING_MENU_RADIO ? "radio" : "checkmark");
    if (!strcmp(key, "toggle-state") && (flags & (DARLING_MENU_CHECK | DARLING_MENU_RADIO)))
        return g_variant_new_int32(entry->toggle_state);
    return NULL;
}

static GVariant *properties(DarlingDBusMenu *menu, gint id, const gchar **requested) {
    const char *all[] = {"label", "enabled", "visible", "type", "children-display",
                         "toggle-type", "toggle-state", NULL};
    const char **keys = requested && *requested ? requested : all;
    GVariantBuilder builder;
    g_variant_builder_init(&builder, G_VARIANT_TYPE("a{sv}"));
    for (guint i = 0; keys[i]; i++) {
        GVariant *value = property(menu, id, keys[i]);
        if (value) g_variant_builder_add(&builder, "{sv}", keys[i], value);
    }
    return g_variant_builder_end(&builder);
}

static GVariant *layout(DarlingDBusMenu *menu, gint id, gint depth, const gchar **keys) {
    GVariantBuilder builder;
    g_variant_builder_init(&builder, G_VARIANT_TYPE("av"));
    if (depth != 0) {
        for (guint i = 0; i < menu->count; i++) {
            DarlingStatusMenuEntry *entry = &menu->entries[i];
            if (entry->parent == id)
                g_variant_builder_add(&builder, "v", layout(menu, entry->id,
                                     depth < 0 ? -1 : depth - 1, keys));
        }
    }
    return g_variant_new("(i@a{sv}@av)", id, properties(menu, id, keys),
                         g_variant_builder_end(&builder));
}

static void enqueue(DarlingDBusMenu *menu, gint kind, gint id) {
    DarlingStatusEvent *event = g_new0(DarlingStatusEvent, 1);
    event->kind = kind;
    event->x = id;
    g_async_queue_lock(menu->events);
    if (g_async_queue_length_unlocked(menu->events) >= 128)
        g_free(g_async_queue_try_pop_unlocked(menu->events));
    g_async_queue_push_unlocked(menu->events, event);
    g_async_queue_unlock(menu->events);
}

static gboolean event_received(DarlingDBusMenu *menu, gint id, const char *name) {
    DarlingStatusMenuEntry *entry = find(menu, id);
    if (!strcmp(name, "opened") || !strcmp(name, "closed")) {
        if (id && !entry) return FALSE;
        if (id && !children(menu, id)) return FALSE;
        enqueue(menu, !strcmp(name, "opened") ? DARLING_STATUS_MENU_OPEN : DARLING_STATUS_MENU_CLOSE, id);
        return TRUE;
    }
    if (!entry) return FALSE;
    if (!strcmp(name, "clicked") && !(entry->flags & DARLING_MENU_SEPARATOR) && !children(menu, id)) {
        gboolean allowed = TRUE;
        for (DarlingStatusMenuEntry *ancestor = entry; ancestor;
             ancestor = find(menu, ancestor->parent)) {
            if ((ancestor->flags & 3) != 3) allowed = FALSE;
        }
        if (allowed) enqueue(menu, DARLING_STATUS_MENU_CLICK, id);
    }
    return TRUE;
}

static GVariant *menu_property(GDBusConnection *bus, const gchar *sender,
        const gchar *path, const gchar *interface, const gchar *name,
        GError **error, gpointer data) {
    (void)bus; (void)sender; (void)path; (void)interface; (void)error; (void)data;
    if (!strcmp(name, "Version")) return g_variant_new_uint32(3);
    if (!strcmp(name, "TextDirection")) return g_variant_new_string("ltr");
    if (!strcmp(name, "Status")) return g_variant_new_string("normal");
    return g_variant_new_strv(NULL, 0);
}

static void called(GDBusConnection *bus, const gchar *sender, const gchar *path,
        const gchar *interface, const gchar *method, GVariant *args,
        GDBusMethodInvocation *invocation, gpointer data) {
    (void)bus; (void)sender; (void)path; (void)interface;
    DarlingDBusMenu *menu = data;
    gint id = 0;
    if (!strcmp(method, "GetLayout")) {
        gint depth;
        const gchar **keys;
        g_variant_get(args, "(ii^a&s)", &id, &depth, &keys);
        if ((id && !find(menu, id)) || depth < -1) {
            g_free(keys);
            goto invalid;
        }
        GVariant *result = g_variant_new("(u@(ia{sv}av))", menu->revision,
                                        layout(menu, id, depth, keys));
        g_free(keys);
        g_dbus_method_invocation_return_value(invocation, result);
    } else if (!strcmp(method, "GetProperty")) {
        const char *key;
        g_variant_get(args, "(i&s)", &id, &key);
        if (id && !find(menu, id)) goto invalid;
        GVariant *value = property(menu, id, key);
        if (!value) goto invalid;
        g_dbus_method_invocation_return_value(invocation, g_variant_new("(v)", value));
    } else if (!strcmp(method, "GetGroupProperties")) {
        GVariant *ids;
        const gchar **keys;
        g_variant_get(args, "(@ai^a&s)", &ids, &keys);
        GVariantBuilder builder;
        g_variant_builder_init(&builder, G_VARIANT_TYPE("a(ia{sv})"));
        GVariantIter iter;
        g_variant_iter_init(&iter, ids);
        if (!g_variant_n_children(ids)) {
            g_variant_builder_add(&builder, "(i@a{sv})", 0, properties(menu, 0, keys));
            for (guint i = 0; i < menu->count; i++)
                g_variant_builder_add(&builder, "(i@a{sv})", menu->entries[i].id,
                                      properties(menu, menu->entries[i].id, keys));
        }
        while (g_variant_iter_next(&iter, "i", &id))
            if (!id || find(menu, id))
                g_variant_builder_add(&builder, "(i@a{sv})", id, properties(menu, id, keys));
        g_free(keys);
        g_variant_unref(ids);
        g_dbus_method_invocation_return_value(invocation, g_variant_new("(a(ia{sv}))", &builder));
    } else if (!strcmp(method, "Event")) {
        const char *name;
        GVariant *value;
        guint timestamp;
        g_variant_get(args, "(i&s@vu)", &id, &name, &value, &timestamp);
        gboolean valid = event_received(menu, id, name);
        g_variant_unref(value);
        if (!valid) goto invalid;
        g_dbus_method_invocation_return_value(invocation, NULL);
    } else if (!strcmp(method, "EventGroup")) {
        GVariant *events = g_variant_get_child_value(args, 0);
        GVariantIter iter;
        GVariantBuilder errors;
        g_variant_builder_init(&errors, G_VARIANT_TYPE("ai"));
        g_variant_iter_init(&iter, events);
        const char *name;
        GVariant *value;
        guint timestamp;
        while (g_variant_iter_next(&iter, "(i&s@vu)", &id, &name, &value, &timestamp)) {
            if (!event_received(menu, id, name)) g_variant_builder_add(&errors, "i", id);
            g_variant_unref(value);
        }
        g_variant_unref(events);
        g_dbus_method_invocation_return_value(invocation, g_variant_new("(ai)", &errors));
    } else if (!strcmp(method, "AboutToShow")) {
        g_variant_get(args, "(i)", &id);
        if (id && !find(menu, id)) goto invalid;
        enqueue(menu, DARLING_STATUS_MENU_OPEN, id);
        // Never wait for guest main-thread work on this native thread. The
        // owner may publish a refreshed snapshot and LayoutUpdated afterward.
        g_dbus_method_invocation_return_value(invocation, g_variant_new("(b)", FALSE));
    } else if (!strcmp(method, "AboutToShowGroup")) {
        GVariant *ids = g_variant_get_child_value(args, 0);
        GVariantBuilder updates, errors;
        g_variant_builder_init(&updates, G_VARIANT_TYPE("ai"));
        g_variant_builder_init(&errors, G_VARIANT_TYPE("ai"));
        GVariantIter iter;
        g_variant_iter_init(&iter, ids);
        while (g_variant_iter_next(&iter, "i", &id)) {
            if (id && !find(menu, id)) g_variant_builder_add(&errors, "i", id);
            else enqueue(menu, DARLING_STATUS_MENU_OPEN, id);
        }
        g_variant_unref(ids);
        g_dbus_method_invocation_return_value(invocation, g_variant_new("(aiai)", &updates, &errors));
    } else {
        g_dbus_method_invocation_return_error(invocation, G_DBUS_ERROR,
            G_DBUS_ERROR_UNKNOWN_METHOD, "Unknown menu method");
    }
    return;
invalid:
    g_dbus_method_invocation_return_error(invocation, G_DBUS_ERROR,
        G_DBUS_ERROR_INVALID_ARGS, "Unknown item/property or invalid layout depth");
}

static const GDBusInterfaceVTable vtable = {.method_call = called, .get_property = menu_property};

DarlingDBusMenu *darling_menu_create(GDBusConnection *bus, GAsyncQueue *events) {
    DarlingDBusMenu *menu = g_new0(DarlingDBusMenu, 1);
    menu->bus = bus;
    menu->events = events;
    menu->node = g_dbus_node_info_new_for_xml(xml, NULL);
    if (menu->node)
        menu->registration = g_dbus_connection_register_object(bus, MENU_PATH,
            menu->node->interfaces[0], &vtable, menu, NULL, NULL);
    if (!menu->registration) {
        darling_menu_destroy(menu);
        return NULL;
    }
    return menu;
}

static void free_entries(DarlingStatusMenuEntry *entries, guint count) {
    for (guint i = 0; i < count; i++) g_free((gpointer)entries[i].label);
    g_free(entries);
}

int darling_menu_set(DarlingDBusMenu *menu, const DarlingStatusMenuEntry *entries, guint count) {
    if (!menu || count > MAX_ENTRIES || (count && !entries)) return 0;
    guint depths[MAX_ENTRIES];
    for (guint i = 0; i < count; i++) {
        const DarlingStatusMenuEntry *entry = &entries[i];
        if (entry->id <= 0 || entry->parent < 0 || !entry->label ||
            strlen(entry->label) > 4096 || !g_utf8_validate(entry->label, -1, NULL) ||
            (entry->flags & ~31u) || (entry->flags & 24u) == 24u ||
            entry->toggle_state < -1 || entry->toggle_state > 1) return 0;
        depths[i] = 1;
        gboolean parent_found = !entry->parent;
        for (guint j = 0; j < i; j++) {
            if (entries[j].id == entry->id) return 0;
            if (entries[j].id == entry->parent) {
                if (entries[j].flags & DARLING_MENU_SEPARATOR) return 0;
                parent_found = TRUE;
                depths[i] = depths[j] + 1;
            }
        }
        if (!parent_found || depths[i] > MAX_DEPTH) return 0;
    }
    gboolean unchanged = menu->count == count;
    for (guint i = 0; unchanged && i < count; i++) {
        DarlingStatusMenuEntry *old = &menu->entries[i];
        const DarlingStatusMenuEntry *entry = &entries[i];
        unchanged = old->id == entry->id && old->parent == entry->parent &&
                    old->flags == entry->flags && old->toggle_state == entry->toggle_state &&
                    !strcmp(old->label, entry->label);
    }
    if (unchanged) return 1;
    DarlingStatusMenuEntry *copy = g_new0(DarlingStatusMenuEntry, count);
    for (guint i = 0; i < count; i++) {
        copy[i] = entries[i];
        copy[i].label = g_strdup(entries[i].label);
    }
    free_entries(menu->entries, menu->count);
    menu->entries = copy;
    menu->count = count;
    menu->revision++;
    g_dbus_connection_emit_signal(menu->bus, NULL, MENU_PATH, MENU_IFACE,
        "LayoutUpdated", g_variant_new("(ui)", menu->revision, 0), NULL);
    return 1;
}

gboolean darling_menu_active(DarlingDBusMenu *menu) { return menu && menu->count > 0; }

void darling_menu_destroy(DarlingDBusMenu *menu) {
    if (!menu) return;
    if (menu->registration) g_dbus_connection_unregister_object(menu->bus, menu->registration);
    if (menu->node) g_dbus_node_info_unref(menu->node);
    free_entries(menu->entries, menu->count);
    g_free(menu);
}
