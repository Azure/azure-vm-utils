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
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

// clange-format off
#include <cmocka.h>
// clange-format on

#include "capture.h"
#include "exit_code.h"
#include "identify_disks.h"
#include "identify_udev.h"
#include "nvme.h"

#define OPEN_FD 14
#define OPEN_PATH "/dev/nvme199n19"
#define NSID 19

#include <stdbool.h>
bool debug = false;

struct nvme_id_ns empty_ns = {
    0,
};

char *__real_strndup(const char *value, size_t length);
static bool fail_strndup;
long __real_sysconf(int name);
static bool fail_sysconf;

long __wrap_sysconf(int name)
{
    if (fail_sysconf)
    {
        assert_int_equal(name, _SC_PAGESIZE);
        errno = EINVAL;
        return -1;
    }
    return __real_sysconf(name);
}

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

/**
 * Redirect open64 to open for platforms that use it, e.g. armhf.
 */
int __wrap_open64(const char *pathname, int flags, ...)
{
    return __wrap_open(pathname, flags);
}

int __wrap_posix_memalign(void **memptr, size_t alignment, size_t size)
{
    check_expected(memptr);
    check_expected(alignment);
    check_expected(size);

    int ret = mock_type(int);
    if (ret == 0)
    {
        *memptr = malloc(size);
    }

    return ret;
}

char *__wrap_strndup(const char *value, size_t length)
{
    if (fail_strndup)
    {
        errno = ENOMEM;
        return NULL;
    }
    return __real_strndup(value, length);
}

int __wrap_ioctl(int fd, unsigned long request, ...)
{
    check_expected(fd);
    check_expected(request);

    if (request == NVME_IOCTL_ID)
    {
        int ret = mock_type(int);
        if (ret < 0)
        {
            errno = mock_type(int);
        }
        return ret;
    }

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
        memcpy((void *)(uintptr_t)cmd->addr, ns, sizeof(*ns));
        ns = (struct nvme_id_ns *)(uintptr_t)cmd->addr;
    }

    int ret = mock_type(int);
    if (ret < 0)
    {
        errno = mock_type(int);
    }

    return ret;
}

/**
 * Redirect __ioctl_time64 to ioctl for platforms that use it, e.g. armhf.
 */
int __wrap___ioctl_time64(int fd, unsigned long request, ...)
{
    if (request == NVME_IOCTL_ID)
    {
        return __wrap_ioctl(fd, request);
    }

    va_list args;
    va_start(args, request);
    void *arg = va_arg(args, void *);
    va_end(args);

    return __wrap_ioctl(fd, request, arg);
}

int __wrap_close(int fd)
{
    check_expected(fd);
    return mock_type(int);
}

static void test_nvme_identify_namespace_command_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
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
        will_return(__wrap_ioctl, 0x182);
        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        nvme_identify_namespace(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_IDENTIFY_NAMESPACE_STATUS);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed NVME_IOCTL_ADMIN_CMD ioctl for /dev/nvme199n19: NVMe status 0x182\n");
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
    free(result);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_nvme_identify_namespace_failure_to_open(void **state)
{
    (void)state; // Unused parameter

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, OPEN_PATH);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, -1);
        will_return(__wrap_open, EOWNERDEAD);
        nvme_identify_namespace(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_DEVICE_OPEN);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme199n19: Owner died\n");
}

static void test_nvme_identify_namespace_failure_to_sysconf(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, OPEN_PATH);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);
        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);
        fail_sysconf = true;
        nvme_identify_namespace(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_PAGE_SIZE);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed sysconf: Invalid argument\n");
}

static void test_nvme_identify_namespace_failure_to_posix_memalign(void **state)
{
    (void)state; // Unused parameter

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, OPEN_PATH);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);
        expect_any(__wrap_posix_memalign, memptr);
        expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
        expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
        will_return(__wrap_posix_memalign, ENOLINK);
        errno = EINVAL;
        nvme_identify_namespace(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NO_MEMORY);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed posix_memalign for /dev/nvme199n19: Link has been severed\n");
}

static void test_nvme_identify_namespace_failure_to_ioctl(void **state)
{
    (void)state; // Unused parameter

    pid_t child = capture_fork();
    if (child == 0)
    {
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

        nvme_identify_namespace(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed NVME_IOCTL_ADMIN_CMD ioctl for /dev/nvme199n19: "
                                          "Structure needs cleaning\n");
}

static void test_nvme_identify_namespace_vs_allocation_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
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
        fail_strndup = true;
        nvme_identify_namespace_vs(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NO_MEMORY);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "strndup() failed: Cannot allocate memory\n");
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

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, OPEN_PATH);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, -1);
        will_return(__wrap_open, EOWNERDEAD);
        nvme_identify_namespace_vs(OPEN_PATH, NSID);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_DEVICE_OPEN);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme199n19: Owner died\n");
}

