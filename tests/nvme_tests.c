#include <criterion/criterion.h>
#include <criterion/logging.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/nvme_ioctl.h>

#include "mock_syscalls.h"
#include "nvme.h"

#define SUCCESSFUL_OPEN_FD 3
#define SUCCESSFUL_OPEN_PATH "/dev/nvme199n19"
#define FAILURE_OPEN_PATH "/dev/nvme0n0"

static int mock_open_success(const char *pathname, int flags, ...) {
    cr_expect_str_eq(pathname, SUCCESSFUL_OPEN_PATH, "Device path should match.");
    cr_expect_eq(flags, O_RDONLY, "Flags should match O_RDONLY.");
    return SUCCESSFUL_OPEN_FD;
}

static int mock_open_failure(const char *pathname, int flags, ...) {
    cr_expect_str_eq(pathname, FAILURE_OPEN_PATH, "Device path should match.");
    return -1;
}

static int mock_posix_memalign_success(void **memptr, size_t alignment, size_t size) {
    struct nvme_id_ns *expected_ns = malloc(size);
    cr_expect_not_null(memptr, "Memory pointer should not be NULL.");
    cr_expect_eq(alignment, sysconf(_SC_PAGESIZE), "Alignment should match system page size.");
    cr_expect_eq(size, sizeof(struct nvme_id_ns), "Size should match nvme_id_ns structure size.");
    *memptr = (void *)expected_ns;
    return 0;
}

static int mock_posix_memalign_failure(void **memptr, size_t alignment, size_t size) {
    return -1;
}

static int mock_ioctl_success(int fd, unsigned long request, ...) {
    cr_expect_eq(fd, SUCCESSFUL_OPEN_FD, "File descriptor should match.");
    cr_expect_eq(request, NVME_IOCTL_ADMIN_CMD, "Request should match NVME_IOCTL_ADMIN_CMD.");
    return 0;
}

static int mock_ioctl_failure(int fd, unsigned long request, ...) {
    return -1;
}

static int mock_close_success(int fd) {
    cr_expect_eq(fd, SUCCESSFUL_OPEN_FD, "File descriptor should match for close.");
    return 0;
}

/**
 * Reset all mocks on teardown.
 */
void test_teardown(void) {
    mock_syscalls_reset();
}

TestSuite(nvme_identify_namespace, .fini = test_teardown);

Test(nvme_identify_namespace, nvme_identify_namespace_success) {
    const char *device_path = SUCCESSFUL_OPEN_PATH;
    int nsid = 1;

    mock_open_ptr = mock_open_success;
    mock_posix_memalign_ptr = mock_posix_memalign_success;
    mock_ioctl_ptr = mock_ioctl_success;
    mock_close_ptr = mock_close_success;

    struct nvme_id_ns *result = nvme_identify_namespace(device_path, nsid);

    cr_assert_not_null(result, "Result should not be NULL.");
}

Test(nvme_identify_namespace, nvme_identify_namespace_failure_to_open) {
    const char *device_path = FAILURE_OPEN_PATH;
    int nsid = 1;

    mock_open_ptr = mock_open_failure;

    struct nvme_id_ns *result = nvme_identify_namespace(device_path, nsid);

    cr_assert_null(result, "Result should be NULL on open failure.");
}

Test(nvme_identify_namespace, nvme_identify_namespace_failure_to_posix_memalign) {
    const char *device_path = SUCCESSFUL_OPEN_PATH;
    int nsid = 1;

    mock_open_ptr = mock_open_success;
    mock_posix_memalign_ptr = mock_posix_memalign_failure;
    mock_close_ptr = mock_close_success;

    struct nvme_id_ns *result = nvme_identify_namespace(device_path, nsid);

    cr_assert_null(result, "Result should be NULL on posix_memalign failure.");
}

Test(nvme_identify_namespace, nvme_identify_namespace_failure_to_ioctl) {
    const char *device_path = SUCCESSFUL_OPEN_PATH;
    int nsid = 1;

    mock_open_ptr = mock_open_success;
    mock_posix_memalign_ptr = mock_posix_memalign_success;
    mock_ioctl_ptr = mock_ioctl_failure;
    mock_close_ptr = mock_close_success;

    struct nvme_id_ns *result = nvme_identify_namespace(device_path, nsid);

    cr_assert_null(result, "Result should be NULL on ioctl failure.");
}
