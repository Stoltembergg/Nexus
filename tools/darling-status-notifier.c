/* SPDX-License-Identifier: GPL-3.0-only
 * Linux StatusNotifierItem transport for a future NSStatusItem backend.
 * Original integration code; no client assets, process inspection or game APIs.
 */
#include "darling-status-notifier.h"
#include "darling-dbus-menu.h"
#include <gio/gio.h>
#include <string.h>

#define ITEM_PATH "/StatusNotifierItem"
#define ITEM_INTERFACE "org.kde.StatusNotifierItem"
#define WATCHER "org.kde.StatusNotifierWatcher"
#define MAX_EVENTS 128

struct DarlingStatusNotifier {
    GMainContext *context;
    GMainLoop *loop;
    GThread *thread;
    GDBusConnection *bus;
    GDBusNodeInfo *introspection;
    guint registration, watcher;
    GMutex mutex;
    GCond ready_cond;
    gboolean ready, usable;
    gchar *id, *title, *tooltip, *icon_name, *bus_name;
    GBytes *pixels;
    guint width, height;
    GAsyncQueue *events;
    DarlingDBusMenu *menu;
};

static const char xml[] =
    "<node><interface name='org.kde.StatusNotifierItem'>"
    "<method name='Activate'><arg type='i' direction='in'/><arg type='i' direction='in'/></method>"
    "<method name='SecondaryActivate'><arg type='i' direction='in'/><arg type='i' direction='in'/></method>"
    "<method name='ContextMenu'><arg type='i' direction='in'/><arg type='i' direction='in'/></method>"
    "<method name='Scroll'><arg type='i' direction='in'/><arg type='s' direction='in'/></method>"
    "<property name='Category' type='s' access='read'/>"
    "<property name='Id' type='s' access='read'/>"
    "<property name='Title' type='s' access='read'/>"
    "<property name='Status' type='s' access='read'/>"
    "<property name='WindowId' type='u' access='read'/>"
    "<property name='IconName' type='s' access='read'/>"
    "<property name='IconPixmap' type='a(iiay)' access='read'/>"
    "<property name='OverlayIconName' type='s' access='read'/>"
    "<property name='OverlayIconPixmap' type='a(iiay)' access='read'/>"
    "<property name='AttentionIconName' type='s' access='read'/>"
    "<property name='AttentionIconPixmap' type='a(iiay)' access='read'/>"
    "<property name='AttentionMovieName' type='s' access='read'/>"
    "<property name='ToolTip' type='(sa(iiay)ss)' access='read'/>"
    "<property name='ItemIsMenu' type='b' access='read'/>"
    "<property name='Menu' type='o' access='read'/>"
    "<signal name='NewTitle'/><signal name='NewIcon'/>"
    "<signal name='NewToolTip'/><signal name='NewMenu'/><signal name='NewStatus'><arg type='s'/></signal>"
    "</interface></node>";

static gboolean valid_text(const char *text) {
    return text && strlen(text) <= 4096 && g_utf8_validate(text, -1, NULL);
}

static GVariant *pixmap(DarlingStatusNotifier *item, gboolean include_icon) {
    GVariantBuilder builder;
    g_variant_builder_init(&builder, G_VARIANT_TYPE("a(iiay)"));
    if (include_icon && item->pixels) {
        gsize size;
        const guint8 *bytes = g_bytes_get_data(item->pixels, &size);
        GVariant *data = g_variant_new_fixed_array(G_VARIANT_TYPE_BYTE, bytes, size, 1);
        g_variant_builder_add(&builder, "(ii@ay)", (gint)item->width, (gint)item->height, data);
    }
    return g_variant_builder_end(&builder);
}