static void test_get_nsid_from_namespace_device_path_success(void **state)
{
    (void)state; // Unused parameter

    expect_string(__wrap_open, pathname, "/dev/nvme1n1");
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
    will_return(__wrap_ioctl, 5);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    assert_int_equal(get_nsid_from_namespace_device_path("/dev/nvme1n1"), 5);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_get_nsid_from_namespace_device_path_open_failure(void **state)
{
    (void)state; // Unused parameter

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, OPEN_PATH);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, -1);
        will_return(__wrap_open, ENOENT);
        get_nsid_from_namespace_device_path(OPEN_PATH);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_DEVICE_OPEN);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme199n19: No such file or directory\n");
}

static void test_get_nsid_from_namespace_device_path_ioctl_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, OPEN_PATH);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);

        expect_value(__wrap_ioctl, fd, OPEN_FD);
        expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
        will_return(__wrap_ioctl, -1);
        will_return(__wrap_ioctl, ENOTTY);

        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        get_nsid_from_namespace_device_path(OPEN_PATH);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_NAMESPACE_ID_IOCTL);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(),
                        "failed NVME_IOCTL_ID ioctl for /dev/nvme199n19: Inappropriate ioctl for device\n");
}

static void test_nvme_identify_namespace_vs_for_namespace_device_success(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/dev/nvme0n5";
    const char *vendor_specific_data = "key1=value1,key2=value2";

    expect_string(__wrap_open, pathname, path);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
    will_return(__wrap_ioctl, 7);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    expect_string(__wrap_open, pathname, path);
    expect_value(__wrap_open, flags, O_RDONLY);
    will_return(__wrap_open, OPEN_FD);

    expect_any(__wrap_posix_memalign, memptr);
    expect_value(__wrap_posix_memalign, alignment, sysconf(_SC_PAGESIZE));
    expect_value(__wrap_posix_memalign, size, sizeof(struct nvme_id_ns));
    will_return(__wrap_posix_memalign, 0);

    expect_value(__wrap_ioctl, fd, OPEN_FD);
    expect_value(__wrap_ioctl, request, NVME_IOCTL_ADMIN_CMD);
    will_return(__wrap_ioctl, 7);
    struct nvme_id_ns ns = {.vs = "key1=value1,key2=value2"};
    will_return(__wrap_ioctl, &ns);
    will_return(__wrap_ioctl, 0);

    expect_value(__wrap_close, fd, OPEN_FD);
    will_return(__wrap_close, 0);

    char *result = nvme_identify_namespace_vs_for_namespace_device(path);

    assert_non_null(result);
    assert_string_equal(result, vendor_specific_data);
    free(result);

    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "");
}

static void test_nvme_identify_namespace_vs_for_namespace_device_nsid_failure(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/dev/nvme0n5";

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, path);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);

        expect_value(__wrap_ioctl, fd, OPEN_FD);
        expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
        will_return(__wrap_ioctl, -1);
        will_return(__wrap_ioctl, ENOTTY);

        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        nvme_identify_namespace_vs_for_namespace_device(path);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_NAMESPACE_ID_IOCTL);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(),
                        "failed NVME_IOCTL_ID ioctl for /dev/nvme0n5: Inappropriate ioctl for device\n");
}

static void test_nvme_identify_namespace_vs_for_namespace_device_vs_failure(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/dev/nvme0n5";

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, path);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);

        expect_value(__wrap_ioctl, fd, OPEN_FD);
        expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
        will_return(__wrap_ioctl, 7);

        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        expect_string(__wrap_open, pathname, path);
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, -1);
        will_return(__wrap_open, EOWNERDEAD);

        nvme_identify_namespace_vs_for_namespace_device(path);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_DEVICE_OPEN);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(), "failed to open /dev/nvme0n5: Owner died\n");
}

static void test_identify_udev_device_vs_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        assert_int_equal(setenv("DEVNAME", "/dev/nvme0n5", 1), 0);
        expect_string(__wrap_open, pathname, "/dev/nvme0n5");
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);
        expect_value(__wrap_ioctl, fd, OPEN_FD);
        expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
        will_return(__wrap_ioctl, NSID);
        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        expect_string(__wrap_open, pathname, "/dev/nvme0n5");
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

        identify_udev_device();
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(),
                        "failed NVME_IOCTL_ADMIN_CMD ioctl for /dev/nvme0n5: Structure needs cleaning\n");
}

