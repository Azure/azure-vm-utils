/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <ctype.h>
#include <errno.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// clang-format off
#include <cmocka.h>
// clang-format on

#include "capture.h"
#include "identify_udev.h"
#include "nvme.h"

char *__real_strdup(const char *str);

char *__wrap_strdup(const char *str)
{
    check_expected_ptr(str);

    char *result = mock_ptr_type(char *);
    if (result == NULL)
    {
        errno = mock_type(int);
    }
    return result;
}

char *__wrap_nvme_identify_namespace_vs_for_namespace_device(const char *namespace_path)
{
    check_expected_ptr(namespace_path);
    return mock_ptr_type(char *);
}

static int setup(void **state)
{
    capture_setup(state);
    unsetenv("DEVNAME");
    return 0;
}

static int teardown(void **state)
{
    capture_teardown(state);
    unsetenv("DEVNAME");
    return 0;
}

static void test_print_udev_key_value(void **state)
{
    (void)state; // Unused parameter

    print_udev_key_value("type", "local");

    assert_string_equal(capture_stdout(), "AZURE_DISK_TYPE=local\n");
    assert_string_equal(capture_stderr(), "");
}

static void test_print_udev_key_values_allocation_failure(void **state)
{
    (void)state; // Unused parameter

    char vs[] = "type=local";

    expect_string(__wrap_strdup, str, vs);
    will_return(__wrap_strdup, NULL);
    will_return(__wrap_strdup, ENOMEM);

    int result = print_udev_key_values_for_vs(vs);

    assert_int_equal(result, 1);
    assert_string_equal(capture_stderr(), "strdup() failed: Cannot allocate memory\n");
    assert_string_equal(capture_stdout(), "");
}

static void test_print_udev_key_values_for_vs_success(void **state)
{
    (void)state; // Unused parameter

    char vs[] = "type=local,index=2,name=nvme-600G-2";

    expect_string(__wrap_strdup, str, vs);
    will_return(__wrap_strdup, __real_strdup(vs));

    int result = print_udev_key_values_for_vs(vs);

    assert_int_equal(result, 0);
    assert_string_equal(capture_stdout(), "AZURE_DISK_TYPE=local\n"
                                          "AZURE_DISK_INDEX=2\n"
                                          "AZURE_DISK_NAME=nvme-600G-2\n");
    assert_string_equal(capture_stderr(), "");
}

static void test_print_udev_key_values_for_vs_failure(void **state)
{
    (void)state; // Unused parameter

    char vs[] = "type=local,index=2,name";

    expect_string(__wrap_strdup, str, vs);
    will_return(__wrap_strdup, __real_strdup(vs));

    int result = print_udev_key_values_for_vs(vs);

    assert_int_equal(result, 1);
    assert_string_equal(capture_stderr(), "failed to parse key-value pair: name\n");
    assert_string_equal(capture_stdout(), "AZURE_DISK_TYPE=local\n"
                                          "AZURE_DISK_INDEX=2\n");
}

static void test_identify_udev_device_allocation_failure(void **state)
{
    (void)state; // Unused parameter

    setenv("DEVNAME", "/dev/nvme0n5", 1);
    char *vs = __real_strdup("type=local");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme0n5");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, vs);
    expect_string(__wrap_strdup, str, vs);
    will_return(__wrap_strdup, NULL);
    will_return(__wrap_strdup, ENOMEM);

    int result = identify_udev_device();

    assert_int_equal(result, 1);
    assert_string_equal(capture_stderr(), "strdup() failed: Cannot allocate memory\n");
    assert_string_equal(capture_stdout(), "AZURE_DISK_VS=type=local\n");
}

static void test_identify_udev_device_success(void **state)
{
    (void)state; // Unused parameter

    setenv("DEVNAME", "/dev/nvme0n5", 1);
    const char *vs = __real_strdup("type=local,index=2,name=nvme-600G-2");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme0n5");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, vs);
    expect_string(__wrap_strdup, str, vs);
    will_return(__wrap_strdup, __real_strdup(vs));

    int result = identify_udev_device();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stdout(), "AZURE_DISK_VS=type=local,index=2,name=nvme-600G-2\n"
                                          "AZURE_DISK_TYPE=local\n"
                                          "AZURE_DISK_INDEX=2\n"
                                          "AZURE_DISK_NAME=nvme-600G-2\n");
    assert_string_equal(capture_stderr(), "");
}

static void test_identify_udev_device_no_devname(void **state)
{
    (void)state; // Unused parameter

    unsetenv("DEVNAME");

    int result = identify_udev_device();

    assert_int_equal(result, 1);
    assert_string_equal(capture_stderr(), "environment variable 'DEVNAME' not set\n");
    assert_string_equal(capture_stdout(), "");
}

static void test_identify_udev_device_vs_failure(void **state)
{
    (void)state; // Unused parameter

    setenv("DEVNAME", "/dev/nvme0n5", 1);

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme0n5");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, NULL);

    int result = identify_udev_device();

    assert_int_equal(result, 1);
    assert_string_equal(capture_stderr(), "failed to query namespace vendor-specific data: /dev/nvme0n5\n");
    assert_string_equal(capture_stdout(), "");
}

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_print_udev_key_value, setup, teardown),
        cmocka_unit_test_setup_teardown(test_print_udev_key_values_allocation_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_print_udev_key_values_for_vs_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_print_udev_key_values_for_vs_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_udev_device_allocation_failure, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_udev_device_success, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_udev_device_no_devname, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_udev_device_vs_failure, setup, teardown),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
