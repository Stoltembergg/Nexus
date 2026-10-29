/* SPDX-License-Identifier: GPL-3.0-only
 * Standalone default-NSMenuItem regression; no tray, client or display needed.
 */
#import <AppKit/NSMenuItem.h>
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <assert.h>
#include <stdio.h>

extern id objc_alloc_init(Class cls);

static void assertMenuDefaults(NSMenuItem *item) {
    assert(item != nil);
    assert([item isEnabled]);
    assert(![item isHidden]);
    assert(![item isSeparatorItem]);
    assert([[item title] isEqualToString:@""]);
    assert([[item keyEquivalent] isEqualToString:@""]);
    assert([item action] == NULL && [item target] == nil);
    [item setTitle:@"Configured after initialization"];
    assert([item isEnabled]);
    [item setEnabled:NO];
    assert(![item isEnabled]); // Explicit application state remains authoritative.
    [item release];
}

int main(void) {
    @autoreleasepool {
        assertMenuDefaults([[NSMenuItem alloc] init]);
        assertMenuDefaults([NSMenuItem new]);
        assertMenuDefaults(objc_alloc_init([NSMenuItem class]));
        NSMenuItem *separator = [NSMenuItem separatorItem];
        assert([separator isSeparatorItem]);
        NSMenuItem *designated = [[NSMenuItem alloc] initWithTitle:@"Explicit"
            action:NULL keyEquivalent:@"x"];
        assert([designated isEnabled]);
        assert([[designated title] isEqualToString:@"Explicit"]);
        assert([[designated keyEquivalent] isEqualToString:@"x"]);
        [designated release];
        puts("MENU_ITEM_INIT init=1 new=1 objc_alloc_init=1 explicit_disable=1 separator=1 designated=1");
    }
    return 0;
}
