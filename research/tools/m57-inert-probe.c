/* Control probe: proves whether loading an otherwise inert Mach-O dylib changes
 * Electron behavior. It has no constructors, interposers, hooks, or imports. */
__attribute__((visibility("default"))) int m57_inert_probe = 1;
