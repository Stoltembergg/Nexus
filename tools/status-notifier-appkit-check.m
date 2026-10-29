/* SPDX-License-Identifier: GPL-3.0-only
 * Owned lifecycle probe: no Riot assets, windows, credentials or automation.
 */
#import <AppKit/AppKit.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

@interface NSStatusItem (OwnedNativeProbe)
- (BOOL) _ensureNative;
- (void) _refreshNativeMenu;
- (void) _dispatchNativeMenuID: (int32_t) identifier;
- (const char *) _nativeBusName;
- (void) _openNativeMenuID: (int32_t) identifier;
- (void) _closeNativeMenuID: (int32_t) identifier;
@end

@interface OwnedMenuTarget : NSObject <NSMenuDelegate> {
@public
    unsigned clicks;
    BOOL finished;
    BOOL desktop;
    NSMenuItem *dynamicItem;
    unsigned refreshes;
}
- (void) selected: (id) sender;
- (void) finish: (id) sender;
- (void) menuNeedsUpdate: (NSMenu *) menu;
@end
@implementation OwnedMenuTarget
- (void) selected: (id) sender {
    assert([NSThread isMainThread]);
    assert([sender isKindOfClass:[NSMenuItem class]]);
    clicks++;
    if (desktop) {
        [(NSMenuItem *)sender setTitle:@"Ação confirmada"];
        printf("STATUS_DESKTOP_ACTION count=%u main_thread=1\n", clicks);
    }
}
- (void) finish: (id) sender {
    assert([NSThread isMainThread]);
    finished = YES;
}
- (void) menuNeedsUpdate: (NSMenu *) menu {
    assert([NSThread isMainThread]);
    if (desktop && dynamicItem != nil) {
        refreshes++;
        [dynamicItem setTitle:[NSString stringWithFormat:@"Atualização dinâmica %u", refreshes]];
    }
}
@end

@interface OwnedTrackingTarget : NSObject <NSMenuDelegate> {
@public
    BOOL open;
    unsigned opens, closes, actions;
}
- (void) selected: (id) sender;
@end
@implementation OwnedTrackingTarget
- (void) menuWillOpen: (NSMenu *) menu {
    assert([NSThread isMainThread]);
    open = YES;
    opens++;
}
- (void) menuDidClose: (NSMenu *) menu {
    assert([NSThread isMainThread]);
    open = NO;
    closes++;
}
- (BOOL) validateMenuItem: (NSMenuItem *) item { return open; }
- (void) selected: (id) sender {
    assert([NSThread isMainThread]);
    assert(open);
    actions++;
}
@end

static int32_t identifierFor(NSStatusItem *status, NSMenuItem *item) {
    NSDictionary *items = [status valueForKey:@"nativeMenuItems"];
    for (NSNumber *key in items)
        if ([items objectForKey:key] == item) return [key intValue];
    return 0;
}