static void test_enumerate_namespaces_nsid_failure(void **state)
{
    (void)state;

    char template[] = "/tmp/nvme_test_XXXXXX";
    char *controller_path = mkdtemp(template);
    assert_non_null(controller_path);

    char first_namespace[MAX_PATH];
    char second_namespace[MAX_PATH];
    snprintf(first_namespace, sizeof(first_namespace), "%s/nvme0n1", controller_path);
    snprintf(second_namespace, sizeof(second_namespace), "%s/nvme0n2", controller_path);
    assert_int_equal(mkdir(first_namespace, 0700), 0);
    assert_int_equal(mkdir(second_namespace, 0700), 0);

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, "/dev/nvme0n1");
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);
        expect_value(__wrap_ioctl, fd, OPEN_FD);
        expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
        will_return(__wrap_ioctl, -1);
        will_return(__wrap_ioctl, ENOTTY);
        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        struct nvme_controller ctrl = {0};
        snprintf(ctrl.name, sizeof(ctrl.name), "nvme0");
        snprintf(ctrl.sys_path, sizeof(ctrl.sys_path), "%s", controller_path);
        struct context ctx = {.output_format = PLAIN};
        json_object *namespaces = json_object_new_array();
        assert_non_null(namespaces);
        enumerate_namespaces_for_controller(&ctrl, &ctx, namespaces);
        json_object_put(namespaces);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_NAMESPACE_ID_IOCTL);
    assert_int_equal(rmdir(first_namespace), 0);
    assert_int_equal(rmdir(second_namespace), 0);
    assert_int_equal(rmdir(controller_path), 0);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(),
                        "failed NVME_IOCTL_ID ioctl for /dev/nvme0n1: Inappropriate ioctl for device\n");
}

static void test_enumerate_namespaces_vs_failure(void **state)
{
    (void)state;

    char template[] = "/tmp/nvme_test_XXXXXX";
    char *controller_path = mkdtemp(template);
    assert_non_null(controller_path);

    char first_namespace[MAX_PATH];
    char second_namespace[MAX_PATH];
    snprintf(first_namespace, sizeof(first_namespace), "%s/nvme0n1", controller_path);
    snprintf(second_namespace, sizeof(second_namespace), "%s/nvme0n2", controller_path);
    assert_int_equal(mkdir(first_namespace, 0700), 0);
    assert_int_equal(mkdir(second_namespace, 0700), 0);

    pid_t child = capture_fork();
    if (child == 0)
    {
        expect_string(__wrap_open, pathname, "/dev/nvme0n1");
        expect_value(__wrap_open, flags, O_RDONLY);
        will_return(__wrap_open, OPEN_FD);
        expect_value(__wrap_ioctl, fd, OPEN_FD);
        expect_value(__wrap_ioctl, request, NVME_IOCTL_ID);
        will_return(__wrap_ioctl, NSID);
        expect_value(__wrap_close, fd, OPEN_FD);
        will_return(__wrap_close, 0);

        expect_string(__wrap_open, pathname, "/dev/nvme0n1");
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

        struct nvme_controller ctrl = {0};
        snprintf(ctrl.name, sizeof(ctrl.name), "nvme0");
        snprintf(ctrl.sys_path, sizeof(ctrl.sys_path), "%s", controller_path);
        struct context ctx = {.output_format = PLAIN};
        json_object *namespaces = json_object_new_array();
        assert_non_null(namespaces);
        enumerate_namespaces_for_controller(&ctrl, &ctx, namespaces);
        json_object_put(namespaces);
        _exit(EXIT_CODE_SUCCESS);
    }
    capture_wait(child, EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL);
    assert_int_equal(rmdir(first_namespace), 0);
    assert_int_equal(rmdir(second_namespace), 0);
    assert_int_equal(rmdir(controller_path), 0);
    assert_string_equal(capture_stdout(), "");
    assert_string_equal(capture_stderr(),
                        "failed NVME_IOCTL_ADMIN_CMD ioctl for /dev/nvme0n1: Structure needs cleaning\n");
}

static int setup(void **state)
{
    (void)state; // Unused parameter

    fail_strndup = false;
    fail_sysconf = false;
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
        cmocka_unit_test_setup_teardown(test_identify_udev_device_vs_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_enumerate_namespaces_nsid_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_enumerate_namespaces_vs_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_command_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_open, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_sysconf, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_posix_memalign, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_failure_to_ioctl, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_allocation_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_get_nsid_from_namespace_device_path_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_get_nsid_from_namespace_device_path_open_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_get_nsid_from_namespace_device_path_ioctl_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_for_namespace_device_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_for_namespace_device_nsid_failure, setup,
                                        teardown),
        cmocka_unit_test_setup_teardown(test_nvme_identify_namespace_vs_for_namespace_device_vs_failure, setup,
                                        teardown),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
