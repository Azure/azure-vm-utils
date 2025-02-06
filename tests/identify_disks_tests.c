#include <dirent.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

// clang-format off
#include <cmocka.h>
// clang-format on

#include "capture.h"
#include "identify_disks.h"

#define MSFT_NVME_ACCELERATOR_MODEL_V1 "MSFT NVMe Accelerator v1.0              \n"

char *fake_sys_class_nvme_path = "/sys/class/nvme";

char *__wrap_nvme_identify_namespace_vs_for_namespace_device(const char *namespace_path)
{
    check_expected_ptr(namespace_path);
    return mock_ptr_type(char *);
}

static void remove_temp_dir(const char *path)
{
    struct dirent *entry;
    DIR *dir = opendir(path);

    if (dir == NULL)
    {
        return;
    }

    while ((entry = readdir(dir)) != NULL)
    {
        char full_path[MAX_PATH];
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
        {
            continue;
        }
        snprintf(full_path, sizeof(full_path), "%s/%s", path, entry->d_name);
        if (entry->d_type == DT_DIR)
        {
            remove_temp_dir(full_path);
        }
        else
        {
            remove(full_path);
        }
    }

    closedir(dir);
    rmdir(path);
}

static void create_intermediate_dirs(const char *path)
{
    char temp_path[MAX_PATH];
    snprintf(temp_path, sizeof(temp_path), "%s", path);

    char *p = temp_path;
    while (*p)
    {
        if (*p == '/')
        {
            *p = '\0';
            mkdir(temp_path, 0755);
            *p = '/';
        }
        p++;
    }
}

static void create_dir(const char *base_path, const char *sub_path)
{
    char full_path[MAX_PATH];
    snprintf(full_path, sizeof(full_path), "%s/%s", base_path, sub_path);
    create_intermediate_dirs(full_path);
    mkdir(full_path, 0755);
}

static void create_file(const char *base_path, const char *sub_path, const char *content)
{
    char full_path[MAX_PATH];
    snprintf(full_path, sizeof(full_path), "%s/%s", base_path, sub_path);
    create_intermediate_dirs(full_path);

    FILE *file = fopen(full_path, "w");
    if (file == NULL)
    {
        perror("fopen");
        return;
    }
    fputs(content, file);
    fclose(file);
}

static int setup(void **state)
{
    capture_setup(state);

    char template[] = "/tmp/nvme_test_XXXXXX";
    char *temp_path = mkdtemp(template);
    if (temp_path == NULL)
    {
        perror("mkdtemp");
        return -1;
    }

    *state = strdup(temp_path);
    fake_sys_class_nvme_path = *state;

    return 0;
}

static int teardown(void **state)
{
    capture_teardown(state);

    if (*state != NULL)
    {
        remove_temp_dir(*state);
        free(*state);
        *state = NULL;
    }

    fake_sys_class_nvme_path = SYS_CLASS_NVME_PATH;
    return 0;
}

static void test_trim_trailing_whitespace(void **state)
{
    (void)state; // Unused parameter

    struct
    {
        char input[MAX_PATH];
        char expected[MAX_PATH];
    } test_cases[] = {{"NoTrailingWhitespace", "NoTrailingWhitespace"},
                      {"TrailingSpaces   ", "TrailingSpaces"},
                      {"TrailingTabs\t\t\t", "TrailingTabs"},
                      {"TrailingNewline\n", "TrailingNewline"},
                      {"TrailingMixed   \t\n", "TrailingMixed"},
                      {"", ""},
                      {"\0", "\0"}};

    for (size_t i = 0; i < sizeof(test_cases) / sizeof(test_cases[0]); i++)
    {
        trim_trailing_whitespace(test_cases[i].input);
        assert_string_equal(test_cases[i].input, test_cases[i].expected);
    }
}

static void test_identify_disks_no_sys_class_nvme_present(void **state)
{
    (void)state; // Unused parameter

    char expected_string[1024];
    snprintf(expected_string, sizeof(expected_string), "no NVMe devices in %s: No such file or directory\n",
             fake_sys_class_nvme_path);
    remove_temp_dir(fake_sys_class_nvme_path);

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), expected_string);
    assert_string_equal(capture_stdout(), "");
}

static void test_identify_disks_no_nvme_devices(void **state)
{
    (void)state; // Unused parameter

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "");
}

