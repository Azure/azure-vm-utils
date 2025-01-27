/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <errno.h>
#include <fcntl.h>
#include <linux/nvme_ioctl.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

// clange-format off
#include <cmocka.h>
// clange-format on

#include "capture.h"
#include "nvme.h"

#define OPEN_FD 14
#define OPEN_PATH "/dev/nvme199n19"
#define NSID 19

#include <stdbool.h>
bool debug = false;

struct nvme_id_ns empty_ns = {
    0,
};

int __wrap_open(const char *pathname, int flags, ...)
{
    check_expected(pathname);
    check_expected(flags);

    int ret = mock_type(int);
    if (ret < 0)
    {
        errno = mock_type(int);
    }
    return ret;
}

int __wrap_posix_memalign(void **memptr, size_t alignment, size_t size)
{
    check_expected(memptr);
    check_expected(alignment);
    check_expected(size);

    int ret = mock_type(int);
    if (ret < 0)
    {
        errno = mock_type(int);
    }
    else if (ret == 0)
    {
        *memptr = malloc(size);
    }

    return ret;
}

int __wrap_ioctl(int fd, unsigned long request, ...)
{
    check_expected(fd);
    check_expected(request);

    va_list args;
    va_start(args, request);
    void *arg = va_arg(args, void *);
    va_end(args);

    struct nvme_admin_cmd *cmd = (struct nvme_admin_cmd *)arg;
    assert_non_null(cmd);
    assert_int_equal(cmd->opcode, NVME_ADMIN_IDENTFY_NAMESPACE_OPCODE);

    unsigned int nsid = mock_type(unsigned int);
    assert_int_equal(cmd->nsid, nsid);
    assert_int_equal(cmd->data_len, sizeof(struct nvme_id_ns));
    assert_non_null(cmd->addr);

    struct nvme_id_ns *ns = mock_type(struct nvme_id_ns *);
    if (ns != NULL)
    {
        memcpy((void *)cmd->addr, ns, sizeof(struct nvme_id_ns));
        ns = (struct nvme_id_ns *)cmd->addr;
    }

    int ret = mock_type(int);
    if (ret < 0)
    {
        errno = mock_type(int);
    }

    return ret;
}

int __wrap_close(int fd)
{
    check_expected(fd);
    return mock_type(int);
}

static void test_nvme_identify_namespace_success(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, OPEN_PATH);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_any(__wrap_posix_memalign, memptr);
    expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
    expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
    will_return(__wrap_posix_memalign, 0);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ADMIN_CMD);
    will_return(__wrap_ioctl, NSID);
    will_return(__wrap_ioctl, &empty_ns);
    will_return(__wrap_ioctl, 0);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    struct nvme_id_ns *result = nvme_identify_namespace(OPEN_PATH, NSID);

    assert_non_null(result);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_nvme_identify_namespace_failure_to_open(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, OPEN_PATH);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, -1);
    will_return(__wrap_open, EOWNERDEAD);

    struct nvme_id_ns *result = nvme_identify_namespace(OPEN_PATH, NSID);

    assert_null(result);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme199n19: Owner died\n");
}

static void test_nvme_identify_namespace_failure_to_posix_memalign(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, OPEN_PATH);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_any(__wrap_posix_memalign, memptr);
    expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
    expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
    will_return(__wrap_posix_memalign, -1);
    will_return(__wrap_posix_memalign, ENOLINK);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    struct nvme_id_ns *result = nvme_identify_namespace(OPEN_PATH, NSID);

    assert_null(result);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed posix_memalign for /dev/nvme199n19: Link has been severed\n");
}

static void test_nvme_identify_namespace_failure_to_ioctl(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, OPEN_PATH);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_any(__wrap_posix_memalign, memptr);
    expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
    expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
    will_return(__wrap_posix_memalign, 0);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ADMIN_CMD);
    will_return(__wrap_ioctl, NSID);
    will_return(__wrap_ioctl, NULL);
    will_return(__wrap_ioctl, -1);
    will_return(__wrap_ioctl, EUCLEAN);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    struct nvme_id_ns *result = nvme_identify_namespace(OPEN_PATH, NSID);

    assert_null(result);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed NVME_IOCTL_ADMIN_CMD ioctl for /dev/nvme199n19: "
                                          "Structure needs cleaning\n");
}

