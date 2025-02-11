/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <ctype.h>
#include <dirent.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "debug.h"
#include "identify_disks.h"
#include "nvme.h"

/**
 * Trim trailing whitespace from a string in-place.
 */
void trim_trailing_whitespace(char *str)
{
    size_t len = strlen(str);
    while (len > 0 && isspace((unsigned char)str[len - 1]))
    {
        str[--len] = '\0'; // Replace trailing whitespace with null terminator
    }
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
 * Identify namespace without using vendor-specific command set.
 * Used as a fallback when vendor-specific command set is not supported.
 */
char *identify_namespace_without_vs(const char *controller_sys_path, const char *namespace_path)
{
    char model_name[MAX_PATH] = {0};
    char model_path[MAX_PATH];
    snprintf(model_path, sizeof(model_path), "%s/model", controller_sys_path);

    FILE *file = fopen(model_path, "r");
    if (file == NULL)
    {
        DEBUG_PRINTF("failed to open %s: %m\n", model_path);
        return strdup("");
    }

    char *result = fgets(model_name, sizeof(model_name), file);
    if (result == NULL)
    {
        DEBUG_PRINTF("failed to read model name from %s: %m\n", model_path);
        fclose(file);
        return strdup("");
    }

    fclose(file);

    trim_trailing_whitespace(model_name);
    DEBUG_PRINTF("read model name=\"%s\"\n", model_name);

    if (strcmp(model_name, "MSFT NVMe Accelerator v1.0") == 0)
    {
        // Microsoft Azure NVMe Accelerator v1.0 supports remote OS and data disks.
        // nsid=1 is the OS disk and nsid=2+ for data disks.
        // A data disk's lun id == nsid - 2.
        int nsid = get_nsid_from_namespace_device_path(namespace_path);
        if (nsid == 1)
        {
            return strdup("type=os");
        }
        else
        {
            char *output = NULL;
            if (asprintf(&output, "type=data,lun=%d", nsid - 2) > 0)
            {
                return output;
            }
        }
    }
    else if (strcmp(model_name, "Microsoft NVMe Direct Disk") == 0 ||
             strcmp(model_name, "Microsoft NVMe Direct Disk v2") == 0)
    {
        return strdup("type=local");
    }

    return strdup("");
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
            if (vs[0] == 0)
            {
                free(vs);
                vs = identify_namespace_without_vs(ctrl->sys_path, namespace_path);
            }

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

    FILE *file = fopen(vendor_id_path, "r");
    if (file == NULL)
    {
        return 0;
    }

    unsigned int vendor_id;
    int result = fscanf(file, "%x", &vendor_id);
    fclose(file);

    if (result != 1)
    {
        return 0;
    }

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

        snprintf(ctrl.name, sizeof(ctrl.name), "%s", namelist[i]->d_name);
        snprintf(ctrl.dev_path, sizeof(ctrl.dev_path), "/dev/%s", ctrl.name);
        snprintf(ctrl.sys_path, sizeof(ctrl.sys_path), "%s/%s", SYS_CLASS_NVME_PATH, ctrl.name);

        enumerate_namespaces_for_controller(&ctrl);
        free(namelist[i]);
    }

    free(namelist);
    return 0;
}
