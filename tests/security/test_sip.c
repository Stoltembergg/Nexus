/*
 * Guest-side M7 SIP prototype test: protected-path writes, /usr/local
 * exception, symlink/.. escapes and csrctl's active configuration.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/csr.h>
#include <sys/stat.h>

static int try_mkdir(const char* path) {
	int rc = mkdir(path, 0700);
	printf("mkdir %s rc=%d errno=%d\n", path, rc, errno);
	if (rc == 0)
		rmdir(path);
	return rc;
}

static int try_write(const char* path) {
	int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
	if (fd < 0) {
		printf("write %s rc=-1 errno=%d\n", path, errno);
		return -1;
	}
	close(fd);
	printf("write %s rc=0\n", path);
	return 0;
}

int main(void) {
	csr_config_t config = 0xffffffffu;
	int protected_write, protected_mkdir, local_write, dotdot_write, localdotdot_write, symlink_write;

	if (csr_get_active_config(&config) != 0) {
		printf("CSR_GET_FAIL errno=%d\n", errno);
		return 1;
	}
	printf("csr_config=0x%08x\n", config);

	protected_mkdir = try_mkdir("/private/etc");
	protected_write = try_write("/private/etc/sip-test");
	local_write = try_write("/usr/local/sip-test");
	dotdot_write = try_write("/private/etc/../etc/sip-test");
	localdotdot_write = try_write("/usr/local/../private/etc/sip-test");
	symlink_write = try_write("/private/tmp/sip-link/sip-test");

	unlink("/usr/local/sip-test");
	unlink("/private/etc/sip-test");

	if (config == 0) {
		if (protected_write == 0 || protected_mkdir == 0 || dotdot_write == 0 || localdotdot_write == 0 || symlink_write == 0 || local_write != 0) {
			printf("SIP_FAIL\n");
			return 1;
		}
		printf("SIP_ON_OK\n");
	} else {
		if (protected_write != 0 || dotdot_write != 0 || symlink_write != 0 || local_write != 0) {
			printf("SIP_FAIL\n");
			return 1;
		}
		printf("SIP_OFF_OK\n");
	}
	return 0;
}
