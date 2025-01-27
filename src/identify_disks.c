
#include <dirent.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "debug.h"
#include "identify_disks.h"
#include "nvme.h"
#include "util.h"

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
        fprintf(stderr, "failed scandir for %s: %m\n", ctrl->sys_path);
        return 1;
    }

    DEBUG_PRINTF("found %d namespace(s) for controller=%s:\n", n, ctrl->name);
    for (int i = 0; i < n; i++)
    {
        char namespace_path[MAX_PATH];
        snprintf(namespace_path, sizeof(namespace_path), "/dev/%s", namelist[i]->d_name);

        char *vs = nvme_identify_namespace_vs_for_namespace_device(namespace_path);
        if (vs != NULL)
        {
            printf("%s: %s\n", namespace_path, vs);
            free(vs);
        }
        free(namelist[i]);
    }

    free(namelist);
    return 0;
}

/**
 * Check if NVMe vendor in sysfs matches Microsoft's vendor ID.
 */
int is_microsoft_nvme_device(const char *device_name)
{
    char vendor_id_path[MAX_PATH];
    snprintf(vendor_id_path, sizeof(vendor_id_path), "%s/%s/device/vendor", SYS_CLASS_NVME_PATH, device_name);

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
 * Enumerate Microsoft Azure NVMe controllers and identify disks.
 */
int identify_disks(void)
{
    struct dirent **namelist;

    int n = scandir(SYS_CLASS_NVME_PATH, &namelist, is_azure_nvme_controller, alphasort);
    if (n < 0)
    {
        fprintf(stderr, "no NVMe devices in %s: %m\n", SYS_CLASS_NVME_PATH);
        return 0;
    }

    DEBUG_PRINTF("found %d controllers\n", n);
    for (int i = 0; i < n; i++)
    {
        struct nvme_controller ctrl;

        strncpy(ctrl.name, namelist[i]->d_name, sizeof(ctrl.name));
        snprintf(ctrl.dev_path, sizeof(ctrl.dev_path), "/dev/%s", ctrl.name);
        snprintf(ctrl.sys_path, sizeof(ctrl.sys_path), "%s/%s", SYS_CLASS_NVME_PATH, ctrl.name);

        enumerate_namespaces_for_controller(&ctrl);
        free(namelist[i]);
    }

    free(namelist);
    return 0;
}