static void test_identify_disks_vs_error(void **state)
{
    (void)state; // Unused parameter

    // nvme5: microsoft disk, empty vs for nsid=2, error on nsid=3 (should be
    // skipped)
    create_file(fake_sys_class_nvme_path, "nvme5/device/vendor", "0x1414");
    create_file(fake_sys_class_nvme_path, "nvme5/model", "Unknown model");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n1");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n2");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n3");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n4");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme5n1value1,key2=nvme5n1value2"));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n2");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n3");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, NULL);
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n4");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme5n4value1,key2=nvme5n4value2"));

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "/dev/nvme5n1: key1=nvme5n1value1,key2=nvme5n1value2\n"
                                          "/dev/nvme5n2: \n"
                                          "/dev/nvme5n4: key1=nvme5n4value1,key2=nvme5n4value2\n");
}

static void test_identify_disks_success_no_namespaces(void **state)
{
    (void)state; // Unused parameter

    create_file(fake_sys_class_nvme_path, "nvme0/device/vendor", "0x1414");

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "");
}

static void test_identify_disks_success_one_namespace(void **state)
{
    (void)state; // Unused parameter

    create_file(fake_sys_class_nvme_path, "nvme1/device/vendor", "0x1414");
    create_dir(fake_sys_class_nvme_path, "nvme1/nvme1n1");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme1n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme1n1value1,key2=nvme1n1value2"));

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "/dev/nvme1n1: key1=nvme1n1value1,key2=nvme1n1value2\n");
}

static void test_identify_disks_success_two_namespaces(void **state)
{
    (void)state; // Unused parameter

    create_file(fake_sys_class_nvme_path, "nvme2/device/vendor", "0x1414");
    create_dir(fake_sys_class_nvme_path, "nvme2/nvme2n1");
    create_dir(fake_sys_class_nvme_path, "nvme2/nvme2n2");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme2n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme2n1value1,key2=nvme2n1value2"));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme2n2");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme2n2value1,key2=nvme2n2value2"));

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "/dev/nvme2n1: key1=nvme2n1value1,key2=nvme2n1value2\n"
                                          "/dev/nvme2n2: key1=nvme2n2value1,key2=nvme2n2value2\n");
}

static void test_identify_disks_success_non_microsoft_controller(void **state)
{
    (void)state; // Unused parameter

    create_file(fake_sys_class_nvme_path, "nvme4/device/vendor", "0x0000");
    create_dir(fake_sys_class_nvme_path, "nvme4/nvme4n1");
    create_dir(fake_sys_class_nvme_path, "nvme4/nvme4n2");

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "");
}

static void test_identify_disks_nvme_accelerator_v1_with_vs(void **state)
{
    (void)state; // Unused parameter

    create_file(fake_sys_class_nvme_path, "nvme6/device/vendor", "0x1414");
    create_dir(fake_sys_class_nvme_path, "nvme6/nvme6n1");
    create_file(fake_sys_class_nvme_path, "nvme6/model", MSFT_NVME_ACCELERATOR_MODEL_V1);

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme6n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme6n1value1,key2=nvme6n1value2"));

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "/dev/nvme6n1: key1=nvme6n1value1,key2=nvme6n1value2\n");
}

static void test_identify_disks_nvme_accelerator_v1_without_vs(void **state)
{
    (void)state; // Unused parameter

    create_file(fake_sys_class_nvme_path, "nvme7/device/vendor", "0x1414");
    create_file(fake_sys_class_nvme_path, "nvme7/model", MSFT_NVME_ACCELERATOR_MODEL_V1);
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n1");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n2");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n3");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n4");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n9");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n2");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n3");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n4");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n9");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "/dev/nvme7n1: type=os\n"
                                          "/dev/nvme7n2: type=data,lun=0\n"
                                          "/dev/nvme7n3: type=data,lun=1\n"
                                          "/dev/nvme7n4: type=data,lun=2\n"
                                          "/dev/nvme7n9: type=data,lun=7\n");
}

