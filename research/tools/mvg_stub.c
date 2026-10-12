/* mvg stub for darling-lol: LeagueClient lazily binds 8 Mvg* symbols
 * (MvgInit, MvgIsConnected, MvgRegisterLogin/Logout, MvgDC/GCK/RC/ST).
 * The real 39MB Vanguard binary crashes Darling at startup (obfuscated
 * NULL-dispatch init); this stub returns benign defaults so the LCU can
 * initialize. Vanguard attestation is NOT provided: matches requiring
 * it will refuse, which is expected and honest on Linux.
 * Throwaway/PBE accounts only; upstreaming N/A (Riot binary).
 */
int MvgInit(void* a, void* b) { (void)a; (void)b; return 0; }
int MvgIsConnected(void) { return 0; }
int MvgRegisterLogin(const char* a) { (void)a; return 0; }
int MvgRegisterLogout(void) { return 0; }
int MvgDC(void* a, void* b, void* c) { (void)a; (void)b; (void)c; return 0; }
int MvgGCK(void* a, void* b) { (void)a; (void)b; return 0; }
int MvgRC(void* a) { (void)a; return 0; }
int MvgST(void* a, void* b) { (void)a; (void)b; return 0; }
/* Extra exports the real lib has (for game/Ux future use): */
int MvgGetMvgState(void* a) { (void)a; return 0; }
int MvgRegisterAppEvent(void* a, void* b) { (void)a; (void)b; return 0; }
int MvgRT(void* a, void* b) { (void)a; (void)b; return 0; }