static GVariant *get_property(GDBusConnection *connection, const gchar *sender,
                              const gchar *path, const gchar *interface,
                              const gchar *property, GError **error, gpointer data) {
    (void)connection; (void)sender; (void)path; (void)interface; (void)error;
    DarlingStatusNotifier *item = data;
    if (!strcmp(property, "Category")) return g_variant_new_string("ApplicationStatus");
    if (!strcmp(property, "Id")) return g_variant_new_string(item->id);
    if (!strcmp(property, "Title")) return g_variant_new_string(item->title);
    if (!strcmp(property, "Status")) return g_variant_new_string("Active");
    if (!strcmp(property, "WindowId")) return g_variant_new_uint32(0);
    if (!strcmp(property, "IconName")) return g_variant_new_string(item->icon_name);
    if (!strcmp(property, "IconPixmap")) return pixmap(item, TRUE);
    if (!strcmp(property, "OverlayIconPixmap") || !strcmp(property, "AttentionIconPixmap"))
        return pixmap(item, FALSE);
    if (!strcmp(property, "ToolTip"))
        return g_variant_new("(s@a(iiay)ss)", item->icon_name, pixmap(item, TRUE),
                             item->tooltip ? item->tooltip : item->title, "");
    if (!strcmp(property, "ItemIsMenu")) return g_variant_new_boolean(FALSE);
    if (!strcmp(property, "Menu"))
        return g_variant_new_object_path(darling_menu_active(item->menu) ? "/Menu" : "/");
    return g_variant_new_string("");
}

static void method_call(GDBusConnection *connection, const gchar *sender,
                         const gchar *path, const gchar *interface,
                         const gchar *method, GVariant *parameters,
                         GDBusMethodInvocation *invocation, gpointer data) {
    (void)connection; (void)sender; (void)path; (void)interface;
    DarlingStatusNotifier *item = data;
    DarlingStatusEvent event = {0};
    if (!strcmp(method, "Scroll")) {
        const gchar *orientation;
        g_variant_get(parameters, "(i&s)", &event.delta, &orientation);
        if (strcmp(orientation, "horizontal") && strcmp(orientation, "vertical")) {
            g_dbus_method_invocation_return_error(invocation, G_DBUS_ERROR,
                G_DBUS_ERROR_INVALID_ARGS, "Expected horizontal or vertical");
            return;
        }
        event.kind = DARLING_STATUS_SCROLL;
        event.horizontal = !strcmp(orientation, "horizontal");
    } else {
        g_variant_get(parameters, "(ii)", &event.x, &event.y);
        if (!strcmp(method, "Activate")) event.kind = DARLING_STATUS_ACTIVATE;
        else if (!strcmp(method, "SecondaryActivate")) event.kind = DARLING_STATUS_SECONDARY_ACTIVATE;
        else if (!strcmp(method, "ContextMenu")) event.kind = DARLING_STATUS_CONTEXT_MENU;
        else {
            g_dbus_method_invocation_return_error(invocation, G_DBUS_ERROR,
                G_DBUS_ERROR_UNKNOWN_METHOD, "Unknown status-item method");
            return;
        }
    }
    DarlingStatusEvent *copy = g_memdup2(&event, sizeof(event));
    g_async_queue_lock(item->events);
    if (g_async_queue_length_unlocked(item->events) >= MAX_EVENTS)
        g_free(g_async_queue_try_pop_unlocked(item->events));
    g_async_queue_push_unlocked(item->events, copy);
    g_async_queue_unlock(item->events);
    g_dbus_method_invocation_return_value(invocation, NULL);
}

static const GDBusInterfaceVTable vtable = {
    .method_call = method_call, .get_property = get_property
};

static void watcher_appeared(GDBusConnection *bus, const gchar *name,
                             const gchar *owner, gpointer data) {
    (void)name; (void)owner;
    DarlingStatusNotifier *item = data;
    /* Asynchronous: a missing or unresponsive panel must not block AppKit.
     * The name watch also handles a panel restarting while the app stays up.
     */
    g_dbus_connection_call(bus, WATCHER, "/StatusNotifierWatcher", WATCHER,
        "RegisterStatusNotifierItem", g_variant_new("(s)", item->bus_name),
        NULL, G_DBUS_CALL_FLAGS_NONE, 5000, NULL, NULL, NULL);
}

