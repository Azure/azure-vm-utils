/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <errno.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <unistd.h>

// clang-format off
#include <cmocka.h>
// clang-format on

#include "capture.h"
#include "checked.h"

int __wrap_json_object_array_add(json_object *obj, json_object *value)
{
    (void)obj;
    (void)value;
    errno = ENOMEM;
    return -1;
}

json_object *__wrap_json_object_new_array(void)
{
    errno = ENOMEM;
    return NULL;
}

json_object *__wrap_json_object_new_int(int value)
{
    (void)value;
    errno = ENOMEM;
    return NULL;
}

json_object *__wrap_json_object_new_object(void)
{
    errno = ENOMEM;
    return NULL;
}

json_object *__wrap_json_object_new_string(const char *value)
{
    (void)value;
    errno = ENOMEM;
    return NULL;
}

int __wrap_json_object_object_add(json_object *obj, const char *key, json_object *value)
{
    (void)obj;
    (void)key;
    (void)value;
    errno = ENOMEM;
    return -1;
}

const char *__wrap_json_object_to_json_string_ext(json_object *obj, int flags)
{
    (void)obj;
    (void)flags;
    errno = ENOMEM;
    return NULL;
}

char *__wrap_strdup(const char *str)
{
    (void)str;
    errno = ENOMEM;
    return NULL;
}

char *__wrap_strndup(const char *str, size_t length)
{
    (void)str;
    (void)length;
    errno = ENOMEM;
    return NULL;
}

static void test_json_object_array_add_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_array_add_checked(NULL, NULL);
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_json_object_new_array_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_new_array_checked();
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_json_object_new_int_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_new_int_checked(1);
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_json_object_new_object_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_new_object_checked();
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_json_object_new_string_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_new_string_checked("test");
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_json_object_object_add_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_object_add_checked(NULL, "key", NULL);
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_json_object_to_json_string_ext_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        json_object_to_json_string_ext_checked(NULL, 0);
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_strdup_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        strdup_checked("test");
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

static void test_strndup_checked_failure(void **state)
{
    (void)state;

    pid_t child = capture_fork();
    if (child == 0)
    {
        strndup_checked("test", 4);
        _exit(EXIT_SUCCESS);
    }
    capture_wait(child, ENOMEM);
}

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_json_object_array_add_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_json_object_new_array_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_json_object_new_int_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_json_object_new_object_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_json_object_new_string_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_json_object_object_add_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_json_object_to_json_string_ext_checked_failure, capture_setup,
                                        capture_teardown),
        cmocka_unit_test_setup_teardown(test_strdup_checked_failure, capture_setup, capture_teardown),
        cmocka_unit_test_setup_teardown(test_strndup_checked_failure, capture_setup, capture_teardown),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
