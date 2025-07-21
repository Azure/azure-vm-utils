/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <setjmp.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// clange-format off
#include <cmocka.h>
// clange-format on

#include "capture.h"
#include "debug.h"

extern char **environ;

static const char *environ_test[] = {
    "ENV1=VALUE1",
    "ENV2=VALUE2",
    "ENV3=VALUE3",
    NULL,
};
static char **original_environ = NULL;

static int setup(void **state)
{
    (void)state; // Unused parameter

    original_environ = environ;
    environ = (char **)environ_test;
    capture_setup(state);

    return 0;
}

static int teardown(void **state)
{
    (void)state; // Unused parameter

    environ = original_environ;
    debug = false;
    capture_teardown(state);

    return 0;
}

static void test_debug_environment_variables_with_debug_enabled(void **state)
{
    (void)state; // Unused parameter

    debug = true;
    const char *expected_output = "DEBUG: Environment Variables:\n"
                                  "DEBUG: ENV1=VALUE1\n"
                                  "DEBUG: ENV2=VALUE2\n"
                                  "DEBUG: ENV3=VALUE3\n";

    debug_environment_variables();

    assert_string_equal(capture_stderr(), expected_output);
    assert_string_equal(capture_stdout(), "");
}

static void test_debug_environment_variables_with_debug_disabled(void **state)
{
    (void)state; // Unused parameter

    debug = false;

    debug_environment_variables();

    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "");
}

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_debug_environment_variables_with_debug_enabled, setup, teardown),
        cmocka_unit_test_setup_teardown(test_debug_environment_variables_with_debug_disabled, setup, teardown),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