static gpointer bus_thread(gpointer data) {
    DarlingStatusNotifier *item = data;
    GError *error = NULL;
    g_main_context_push_thread_default(item->context);
    gchar *address = g_dbus_address_get_for_bus_sync(G_BUS_TYPE_SESSION, NULL, &error);
    if (address) {
        item->bus = g_dbus_connection_new_for_address_sync(address,
            G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT |
            G_DBUS_CONNECTION_FLAGS_MESSAGE_BUS_CONNECTION, NULL, NULL, &error);
        g_free(address);
    }
    if (item->bus) {
        g_dbus_connection_set_exit_on_close(item->bus, FALSE);
        item->introspection = g_dbus_node_info_new_for_xml(xml, &error);
        if (item->introspection)
            item->registration = g_dbus_connection_register_object(item->bus, ITEM_PATH,
                item->introspection->interfaces[0], &vtable, item, NULL, &error);
        if (item->registration) {
            item->menu = darling_menu_create(item->bus, item->events);
            item->bus_name = g_strdup(g_dbus_connection_get_unique_name(item->bus));
            item->watcher = g_bus_watch_name_on_connection(item->bus, WATCHER,
                G_BUS_NAME_WATCHER_FLAGS_NONE, watcher_appeared, NULL, item, NULL);
        }
    }
    g_clear_error(&error);
    g_mutex_lock(&item->mutex);
    item->usable = item->registration != 0;
    item->ready = TRUE;
    g_cond_signal(&item->ready_cond);
    g_mutex_unlock(&item->mutex);
    if (item->usable) g_main_loop_run(item->loop);
    if (item->watcher) g_bus_unwatch_name(item->watcher);
    darling_menu_destroy(item->menu);
    if (item->registration) g_dbus_connection_unregister_object(item->bus, item->registration);
    if (item->bus) {
        g_dbus_connection_close_sync(item->bus, NULL, NULL);
        g_object_unref(item->bus);
    }
    if (item->introspection) g_dbus_node_info_unref(item->introspection);
    g_main_context_pop_thread_default(item->context);
    return NULL;
}

DarlingStatusNotifier *DarlingStatusNotifierCreate(const char *id, const char *title,
                                                   const char *icon_name) {
    if (!valid_text(id) || !*id || !valid_text(title) || !valid_text(icon_name)) return NULL;
    DarlingStatusNotifier *item = g_new0(DarlingStatusNotifier, 1);
    item->id = g_strdup(id);
    item->title = g_strdup(title);
    item->icon_name = g_strdup(icon_name);
    g_mutex_init(&item->mutex);
    g_cond_init(&item->ready_cond);
    item->events = g_async_queue_new_full(g_free);
    item->context = g_main_context_new();
    item->loop = g_main_loop_new(item->context, FALSE);
    item->thread = g_thread_new("darling-status", bus_thread, item);
    g_mutex_lock(&item->mutex);
    while (!item->ready) g_cond_wait(&item->ready_cond, &item->mutex);
    gboolean usable = item->usable;
    g_mutex_unlock(&item->mutex);
    if (!usable) {
        DarlingStatusNotifierDestroy(item);
        return NULL;
    }
    return item;
}

typedef struct {
    DarlingStatusNotifier *item;
    const char *text;
    GBytes *pixels;
    guint width, height;
    int operation;
    GMutex mutex;
    GCond cond;
    gboolean done;
    const DarlingStatusMenuEntry *entries;
    guint count;
    int result;
} Update;

static gboolean update_item(gpointer data) {
    Update *update = data;
    DarlingStatusNotifier *item = update->item;
    const char *signal_name = NULL;
    if (update->operation == 0) {
        g_main_loop_quit(item->loop);
    } else if (update->operation == 1) {
        g_free(item->title);
        item->title = g_strdup(update->text);
        signal_name = "NewTitle";
    } else if (update->operation == 2) {
        g_free(item->icon_name);
        item->icon_name = g_strdup(update->text);
        signal_name = "NewIcon";
    } else if (update->operation == 4) {
        g_free(item->tooltip);
        item->tooltip = g_strdup(update->text);
        signal_name = "NewToolTip";
    } else if (update->operation == 5) {
        gboolean previous = darling_menu_active(item->menu);
        update->result = darling_menu_set(item->menu, update->entries, update->count);
        if (update->result && previous != darling_menu_active(item->menu)) {
            GVariantBuilder changed, invalidated;
            g_variant_builder_init(&changed, G_VARIANT_TYPE("a{sv}"));
            g_variant_builder_add(&changed, "{sv}", "Menu", g_variant_new_object_path(
                darling_menu_active(item->menu) ? "/Menu" : "/"));
            g_variant_builder_init(&invalidated, G_VARIANT_TYPE("as"));
            g_dbus_connection_emit_signal(item->bus, NULL, ITEM_PATH,
                "org.freedesktop.DBus.Properties", "PropertiesChanged",
                g_variant_new("(sa{sv}as)", ITEM_INTERFACE, &changed, &invalidated), NULL);
            g_dbus_connection_emit_signal(item->bus, NULL, ITEM_PATH,
                ITEM_INTERFACE, "NewMenu", NULL, NULL);
        }
    } else {
        g_clear_pointer(&item->pixels, g_bytes_unref);
        item->pixels = update->pixels ? g_bytes_ref(update->pixels) : NULL;
        item->width = update->width;
        item->height = update->height;
        signal_name = "NewIcon";
    }
    if (signal_name && !g_dbus_connection_is_closed(item->bus)) {
        g_dbus_connection_emit_signal(item->bus, NULL, ITEM_PATH,
            ITEM_INTERFACE, signal_name, NULL, NULL);
        if (strcmp(signal_name, "NewToolTip"))
            g_dbus_connection_emit_signal(item->bus, NULL, ITEM_PATH,
                ITEM_INTERFACE, "NewToolTip", NULL, NULL);
    }
    g_mutex_lock(&update->mutex);
    update->done = TRUE;
    g_cond_signal(&update->cond);
    g_mutex_unlock(&update->mutex);
    return G_SOURCE_REMOVE;
}

