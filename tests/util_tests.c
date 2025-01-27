/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <setjmp.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// clange-format off
#include <cmocka.h>
// clange-format on

#include "debug.h"
#include "util.h"

bool debug = false;
bool use_mocks = true; // Global variable to control whether mocks are enabled

FILE *__real_fopen(const char *path, const char *mode);
FILE *__wrap_fopen(const char *path, const char *mode)
{
    if (!use_mocks)
    {
        return __real_fopen(path, mode);
    }
    check_expected_ptr(path);
    check_expected_ptr(mode);
    return mock_ptr_type(FILE *);
}

int __real_fseek(FILE *stream, long offset, int whence);
int __wrap_fseek(FILE *stream, long offset, int whence)
{
    if (!use_mocks)
    {
        return __real_fseek(stream, offset, whence);
    }
    check_expected_ptr(stream);
    check_expected(offset);
    check_expected(whence);
    return mock_type(int);
}

long __real_ftell(FILE *stream);
long __wrap_ftell(FILE *stream)
{
    if (!use_mocks)
    {
        return __real_ftell(stream);
    }
    check_expected_ptr(stream);
    return mock_type(long);
}

size_t __real_fread(void *ptr, size_t size, size_t nmemb, FILE *stream);
size_t __wrap_fread(void *ptr, size_t size, size_t nmemb, FILE *stream)
{
    if (!use_mocks)
    {
        return __real_fread(ptr, size, nmemb, stream);
    }
    check_expected_ptr(ptr);
    check_expected(size);
    check_expected(nmemb);
    check_expected_ptr(stream);

    size_t ret = mock_type(size_t);
    if (ret > 0)
    {
        char *src_contents = mock_ptr_type(char *);
        strncpy(ptr, src_contents, ret);
    }

    return ret;
}

int __real_fclose(FILE *stream);
int __wrap_fclose(FILE *stream)
{
    if (!use_mocks)
    {
        return __real_fclose(stream);
    }
    check_expected_ptr(stream);
    return mock_type(int);
}

void *__real_malloc(size_t size);
void *__wrap_malloc(size_t size)
{
    if (!use_mocks)
    {
        return __real_malloc(size);
    }
    check_expected(size);
    return mock_ptr_type(void *);
}

// Setup function to reset use_mocks to true
static int setup(void **state)
{
    (void)state; // Unused parameter
    use_mocks = true;
    return 0;
}

static void test_read_file_as_string_success(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/path/to/file";
    const char *file_contents = "file contents";
    char *malloc_buffer = __real_malloc(sizeof(file_contents));

    expect_string(__wrap_fopen, path, path);
    expect_string(__wrap_fopen, mode, "r");
    will_return(__wrap_fopen, (FILE *)0x1);

    expect_any(__wrap_fseek, stream);
    expect_value(__wrap_fseek, offset, 0);
    expect_value(__wrap_fseek, whence, SEEK_END);
    will_return(__wrap_fseek, 0);

    expect_any(__wrap_ftell, stream);
    will_return(__wrap_ftell, strlen(file_contents));

    expect_any(__wrap_fseek, stream);
    expect_value(__wrap_fseek, offset, 0);
    expect_value(__wrap_fseek, whence, SEEK_SET);
    will_return(__wrap_fseek, 0);

    expect_value(__wrap_malloc, size, strlen(file_contents) + 1);
    will_return(__wrap_malloc, (void *)malloc_buffer);

    expect_any(__wrap_fread, ptr);
    expect_value(__wrap_fread, size, 1);
    expect_value(__wrap_fread, nmemb, strlen(file_contents));
    expect_any(__wrap_fread, stream);
    will_return(__wrap_fread, strlen(file_contents));
    will_return(__wrap_fread, file_contents);

    expect_any(__wrap_fclose, stream);
    will_return(__wrap_fclose, 0);

    char *result = read_file_as_string(path);
    assert_non_null(result);
    assert_string_equal(result, file_contents);

    free(malloc_buffer);
}

static void test_read_file_as_string_fopen_failure(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/path/to/nonexistent/file";

    expect_string(__wrap_fopen, path, path);
    expect_string(__wrap_fopen, mode, "r");
    will_return(__wrap_fopen, NULL);

    char *result = read_file_as_string(path);
    assert_null(result);
}

static void test_read_file_as_string_malloc_failure(void **state)
{
    (void)state; // Unused parameter

    const char *path = "/path/to/file";
    const char *file_contents = "file contents";

    expect_string(__wrap_fopen, path, path);
    expect_string(__wrap_fopen, mode, "r");
    will_return(__wrap_fopen, (FILE *)0x1);

    expect_any(__wrap_fseek, stream);
    expect_value(__wrap_fseek, offset, 0);
    expect_value(__wrap_fseek, whence, SEEK_END);
    will_return(__wrap_fseek, 0);

    expect_any(__wrap_ftell, stream);
    will_return(__wrap_ftell, strlen(file_contents));

    expect_any(__wrap_fseek, stream);
    expect_value(__wrap_fseek, offset, 0);
    expect_value(__wrap_fseek, whence, SEEK_SET);
    will_return(__wrap_fseek, 0);

    expect_value(__wrap_malloc, size, strlen(file_contents) + 1);
    will_return(__wrap_malloc, NULL);

    expect_any(__wrap_fclose, stream);
    will_return(__wrap_fclose, 0);

    char *result = read_file_as_string(path);
    assert_null(result);
}

static void test_read_file_as_string_no_mocks(void **state)
{
    (void)state; // Unused parameter

    use_mocks = false; // Disable mocks

    const char *path = "test_file.txt";
    const char *file_contents = "file contents";

    // Create a temporary file and write contents to it
    FILE *file = fopen(path, "w");
    assert_non_null(file);
    fwrite(file_contents, 1, strlen(file_contents), file);
    fclose(file);

    // Read the file using the function
    char *result = read_file_as_string(path);
    assert_non_null(result);
    assert_string_equal(result, file_contents);

    // Clean up
    free(result);
    remove(path);
}

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup(test_read_file_as_string_success, setup),
        cmocka_unit_test_setup(test_read_file_as_string_fopen_failure, setup),
        cmocka_unit_test_setup(test_read_file_as_string_malloc_failure, setup),
        cmocka_unit_test_setup(test_read_file_as_string_no_mocks, setup),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
