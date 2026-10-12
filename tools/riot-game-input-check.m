#import <AppKit/AppKit.h>
#import <AppKit/NSDisplay.h>
#import <AppKit/NSTextInput.h>
#import <objc/runtime.h>
#include <assert.h>
#include <stdio.h>
extern CGError CGAssociateMouseAndMouseCursorPosition(boolean_t connected);
@interface DragRegionView : NSView { @public NSUInteger presses; }
@end
@implementation DragRegionView
- (BOOL)mouseDownCanMoveWindow { return YES; }
- (void)mouseDown:(NSEvent *)event { ++presses; }
@end
@interface DragCheckWindow : NSWindow { @public NSMutableArray *dragEvents; }
@end
@implementation DragCheckWindow
- (NSEvent *)nextEventMatchingMask:(NSEventMask)mask {
 NSEvent *event=[[[dragEvents objectAtIndex:0] retain] autorelease];
 [dragEvents removeObjectAtIndex:0]; return event;
}
@end
@interface InputClient : NSView { @public NSString *received; NSRange replacement; SEL command; }
@end
@interface ClickResponder : NSResponder { @public NSUInteger presses; }
@end
@implementation ClickResponder
- (void)mouseDown:(NSEvent *)event { ++presses; }
@end
@implementation InputClient
- (void)insertText:(id)text replacementRange:(NSRange)range { [received release]; received=[text copy]; replacement=range; }
- (void)doCommandBySelector:(SEL)selector { command=selector; }
- (void)dealloc { [received release]; [super dealloc]; }
@end
static BOOL requestedGrab;
static void captureGrab(id display, SEL selector, BOOL grab) { requestedGrab=grab; }
int main(void) {
 @autoreleasepool {
  [NSApplication sharedApplication];
  NSBitmapImageRep *bitmap=[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:1 pixelsHigh:1 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bitmapFormat:0 bytesPerRow:4 bitsPerPixel:32];
  unsigned char *bytes=[bitmap bitmapData]; bytes[0]=208; bytes[1]=160; bytes[2]=32; bytes[3]=255;
  CGColorSpaceRef rgb=CGColorSpaceCreateDeviceRGB();
  uint32_t pixel=0;
  CGContextRef canvas=CGBitmapContextCreate(&pixel,1,1,8,4,rgb,kCGImageAlphaPremultipliedFirst|kCGBitmapByteOrder32Little);
  CGContextDrawImage(canvas,CGRectMake(0,0,1,1),[bitmap CGImage]);
  printf("CURSOR_PIXEL expected=ffd0a020 actual=%08x\n",pixel); fflush(stdout);
  assert(pixel==0xffd0a020);
  CGContextRelease(canvas);CGColorSpaceRelease(rgb);[bitmap release];
  InputClient *client=[InputClient new];
  NSTextInputContext *context=[client inputContext];
  assert(context && context==[client inputContext] && [context client]==client);
  NSEvent *event=[NSEvent keyEventWithType:NSKeyDown location:NSZeroPoint modifierFlags:0 timestamp:0 windowNumber:0 context:nil characters:@"éA" charactersIgnoringModifiers:@"éa" isARepeat:NO keyCode:0];
  assert([context handleEvent:event]);
  assert([client->received isEqual:@"éA"] && client->replacement.location==NSNotFound);
  NSEvent *backspace=[NSEvent keyEventWithType:NSKeyDown location:NSZeroPoint modifierFlags:0 timestamp:0 windowNumber:0 context:nil characters:@"\177" charactersIgnoringModifiers:@"\177" isARepeat:NO keyCode:51];
  assert([context handleEvent:backspace] && sel_isEqual(client->command,@selector(deleteBackward:)));
  NSEvent *shortcut=[NSEvent keyEventWithType:NSKeyDown location:NSZeroPoint modifierFlags:NSCommandKeyMask timestamp:0 windowNumber:0 context:nil characters:@"a" charactersIgnoringModifiers:@"a" isARepeat:NO keyCode:0];
  assert(![context handleEvent:shortcut]);
  NSWindow *window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,100,100) styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  ClickResponder *click=[ClickResponder new];
  [window setMovableByWindowBackground:NO]; [window setNextResponder:click];
  NSEvent *press=[NSEvent mouseEventWithType:NSLeftMouseDown location:NSMakePoint(30,40) modifierFlags:0 timestamp:0 windowNumber:[window windowNumber] context:nil eventNumber:1 clickCount:1 pressure:1];
  [window sendEvent:press]; assert(click->presses==1);
  [window setNextResponder:nil]; [click release]; [window release];
  DragCheckWindow *drag=[[DragCheckWindow alloc] initWithContentRect:NSMakeRect(100,100,100,100) styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  NSEvent *down=[NSEvent mouseEventWithType:NSLeftMouseDown location:NSMakePoint(10,10) modifierFlags:0 timestamp:0 windowNumber:[drag windowNumber] context:nil eventNumber:1 clickCount:1 pressure:1];
  NSEvent *motion=[NSEvent mouseEventWithType:NSLeftMouseDragged location:NSMakePoint(25,20) modifierFlags:0 timestamp:0 windowNumber:[drag windowNumber] context:nil eventNumber:2 clickCount:1 pressure:1];
  NSEvent *up=[NSEvent mouseEventWithType:NSLeftMouseUp location:NSMakePoint(10,10) modifierFlags:0 timestamp:0 windowNumber:[drag windowNumber] context:nil eventNumber:3 clickCount:1 pressure:0];
  drag->dragEvents=[[NSMutableArray alloc] initWithObjects:motion,up,nil];
  NSPoint before=[drag frame].origin;
  assert([drag isMovable]);[drag setMovable:NO];[drag performWindowDragWithEvent:down];
  assert(NSEqualPoints(before,[drag frame].origin) && [drag->dragEvents count]==2);
  [drag setMovable:YES];[drag performWindowDragWithEvent:down];
  // These synthetic window-relative events do not move the physical cursor.
  // The drag implementation uses global cursor coordinates; verify tracking
  // consumes the sequence here, and check displacement with real input.
  assert([drag->dragEvents count]==0);
  [drag setContentView:[[[DragRegionView alloc] initWithFrame:NSMakeRect(0,0,100,100)] autorelease]];
  [drag->dragEvents addObject:motion];[drag->dragEvents addObject:up];
  DragRegionView *region=(DragRegionView *)[drag contentView];
  before=[drag frame].origin;[drag sendEvent:down];
  assert(region->presses==1 && NSEqualPoints(before,[drag frame].origin));
  assert([drag->dragEvents count]==2);
  [drag setMovableByWindowBackground:YES];[drag sendEvent:down];
  assert(region->presses==1 && [drag->dragEvents count]==0);
  [drag->dragEvents release];[drag release];
  NSDisplay *display=[NSDisplay currentDisplay];
  Method method=class_getInstanceMethod([display class],@selector(grabMouse:));
  IMP old=method_setImplementation(method,(IMP)captureGrab);
  assert(CGAssociateMouseAndMouseCursorPosition(true)==kCGErrorSuccess && !requestedGrab);
  assert(CGAssociateMouseAndMouseCursorPosition(false)==kCGErrorSuccess && requestedGrab);
  method_setImplementation(method,old);
  [client release];
  puts("PASS text context, Unicode, editing, shortcuts, cursor association, frameless window drag and movable flag");
 }
 return 0;
}