static void test_nvme_identify_namespace_vs_success(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, OPEN_PATH);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_any(__wrap_posix_memalign, memptr);
    expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
    expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
    will_return(__wrap_posix_memalign, 0);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ADMIN_CMD);
    will_return(__wrap_ioctl, NSID);
    struct nvme_id_ns ns = {.vs = "key1=value1,key2=value2"};
    will_return(__wrap_ioctl, &ns);
    will_return(__wrap_ioctl, 0);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    char *vs = nvme_identify_namespace_vs(OPEN_PATH, NSID);

    assert_non_null(vs);
    assert_string_equal(vs, "key1=value1,key2=value2");
    free(vs);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_nvme_identify_namespace_vs_failure(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, OPEN_PATH);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, -1);
    will_return(__wrap_open, EOWNERDEAD);

    char *vs = nvme_identify_namespace_vs(OPEN_PATH, NSID);

    assert_null(vs);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme199n19: Owner died\n"
                                          "failed to identify namespace for device=/dev/nvme199n19\n");
}

static void test_get_nsid_from_namespace_device_path_success(void **state)
{
    (void)state; // Unused parameter

    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme0n5"), 5);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme2n12"), 12);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme100n1"), 1);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme100000n1"), 1);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme55n999"), 999);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_get_nsid_from_namespace_device_path_failure(void **state)
{
    (void)state; // Unused parameter

    assert_int_equal(get_nsid_from_namespace_device_path("bad"), -1);
    assert_int_equal(get_nsid_from_namespace_device_path("bad1n1"), -1);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/bad1n1"), -1);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme0"), -1);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme0n"), -1);
    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme0nX"), -1);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_nvme_identify_namespace_vs_for_namespace_device_success(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/dev/nvme0n5";
    const char *vendor_specific_data = "key1=value1,key2=value2";

    expect_string(__wrap_open, pathname, path);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_any(__wrap_posix_memalign, memptr);
    expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
    expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
    will_return(__wrap_posix_memalign, 0);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ADMIN_CMD);
    will_return(__wrap_ioctl, 5);
    struct nvme_id_ns ns = {.vs = "key1=value1,key2=value2"};
    will_return(__wrap_ioctl, &ns);
    will_return(__wrap_ioctl, 0);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    char *result = nvme_identify_namespace_vs_for_namespace_device(path);

    assert_non_null(result);
    assert_string_equal(result, vendor_specific_data);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_nvme_identify_namespace_vs_for_namespace_device_nsid_failure(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/dev/nvme0nX";

    char *result = nvme_identify_namespace_vs_for_namespace_device(path);

    assert_null(result);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to parse namespace id: /dev/nvme0nX\n");
}

static void test_nvme_identify_namespace_vs_for_namespace_device_vs_failure(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/dev/nvme0n5";

    expect_string(__wrap_open, pathname, path);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, -1);
    will_return(__wrap_open, EOWNERDEAD);

    char *result = nvme_identify_namespace_vs_for_namespace_device(path);

    assert_null(result);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme0n5: Owner died\n"
                                          "failed to identify namespace for device=/dev/nvme0n5\n");
}

static int setup(void **state)
{
    (void)state; // Unused parameter

    capture_setup(state);

    return 0;
}

static int teardown(void **state)
{
    (void)state; // Unused parameter

    capture_teardown(state);

    return 0;
}

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_open, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_posix_memalign, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_ioctl, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_get_nsid_from_namespace_device_path_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_get_nsid_from_namespace_device_path_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_for_namespace_device_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_for_namespace_device_nsid_failure, setup,
                                        teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_for_namespace_device_vs_failure, setup,
                                        teardown),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