static void sync_update(Update *update) {
    g_mutex_init(&update->mutex);
    g_cond_init(&update->cond);
    g_mutex_lock(&update->mutex);
    g_main_context_invoke(update->item->context, update_item, update);
    while (!update->done) g_cond_wait(&update->cond, &update->mutex);
    g_mutex_unlock(&update->mutex);
    g_cond_clear(&update->cond);
    g_mutex_clear(&update->mutex);
}

void DarlingStatusNotifierSetTitle(DarlingStatusNotifier *item, const char *title) {
    if (!item || !valid_text(title)) return;
    Update update = {.item = item, .text = title, .operation = 1};
    sync_update(&update);
}

void DarlingStatusNotifierSetToolTip(DarlingStatusNotifier *item, const char *tooltip) {
    if (!item || !valid_text(tooltip)) return;
    Update update = {.item = item, .text = tooltip, .operation = 4};
    sync_update(&update);
}

void DarlingStatusNotifierSetIconName(DarlingStatusNotifier *item, const char *name) {
    if (!item || !valid_text(name)) return;
    Update update = {.item = item, .text = name, .operation = 2};
    sync_update(&update);
}

int DarlingStatusNotifierSetMenu(DarlingStatusNotifier *item,
                                const DarlingStatusMenuEntry *entries, uint32_t count) {
    if (!item || count > 1024 || (count && !entries)) return 0;
    Update update = {.item = item, .entries = entries, .count = count, .operation = 5};
    sync_update(&update);
    return update.result;
}

int DarlingStatusNotifierSetIcon(DarlingStatusNotifier *item, uint32_t width,
                                  uint32_t height, const uint8_t *argb) {
    if (!item || width > 256 || height > 256) return 0;
    if ((!width || !height) && (width || height || argb)) return 0;
    if (width && !argb) return 0;
    GBytes *bytes = argb ? g_bytes_new(argb, (gsize)width * height * 4) : NULL;
    Update update = {.item = item, .pixels = bytes, .width = width,
                     .height = height, .operation = 3};
    sync_update(&update);
    if (bytes) g_bytes_unref(bytes);
    return 1;
}

int DarlingStatusNotifierPoll(DarlingStatusNotifier *item, DarlingStatusEvent *event) {
    if (!item || !event) return 0;
    DarlingStatusEvent *next = g_async_queue_try_pop(item->events);
    if (!next) return 0;
    *event = *next;
    g_free(next);
    return 1;
}

const char *DarlingStatusNotifierBusName(DarlingStatusNotifier *item) {
    return item ? item->bus_name : NULL;
}

void DarlingStatusNotifierDestroy(DarlingStatusNotifier *item) {
    if (!item) return;
    if (item->usable) {
        Update update = {.item = item, .operation = 0};
        sync_update(&update);
    }
    g_thread_join(item->thread);
    g_main_loop_unref(item->loop);
    g_main_context_unref(item->context);
    g_async_queue_unref(item->events);
    g_clear_pointer(&item->pixels, g_bytes_unref);
    g_free(item->id); g_free(item->title); g_free(item->tooltip);
    g_free(item->icon_name); g_free(item->bus_name);
    g_cond_clear(&item->ready_cond);
    g_mutex_clear(&item->mutex);
    g_free(item);
}