static int desktopProbe(void) {
    NSStatusBar *bar = [NSStatusBar systemStatusBar];
    NSStatusItem *status = [[bar statusItemWithLength:NSSquareStatusItemLength] retain];
    [[status button] setTitle:@"Darling tray desktop probe"];
    [[status button] setToolTip:@"Teste de bandeja Darling — clique com o botão direito"];
    // Original neutral artwork: bright green tile with a white center. No
    // client logo or dependency on the host's application icon theme.
    NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(22, 22)];
    [image lockFocus];
    [[NSColor colorWithCalibratedRed:0.05 green:0.9 blue:0.25 alpha:1] set];
    NSRectFill(NSMakeRect(0, 0, 22, 22));
    [[NSColor whiteColor] set];
    NSRectFill(NSMakeRect(7, 7, 8, 8));
    [image unlockFocus];
    [[status button] setImage:image];
    [image release];
    assert([status _ensureNative]);
    OwnedMenuTarget *target = [[OwnedMenuTarget alloc] init];
    target->desktop = YES;
    NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Teste de integração Darling"];
    [menu setAutoenablesItems:NO];
    NSMenuItem *action = [menu addItemWithTitle:@"Confirmar ação de teste" action:@selector(selected:) keyEquivalent:@""];
    [action setTarget:target];
    NSMenuItem *blocked = [menu addItemWithTitle:@"Ação desabilitada" action:@selector(selected:) keyEquivalent:@""];
    [blocked setTarget:target];
    [blocked setEnabled:NO];
    target->dynamicItem = [menu addItemWithTitle:@"Atualização dinâmica 0" action:NULL keyEquivalent:@""];
    [target->dynamicItem setEnabled:NO];
    [menu setDelegate:target];
    NSMenuItem *finish = [menu addItemWithTitle:@"Finalizar teste" action:@selector(finish:) keyEquivalent:@""];
    [finish setTarget:target];
    [status setMenu:menu];
    const char *name = [status _nativeBusName];
    assert(name != NULL);
    printf("STATUS_DESKTOP_READY bus=%s click=%d blocked=%d finish=%d\n", name,
        identifierFor(status, action), identifierFor(status, blocked), identifierFor(status, finish));
    const char *manual = getenv("STATUS_CHECK_MANUAL");
    long seconds = 30;
    if (manual != NULL && strcmp(manual, "1") == 0) {
        seconds = 180;
        const char *setting = getenv("STATUS_CHECK_MANUAL_SECONDS");
        if (setting != NULL) {
            char *end = NULL;
            long requested = strtol(setting, &end, 10);
            if (end != setting && *end == '\0' && requested >= 30 && requested <= 900)
                seconds = requested;
        }
    }
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:seconds];
    // Do not call _pollNativeEvents directly: this test must exercise the real
    // NSStatusBar timer, native queue and guest run-loop modes.
    while (!target->finished && [deadline timeIntervalSinceNow] > 0) {
        @autoreleasepool {
            [[NSRunLoop mainRunLoop] runMode:NSDefaultRunLoopMode
                beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        }
    }
    BOOL passed = target->finished && target->clicks == 1;
    printf("STATUS_DESKTOP_DONE finished=%d clicks=%u pass=%d\n", target->finished, target->clicks, passed);
    [bar removeStatusItem:status];
    [status release];
    [menu release];
    [target release];
    return passed ? 0 : 1;
}

