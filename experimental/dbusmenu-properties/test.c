/* Private, in-process capture of the exact GDBus signal payloads. */
#include <gio/gio.h>
static GPtrArray *signals;
static GPtrArray *payloads;
static gboolean capture(GDBusConnection *bus, const gchar *destination, const gchar *path,
                        const gchar *interface, const gchar *name, GVariant *parameters,
                        GError **error) {
    (void)bus; (void)destination; (void)path; (void)interface; (void)error;
    g_ptr_array_add(signals, g_strdup(name));
    g_ptr_array_add(payloads, g_variant_ref_sink(parameters));
    return TRUE;
}
#define g_dbus_connection_emit_signal capture
#include "darling-dbus-menu.c"
#undef g_dbus_connection_emit_signal

static void reset(void) { g_ptr_array_set_size(signals, 0); g_ptr_array_set_size(payloads, 0); }
static void expect_name(guint index, const char *name) {
    g_assert_cmpstr(g_ptr_array_index(signals, index), ==, name);
}
static GVariant *item(GVariant *array, gint id) {
    for (gsize i = 0; i < g_variant_n_children(array); i++) {
        GVariant *row = g_variant_get_child_value(array, i);
        gint found; g_variant_get_child(row, 0, "i", &found);
        if (found == id) { GVariant *v = g_variant_get_child_value(row, 1); g_variant_unref(row); return v; }
        g_variant_unref(row);
    }
    return NULL;
}
int main(void) {
    signals = g_ptr_array_new_with_free_func(g_free);
    payloads = g_ptr_array_new_with_free_func((GDestroyNotify)g_variant_unref);
    DarlingDBusMenu menu = {0};
    DarlingStatusMenuEntry entries[] = {{10, 0, "old", 3, 0}, {20, 0, "two", 3, 0}};
    g_assert_true(darling_menu_set(&menu, entries, 2));
    g_assert_cmpuint(signals->len, ==, 2); expect_name(0, "LayoutUpdated"); expect_name(1, "ItemsPropertiesUpdated");
    guint32 rev; gint parent;
    g_variant_get(g_ptr_array_index(payloads, 0), "(ui)", &rev, &parent);
    g_assert_cmpuint(rev, ==, 1); g_assert_cmpint(parent, ==, 0);
    GVariant *first = g_ptr_array_index(payloads, 1);
    GVariant *updates = g_variant_get_child_value(first, 0);
    g_assert_cmpuint(g_variant_n_children(updates), ==, 1);
    GVariant *root = item(updates, 0); g_assert_nonnull(root); g_variant_unref(root); g_variant_unref(updates);
    reset();
    g_assert_true(darling_menu_set(&menu, entries, 2)); g_assert_cmpuint(signals->len, ==, 0);
    entries[0].label = "new"; entries[0].flags = DARLING_MENU_SEPARATOR | DARLING_MENU_CHECK;
    entries[0].toggle_state = 1;
    entries[1].label = "second";
    g_assert_true(darling_menu_set(&menu, entries, 2));
    g_assert_cmpuint(signals->len, ==, 2); expect_name(0, "LayoutUpdated"); expect_name(1, "ItemsPropertiesUpdated");
    g_variant_get(g_ptr_array_index(payloads, 0), "(ui)", &rev, &parent);
    g_assert_cmpuint(rev, ==, 2); g_assert_cmpint(parent, ==, 0);
    GVariant *payload = g_ptr_array_index(payloads, 1);
    g_assert_true(g_variant_is_of_type(payload, G_VARIANT_TYPE("(a(ia{sv})a(ias))")));
    updates = g_variant_get_child_value(payload, 0);
    g_assert_cmpuint(g_variant_n_children(updates), ==, 2);
    GVariant *row = g_variant_get_child_value(updates, 0); gint id;
    g_variant_get_child(row, 0, "i", &id); g_assert_cmpint(id, ==, 10); g_variant_unref(row);
    GVariant *props = item(updates, 10); const char *s; gboolean b; gint32 state;
    g_assert_true(g_variant_lookup(props, "label", "&s", &s)); g_assert_cmpstr(s, ==, "new");
    g_assert_true(g_variant_lookup(props, "enabled", "b", &b)); g_assert_false(b);
    g_assert_true(g_variant_lookup(props, "visible", "b", &b)); g_assert_false(b);
    g_assert_true(g_variant_lookup(props, "type", "&s", &s)); g_assert_cmpstr(s, ==, "separator");
    g_assert_true(g_variant_lookup(props, "toggle-type", "&s", &s)); g_assert_cmpstr(s, ==, "checkmark");
    g_assert_true(g_variant_lookup(props, "toggle-state", "i", &state)); g_assert_cmpint(state, ==, 1);
    g_variant_unref(props); g_variant_unref(updates); reset();
    entries[0].flags = 3; entries[0].toggle_state = 0;
    g_assert_true(darling_menu_set(&menu, entries, 2));
    g_assert_cmpuint(signals->len, ==, 2); expect_name(0, "LayoutUpdated"); expect_name(1, "ItemsPropertiesUpdated");
    payload = g_ptr_array_index(payloads, 1); GVariant *removed = g_variant_get_child_value(payload, 1);
    updates = g_variant_get_child_value(payload, 0); props = item(updates, 10);
    g_assert_true(g_variant_lookup(props, "type", "&s", &s)); g_assert_cmpstr(s, ==, "standard");
    g_variant_unref(props); g_variant_unref(updates);
    GVariant *names = item(removed, 10); g_assert_nonnull(names);
    g_assert_cmpuint(g_variant_n_children(names), ==, 2);
    g_variant_get_child(names, 0, "&s", &s); g_assert_cmpstr(s, ==, "toggle-type");
    g_variant_get_child(names, 1, "&s", &s); g_assert_cmpstr(s, ==, "toggle-state");
    g_variant_unref(names); g_variant_unref(removed); reset();
    DarlingStatusMenuEntry reordered[] = {{20, 0, "second", 3, 0}, {10, 0, "newer", 3, 0}, {30, 10, "child", 3, 0}};
    g_assert_true(darling_menu_set(&menu, reordered, 3));
    g_assert_cmpuint(signals->len, ==, 2); expect_name(0, "LayoutUpdated"); expect_name(1, "ItemsPropertiesUpdated");
    g_variant_get(g_ptr_array_index(payloads, 0), "(ui)", &rev, &parent);
    g_assert_cmpuint(rev, ==, 4); g_assert_cmpint(parent, ==, 0);
    payload = g_ptr_array_index(payloads, 1); updates = g_variant_get_child_value(payload, 0);
    g_assert_null(item(updates, 30)); props = item(updates, 10); g_assert_nonnull(props);
    g_assert_true(g_variant_lookup(props, "children-display", "&s", &s)); g_assert_cmpstr(s, ==, "submenu");
    g_variant_unref(props); g_variant_unref(updates); reset();
    g_assert_true(darling_menu_set(&menu, reordered, 2));
    g_assert_cmpuint(signals->len, ==, 2); expect_name(0, "LayoutUpdated"); expect_name(1, "ItemsPropertiesUpdated");
    g_variant_get(g_ptr_array_index(payloads, 0), "(ui)", &rev, &parent);
    g_assert_cmpuint(rev, ==, 5); g_assert_cmpint(parent, ==, 0);
    payload = g_ptr_array_index(payloads, 1); removed = g_variant_get_child_value(payload, 1);
    names = item(removed, 10); g_assert_nonnull(names); g_variant_get_child(names, 0, "&s", &s);
    g_assert_cmpstr(s, ==, "children-display"); g_variant_unref(names); g_variant_unref(removed);
    reset();
    /* An unexposed state change still preserves the original layout revision. */
    guint revision = menu.revision;
    reordered[0].toggle_state = 1;
    g_assert_true(darling_menu_set(&menu, reordered, 2));
    g_assert_cmpuint(menu.revision, ==, revision + 1);
    g_assert_cmpuint(signals->len, ==, 1); expect_name(0, "LayoutUpdated");
    reset();
    g_assert_true(darling_menu_set(&menu, reordered, 2)); g_assert_cmpuint(signals->len, ==, 0);
    free_entries(menu.entries, menu.count); g_ptr_array_unref(signals); g_ptr_array_unref(payloads);
    return 0;
}