static void test_identify_disks_combined(void **state)
{
    (void)state; // Unused parameter

    // nvme0: microsoft disk, no namespaces
    create_file(fake_sys_class_nvme_path, "nvme0/device/vendor", "0x1414");

    // nvme1: microsoft disk, one namespace
    create_file(fake_sys_class_nvme_path, "nvme1/device/vendor", "0x1414");
    create_dir(fake_sys_class_nvme_path, "nvme1/nvme1n1");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme1n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme1n1value1,key2=nvme1n1value2"));

    // nvme2: microsoft disk, two namespaces
    create_file(fake_sys_class_nvme_path, "nvme2/device/vendor", "0x1414");
    create_dir(fake_sys_class_nvme_path, "nvme2/nvme2n1");
    create_dir(fake_sys_class_nvme_path, "nvme2/nvme2n2");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme2n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme2n1value1,key2=nvme2n1value2"));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme2n2");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme2n2value1,key2=nvme2n2value2"));

    // nvme4: non-microsoft disk
    create_file(fake_sys_class_nvme_path, "nvme4/device/vendor", "0x0000");
    create_dir(fake_sys_class_nvme_path, "nvme4/nvme4n1");
    create_dir(fake_sys_class_nvme_path, "nvme4/nvme4n2");

    // nvme5: microsoft disk, empty vs for nsid=2, error on nsid=3 (should be
    // skipped)
    create_file(fake_sys_class_nvme_path, "nvme5/device/vendor", "0x1414");
    create_file(fake_sys_class_nvme_path, "nvme5/model", "Unknown model");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n1");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n2");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n3");
    create_dir(fake_sys_class_nvme_path, "nvme5/nvme5n4");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme5n1value1,key2=nvme5n1value2"));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n2");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n3");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, NULL);
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme5n4");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme5n4value1,key2=nvme5n4value2"));

    // nvme6: remote accelerator v1 with vs
    create_file(fake_sys_class_nvme_path, "nvme6/device/vendor", "0x1414");
    create_dir(fake_sys_class_nvme_path, "nvme6/nvme6n1");
    create_file(fake_sys_class_nvme_path, "nvme6/model", MSFT_NVME_ACCELERATOR_MODEL_V1);

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme6n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device,
                strdup("key1=nvme6n1value1,key2=nvme6n1value2"));

    // nvme7: remote accelerator v1 without vs
    create_file(fake_sys_class_nvme_path, "nvme7/device/vendor", "0x1414");
    create_file(fake_sys_class_nvme_path, "nvme7/model", MSFT_NVME_ACCELERATOR_MODEL_V1);
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n1");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n2");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n3");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n4");
    create_dir(fake_sys_class_nvme_path, "nvme7/nvme7n9");

    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n1");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n2");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n3");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n4");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));
    expect_string(__wrap_nvme_identify_namespace_vs_for_namespace_device, namespace_path, "/dev/nvme7n9");
    will_return(__wrap_nvme_identify_namespace_vs_for_namespace_device, strdup(""));

    int result = identify_disks();

    assert_int_equal(result, 0);
    assert_string_equal(capture_stderr(), "");
    assert_string_equal(capture_stdout(), "/dev/nvme1n1: key1=nvme1n1value1,key2=nvme1n1value2\n"
                                          "/dev/nvme2n1: key1=nvme2n1value1,key2=nvme2n1value2\n"
                                          "/dev/nvme2n2: key1=nvme2n2value1,key2=nvme2n2value2\n"
                                          "/dev/nvme5n1: key1=nvme5n1value1,key2=nvme5n1value2\n"
                                          "/dev/nvme5n2: \n"
                                          "/dev/nvme5n4: key1=nvme5n4value1,key2=nvme5n4value2\n"
                                          "/dev/nvme6n1: key1=nvme6n1value1,key2=nvme6n1value2\n"
                                          "/dev/nvme7n1: type=os\n"
                                          "/dev/nvme7n2: type=data,lun=0\n"
                                          "/dev/nvme7n3: type=data,lun=1\n"
                                          "/dev/nvme7n4: type=data,lun=2\n"
                                          "/dev/nvme7n9: type=data,lun=7\n");
}

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_trim_trailing_whitespace),
        cmocka_unit_test_setup_teardown(test_identify_disks_no_sys_class_nvme_present, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_no_nvme_devices, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_vs_error, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_success_no_namespaces, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_success_one_namespace, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_success_two_namespaces, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_success_non_microsoft_controller, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_nvme_accelerator_v1_with_vs, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_nvme_accelerator_v1_without_vs, setup, teardown),
        cmocka_unit_test_setup_teardown(test_identify_disks_combined, setup, teardown),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
