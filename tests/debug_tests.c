#include <criterion/criterion.h>
#include <criterion/logging.h>
#include <criterion/redirect.h>

#include "debug.h"

extern char **environ;

static const char *environ_test[] = {
    "ENV1=VALUE1",
    "ENV2=VALUE2",
    "ENV3=VALUE3",
    NULL,
};

static char **original_environ = NULL;

void setup_test_environment()
{
    original_environ = environ;
    environ = (char **)environ_test;
}

void teardown_test_environment()
{
    environ = original_environ;
    debug = false;
}

TestSuite(debug_environment_variables, .init = setup_test_environment, .fini = teardown_test_environment);

Test(debug_environment_variables, debug_environment_variables_with_debug_enabled)
{
    debug = true;
    const char *expected_output =
        "DEBUG: Environment Variables:\n"
        "DEBUG: ENV1=VALUE1\n"
        "DEBUG: ENV2=VALUE2\n"
        "DEBUG: ENV3=VALUE3\n";

    cr_redirect_stderr();

    debug_environment_variables();

    cr_assert_stderr_eq_str(expected_output, "Unexpected output when debug enabled.");
}

Test(debug_environment_variables, debug_environment_variables_with_debug_disabled)
{
    debug = false;

    cr_redirect_stderr();

    debug_environment_variables();

    cr_assert_stderr_eq_str("", "Unexpected output when debug disabled.");
}
