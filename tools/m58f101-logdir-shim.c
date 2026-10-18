/* Rewrite Riot's relative Electron --log-dir argument before app startup. */
/* Declare the public dyld API directly so the shim builds without an Apple SDK. */
typedef unsigned long size_t;
extern char *getenv(const char *);
extern void *malloc(size_t);
extern size_t strlen(const char *);
extern int strncmp(const char *, const char *, size_t);
extern void *memcpy(void *, const void *, size_t);
extern char ***_NSGetArgv(void);

__attribute__((constructor)) static void make_log_dir_absolute(void) {
    char ***argvp = _NSGetArgv();
    const char *home = getenv("HOME");
    if (argvp == 0 || *argvp == 0 || home == 0 || home[0] != '/')
        return;

    size_t home_len = strlen(home);
    for (char **arg = *argvp; *arg != 0; ++arg) {
        static const char option[] = "--log-dir=";
        if (strncmp(*arg, option, sizeof(option) - 1) != 0)
            continue;
        const char *path = *arg + sizeof(option) - 1;
        if (path[0] == '/')
            continue;

        size_t path_len = strlen(path);
        char *absolute = malloc(sizeof(option) - 1 + home_len + 1 + path_len + 1);
        if (absolute == 0)
            return;
        memcpy(absolute, option, sizeof(option) - 1);
        memcpy(absolute + sizeof(option) - 1, home, home_len);
        absolute[sizeof(option) - 1 + home_len] = '/';
        memcpy(absolute + sizeof(option) + home_len, path, path_len + 1);
        *arg = absolute;
    }
}