int main(void) {
    setbuf(stdout, NULL);
    @autoreleasepool {
        [NSApplication sharedApplication];
        NSMenuItem *defaultItem = [[NSMenuItem alloc] init];
        assert([defaultItem isEnabled]);
        assert([[defaultItem title] isEqualToString:@""]);
        assert([[defaultItem keyEquivalent] isEqualToString:@""]);
        assert([defaultItem action] == NULL && [defaultItem target] == nil);
        [defaultItem release];
        puts("STATUS_MENU_DEFAULT_INIT enabled=1 empty_title=1 empty_key=1");
        if (getenv("STATUS_CHECK_DESKTOP"))
            return desktopProbe();
        NSStatusBar *bar = [NSStatusBar systemStatusBar];
        NSAutoreleasePool *pool = [NSAutoreleasePool new];
        NSStatusItem *item = [[bar statusItemWithLength:NSSquareStatusItemLength] retain];
        NSStatusBarButton *button = [[item button] retain];
        assert(button == [item button]);
        [button setTitle:@"Owned tray probe"];
        assert([[item title] isEqualToString:@"Owned tray probe"]);
        if (getenv("STATUS_CHECK_REQUIRE_NATIVE"))
            assert([item _ensureNative]);
        NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Probe"];
        [item setMenu:menu];
        assert([item menu] == menu);
        [menu addItemWithTitle:@"First" action:NULL keyEquivalent:@""];
        assert([[item menu] numberOfItems] == 1);
        [item setMenu:menu]; // Self-assignment must preserve the menu.
        if (getenv("STATUS_CHECK_REQUIRE_NATIVE")) {
            [menu setAutoenablesItems:NO];
            OwnedMenuTarget *target = [[OwnedMenuTarget alloc] init];
            // Also exercise default construction followed by setters, as used
            // by native menu wrappers rather than addItemWithTitle:.
            NSMenuItem *action = [[NSMenuItem alloc] init];
            [action setTitle:@"Action"];
            [action setAction:@selector(selected:)];
            [action setTarget:target];
            [menu addItem:action];
            [action release];
            [item _refreshNativeMenu];
            int32_t identifier = identifierFor(item, action);
            assert(identifier > 0);
            [menu insertItemWithTitle:@"Inserted" action:NULL keyEquivalent:@"" atIndex:0];
            [item _refreshNativeMenu];
            assert(identifierFor(item, action) == identifier);
            [item _dispatchNativeMenuID:identifier];
            assert(target->clicks == 1);
            [action setEnabled:NO];
            [item _dispatchNativeMenuID:identifier];
            assert(target->clicks == 1);
            [action setEnabled:YES];
            [action setHidden:YES];
            [item _dispatchNativeMenuID:identifier];
            assert(target->clicks == 1);
            [action setHidden:NO];
            [menu removeItem:action];
            [item _dispatchNativeMenuID:identifier];
            assert(target->clicks == 1);
            NSMenuItem *replacement = [menu addItemWithTitle:@"Replacement" action:@selector(selected:) keyEquivalent:@""];
            [replacement setTarget:target];
            [item _refreshNativeMenu];
            assert(identifierFor(item, replacement) != identifier);
            [item _dispatchNativeMenuID:identifier];
            assert(target->clicks == 1);
            [menu removeItem:replacement];
            [item _refreshNativeMenu];
            NSMenu *submenu = [[NSMenu alloc] initWithTitle:@"Nested"];
            [submenu setAutoenablesItems:NO];
            NSMenuItem *parent = [menu addItemWithTitle:@"Parent" action:NULL keyEquivalent:@""];
            [menu setSubmenu:submenu forItem:parent];
            NSMenuItem *child = [submenu addItemWithTitle:@"Child" action:@selector(selected:) keyEquivalent:@""];
            [child setTarget:target];
            [parent setEnabled:NO];
            [item _refreshNativeMenu];
            int32_t childID = identifierFor(item, child);
            assert(childID > 0);
            [item _dispatchNativeMenuID:childID];
            assert(target->clicks == 1);
            [parent setEnabled:YES];
            [item _dispatchNativeMenuID:childID];
            assert(target->clicks == 2);
            [menu removeItem:parent];
            [item _dispatchNativeMenuID:childID];
            assert(target->clicks == 2);
            [submenu release];
            [target release];
            OwnedTrackingTarget *tracking = [[OwnedTrackingTarget alloc] init];
            NSMenu *validated = [[NSMenu alloc] initWithTitle:@"Validated"];
            [validated setDelegate:tracking];
            NSMenuItem *trackedAction = [validated addItemWithTitle:@"Enabled only when open"
                action:@selector(selected:) keyEquivalent:@""];
            [trackedAction setTarget:tracking];
            [item setMenu:validated];
            assert(![trackedAction isEnabled]);
            [item _openNativeMenuID:0];
            [item _openNativeMenuID:0]; // AboutToShow + opened must not notify twice.
            assert([trackedAction isEnabled] && tracking->opens == 1);
            [item _dispatchNativeMenuID:identifierFor(item, trackedAction)];
            assert(tracking->actions == 1);
            [item _closeNativeMenuID:0];
            [item _closeNativeMenuID:0];
            assert(![trackedAction isEnabled] && tracking->closes == 1);
            [item _openNativeMenuID:0];
            [item setMenu:menu]; // Replacement closes the previous tracking session.
            assert(tracking->opens == 2 && tracking->closes == 2);
            [validated release];
            [tracking release];
            puts("STATUS_MENU_TRACKING will_open=1 did_close=1 validation=1 deduplicated=1 replacement=1");
            puts("STATUS_MENU stable_ids=1 main_thread_action=1 disabled_hidden_removed=1");
        }
        [item setLength:37];
        assert([button frame].size.width == 37);
        [bar removeStatusItem:item];
        [bar removeStatusItem:item]; // Idempotent removal.
        [button setTitle:@"Removed item must stay removed"];
        if (getenv("STATUS_CHECK_REQUIRE_NATIVE"))
            assert(![item _ensureNative]);
        [item release];
        [pool drain]; // Release the factory's autoreleased reference.
        [button setTitle:@"Owner already destroyed"];
        [button release];
        [menu release];
        puts("STATUS_APPKIT lifecycle=1 live_menu=1 retained_button=1");
    }
    return 0;
}
