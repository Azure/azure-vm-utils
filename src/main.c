#include <ctype.h>
#include <dirent.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/nvme_ioctl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "nvme.h"
#include "version.h"

#define MAX_PATH 4096
#define MICROSOFT_NVME_VENDOR_ID 0x1414

struct nvme_controller
{
    char name[256];
    char dev_path[MAX_PATH];
    char sys_path[MAX_PATH];
    char model[MAX_PATH];
};

static bool debug = false;
static bool udev_mode = false;

#define DEBUG_PRINTF(fmt, ...)                                                                                         \
    do                                                                                                                 \
    {                                                                                                                  \
        if (debug == true)                                                                                             \
        {                                                                                                              \
            fprintf(stderr, "DEBUG: " fmt, ##__VA_ARGS__);                                                             \
        }                                                                                                              \
    } while (0)

/**
 * Given the path to a namespace, determine the namespace id.
 */
int get_namespace_id_for_path(const char *namespace_path)
{
    unsigned int ctrl, nsid;

    if (sscanf(namespace_path, "/dev/nvme%un%u", &ctrl, &nsid) != 2)
    {
        return -1;
    }

    return nsid;
}

/**
 * Dump environment variables.
 */
void debug_environment_variables()
{
    int i = 0;

    DEBUG_PRINTF("Environment Variables:\n");
    while (environ[i])
    {
        DEBUG_PRINTF("%s\n", environ[i]);
        i++;
    }
}

/**
 * Read file contents as a null-terminated string.
 *
 * For sysfs entries, etc. where the file contents are not null-terminated and
 * we know the contents are just a simple string (e.g. sysfs attributes).
 */
char *read_file_as_string(const char *path)
{
    DEBUG_PRINTF("reading %s...\n", path);

    FILE *file = fopen(path, "r");
    if (file == NULL)
    {
        perror("fopen");
        return NULL;
    }

    // Determine the file size
    if (fseek(file, 0, SEEK_END) < 0)
    {
        perror("fseek");
        fclose(file);
        return NULL;
    }

    long length = ftell(file);
    if (length < 0)
    {
        perror("ftell");
        fclose(file);
        return NULL;
    }

    if (fseek(file, 0, SEEK_SET) < 0)
    {
        perror("fseek");
        fclose(file);
        return NULL;
    }

    // Allocate size of file plus one byte for null.
    char *contents = malloc(length + 1);
    if (contents == NULL)
    {
        perror("malloc");
        fclose(file);
        return NULL;
    }

    // Read file contents.
    size_t bytes_read = fread(contents, 1, length, file);
    if ((long)bytes_read < length)
    {
        DEBUG_PRINTF("short read on %s, contents probably changed", path);
    }

    fclose(file);

    // Null-terminate the string.
    contents[length] = '\0';

    DEBUG_PRINTF("%s => %s\n", path, contents);
    return contents;
}

/**
 * Check if NVMe vendor in sysfs matches Microsoft's vendor ID.
 */
int is_microsoft_nvme_device(const char *device_name)
{
    char vendor_id_path[MAX_PATH];
    snprintf(vendor_id_path, sizeof(vendor_id_path), "/sys/class/nvme/%s/device/vendor", device_name);

    char *vendor_id_string = read_file_as_string(vendor_id_path);
    if (vendor_id_string == NULL)
    {
        return false;
    }

    long int vendor_id = strtol(vendor_id_string, NULL, 16);
    free(vendor_id_string);

    return vendor_id == MICROSOFT_NVME_VENDOR_ID;
}

/**
 * Query the NVMe namespace for the vendor specific data.
 *
 * For Azure devices, the vendor-specific data is current exposed as a string.
 * It will include the type of device and various properties in the format:
 * key1=value1,key2=value2,...\0.
 *
 * Anything beyond the terminating null-byte is currently undefined and
 * consequently ignored.
 */
char *query_namespace_vs(const char *namespace_path)
{
    int nsid = get_namespace_id_for_path(namespace_path);
    if (nsid < 0)
    {
        fprintf(stderr, "failed to parse namespace id: %s\n", namespace_path);
        return NULL;
    }

    int fd = open(namespace_path, O_RDONLY);
    if (fd < 0)
    {
        perror("open");
        return NULL;
    }

    DEBUG_PRINTF("Opened device: %s with namespace id: %d...\n", namespace_path, nsid);

    struct nvme_id_ns *ns = NULL;
    if (posix_memalign((void **)&ns, sysconf(_SC_PAGESIZE), sizeof(struct nvme_id_ns)) != 0)
    {
        perror("posix_memalign");
        close(fd);
        return NULL;
    }

    struct nvme_admin_cmd cmd = {
        .opcode = 0x06, // Identify command
        .nsid = nsid,
        .addr = (unsigned long)ns,
        .data_len = sizeof(ns),
    };

    if (ioctl(fd, NVME_IOCTL_ADMIN_CMD, &cmd) < 0)
    {
        perror("ioctl");
        free(ns);
        close(fd);
        return NULL;
    }

    char *vs = strndup((const char *)ns->vs, sizeof(ns->vs));

    free(ns);
    close(fd);

    return vs;
}

/**
 * Callback for scandir() to filter for NVMe namespaces.
 */
int is_nvme_namespace(const struct dirent *entry)
{
    unsigned int ctrl, nsid;
    char p;

    // Check for NVME controller name format: nvme<ctrl id>n<ns id>
    return sscanf(entry->d_name, "nvme%un%u%c", &ctrl, &nsid, &p) == 2;
}

/**
 * Enumerate namespaces for a controller.
 */
int enumerate_namespaces_for_controller(struct nvme_controller *ctrl)
{
    struct dirent **namelist;

    int n = scandir(ctrl->sys_path, &namelist, is_nvme_namespace, alphasort);
    if (n < 0)
    {
        perror("scandir");
        return 1;
    }

    DEBUG_PRINTF("found %d namespace(s) for controller=%s:\n", n, ctrl->name);
    for (int i = 0; i < n; i++)
    {
        char namespace_path[MAX_PATH];
        snprintf(namespace_path, sizeof(namespace_path), "/dev/%s", namelist[i]->d_name);

        char *vs = query_namespace_vs(namespace_path);
        printf("%s: %s\n", namespace_path, vs);
        free(vs);

        free(namelist[i]);
    }

    free(namelist);
    return 0;
}

/**
 * Callback for scandir() to filter for Microsoft Azure NVMe controllers.
 */
int is_azure_nvme_controller(const struct dirent *entry)
{
    unsigned int ctrl;
    char p;

    // Check for NVME controller name format: nvme<int>
    if (sscanf(entry->d_name, "nvme%u%c", &ctrl, &p) != 1)
    {
        return false;
    }

    return is_microsoft_nvme_device(entry->d_name);
}

/**
 * Enumerate Microsoft Azure NVMe controllers.
 */
int enumerate_azure_nvme_controllers()
{
    struct dirent **namelist;

    int n = scandir("/sys/class/nvme", &namelist, is_azure_nvme_controller, alphasort);
    if (n < 0)
    {
        perror("scandir");
        return 1;
    }

    DEBUG_PRINTF("found %d controllers\n", n);
    for (int i = 0; i < n; i++)
    {
        struct nvme_controller ctrl;

        strncpy(ctrl.name, namelist[i]->d_name, sizeof(ctrl.name));
        snprintf(ctrl.dev_path, sizeof(ctrl.dev_path), "/dev/%s", ctrl.name);
        snprintf(ctrl.sys_path, sizeof(ctrl.sys_path), "/sys/class/nvme/%s", ctrl.name);

        enumerate_namespaces_for_controller(&ctrl);
        free(namelist[i]);
    }

    free(namelist);
    return 0;
}

/**
 * Print a udev key-value pair for environment variable.
 */
void print_udev_key_value(const char *key, const char *value)
{
    printf("AZURE_NVME_");
    while (*key)
    {
        putchar(toupper((unsigned char)*key));
        key++;
    }
    printf("=%s\n", value);
}

/**
 * Print udev environment variables for all vs properties.
 *
 * Example parsing for vs:
 *     type=local,index=2,name=nvme-600G-2
 *
 * Environment variables printed include:
 *     AZURE_NVME_TYPE=local
 *     AZURE_NVME_INDEX=2
 *     AZURE_NVME_NAME=nvme-600G-2
 */
int parse_vs_for_udev_import(char *vs)
{
    char *vs_copy = strdup(vs);
    char *outer_saveptr = NULL;
    char *inner_saveptr = NULL;

    char *pair = strtok_r(vs_copy, ",", &outer_saveptr);
    while (pair != NULL)
    {
        char *key = strtok_r(pair, "=", &inner_saveptr);
        char *value = strtok_r(NULL, "=", &inner_saveptr);

        if (key == NULL || value == NULL)
        {
            fprintf(stderr, "failed to parse key-value pair: %s\n", pair);
            free(vs_copy);
            return 1;
        }

        print_udev_key_value(key, value);
        pair = strtok_r(NULL, ",", &outer_saveptr);
    }

    free(vs_copy);
    return 0;
}

/**
 * Execute udev mode, printing out environment variables for import.
 *
 * AZURE_NVME_VS: <vendor specific data>
 * AZURE_NVME_TYPE: <type, if specified>
 * AZURE_NVME_INDEX: <index for data disk, if specified>
 * AZURE_NVME_NAME: <name for disk, if specified>
 * etc...
 */
int execute_udev_import(void)
{
    const char *dev_name = getenv("DEVNAME");
    if (dev_name == NULL)
    {
        fprintf(stderr, "environment variable 'DEVNAME' not set\n");
        return 1;
    }

    char *vs = query_namespace_vs(dev_name);
    if (vs == NULL)
    {
        fprintf(stderr, "failed to query namespace vendor-specific data: %s\n", dev_name);
        return 1;
    }

    printf("AZURE_NVME_VS=%s\n", vs);
    parse_vs_for_udev_import(vs);
    free(vs);

    return 0;
}

int main(int argc, const char **argv)
{
    for (int i = 1; i < argc; i++)
    {
        if (strcmp(argv[i], "--debug") == 0)
        {
            debug = true;
            continue;
        }
        if (strcmp(argv[i], "--udev") == 0)
        {
            udev_mode = true;
            continue;
        }
        if (strcmp(argv[i], "--version") == 0)
        {
            printf("azure-nvme-id v%s\n", VERSION);
            return 0;
        }
        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0)
        {
            printf("Usage: %s [--debug] [--udev|--help|--version]\n", argv[0]);
            return 0;
        }
    }

    if (debug)
    {
        debug_environment_variables();
    }

    if (udev_mode)
    {
        return execute_udev_import();
    }

    return enumerate_azure_nvme_controllers();
}
