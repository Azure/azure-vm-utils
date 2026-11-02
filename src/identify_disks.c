/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <json-c/json.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "checked.h"
#include "debug.h"
#include "exit_code.h"
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
char *identify_namespace_without_vs(const char *controller_sys_path, int nsid)
{
    char model_name[MAX_PATH] = {0};
    char model_path[MAX_PATH];
    snprintf(model_path, sizeof(model_path), "%s/model", controller_sys_path);

    FILE *file = fopen(model_path, "r");
    if (file == NULL)
    {
        fprintf(stderr, "failed to open %s: %m\n", model_path);
        // Keep the namespace with empty properties when fallback metadata is unavailable.
        return strdup_checked("");
    }

    char *result = fgets(model_name, sizeof(model_name), file);
    if (result == NULL)
    {
        if (ferror(file))
        {
            fprintf(stderr, "failed to read model name from %s: %m\n", model_path);
        }
        else
        {
            fprintf(stderr, "failed to read model name from %s: unexpected end of file\n", model_path);
        }
        fclose(file);
        // Keep the namespace with empty properties when fallback metadata is unavailable.
        return strdup_checked("");
    }

    fclose(file);

    trim_trailing_whitespace(model_name);
    DEBUG_PRINTF("read model name=\"%s\"\n", model_name);

    if (strcmp(model_name, "MSFT NVMe Accelerator v1.0") == 0)
    {
        // Microsoft Azure NVMe Accelerator v1.0 supports remote OS and data disks.
        // nsid=1 is the OS disk and nsid=2+ for data disks.
        // A data disk's lun id == nsid - 2.
        if (nsid == 1)
        {
            return strdup_checked("type=os");
        }
        else
        {
            char *output = NULL;
            if (asprintf(&output, "type=data,lun=%d", nsid - 2) < 0)
            {
                fprintf(stderr, "asprintf() failed: %m\n");
                exit(EXIT_CODE_NO_MEMORY);
            }
            return output;
        }
    }
    else if (strcmp(model_name, "Microsoft NVMe Direct Disk") == 0 ||
             strcmp(model_name, "Microsoft NVMe Direct Disk v2") == 0)
    {
        return strdup_checked("type=local");
    }

    return strdup_checked("");
}

/**
 * Parse a vs string and turn it into a JSON dictionary.
 * Example: "type=local,index=2,name=nvme-600G-2"
 */
json_object *parse_vs_string(const char *vs)
{
    json_object *vs_obj = json_object_new_object_checked();
    char *vs_copy = strdup_checked(vs);
    char *token;
    char *rest = vs_copy;

    while ((token = strtok_r(rest, ",", &rest)))
    {
        char *key = strtok_r(token, "=", &token);
        char *value = strtok_r(NULL, "=", &token);

        if (key != NULL && value != NULL)
        {
            int int_value = atoi(value);
            if ((strcmp(key, "lun") == 0) || (strcmp(key, "index") == 0))
            {
                if (int_value == 0 && strcmp(value, "0") != 0)
                {
                    fprintf(stderr, "failed to parse vs=%s key=%s value=%s as int\n", vs, key, value);
                    // Preserve the reported value as a string instead of failing enumeration.
                    json_object_object_add_checked(vs_obj, key, json_object_new_string_checked(value));
                }
                else
                {
                    json_object_object_add_checked(vs_obj, key, json_object_new_int_checked(int_value));
                }
            }
            else
            {
                json_object_object_add_checked(vs_obj, key, json_object_new_string_checked(value));
            }
        }
    }

    free(vs_copy);
    return vs_obj;
}

/**
 * Enumerate namespaces for a controller.
 */
int enumerate_namespaces_for_controller(struct nvme_controller *ctrl, struct context *ctx,
                                        json_object *namespaces_array)
{
    struct dirent **namelist;

    int n = scandir(ctrl->sys_path, &namelist, is_nvme_namespace, versionsort);
    if (n < 0)
    {
        // A controller removed during enumeration has no remaining namespaces to report.
        int result = errno == ENOENT ? EXIT_CODE_SUCCESS : EXIT_CODE_NAMESPACE_SCAN;
        fprintf(stderr, "failed scandir for %s: %m\n", ctrl->sys_path);
        return result;
    }

    DEBUG_PRINTF("found %d namespace(s) for controller=%s:\n", n, ctrl->name);
    for (int i = 0; i < n; i++)
    {
        char *id;
        char namespace_path[MAX_PATH];
        snprintf(namespace_path, sizeof(namespace_path), "/dev/%s", namelist[i]->d_name);

        int nsid = get_nsid_from_namespace_device_path(namespace_path);
        char *vs = nvme_identify_namespace_vs(namespace_path, nsid);

        json_object *namespace_obj = json_object_new_object_checked();
        json_object_object_add_checked(namespace_obj, "path", json_object_new_string_checked(namespace_path));
        json_object_object_add_checked(namespace_obj, "model", json_object_new_string_checked(ctrl->model));
        json_object_object_add_checked(namespace_obj, "nsid", json_object_new_int_checked(nsid));
        json_object_array_add_checked(namespaces_array, namespace_obj);

        if (vs[0] == 0)
        {
            id = identify_namespace_without_vs(ctrl->sys_path, nsid);
        }
        else
        {
            id = strdup_checked(vs);
        }

        if (ctx->output_format == PLAIN)
        {
            printf("%s: %s\n", namespace_path, id);
        }

        json_object_object_add_checked(namespace_obj, "properties", parse_vs_string(id));
        free(id);
        json_object_object_add_checked(namespace_obj, "vs", json_object_new_string_checked(vs));
        free(vs);

        free(namelist[i]);
    }

    free(namelist);
    return EXIT_CODE_SUCCESS;
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
        fprintf(stderr, "failed to open %s: %m\n", vendor_id_path);
        // Skip unverified controllers so other devices can still be enumerated.
        return 0;
    }

    unsigned int vendor_id;
    int result = fscanf(file, "%x", &vendor_id);
    if (result != 1)
    {
        if (ferror(file))
        {
            fprintf(stderr, "failed to read vendor ID from %s: %m\n", vendor_id_path);
        }
        else
        {
            fprintf(stderr, "failed to parse vendor ID from %s: expected a hexadecimal vendor ID\n", vendor_id_path);
        }
        fclose(file);
        // Skip unverified controllers so other devices can still be enumerated.
        return 0;
    }

    fclose(file);
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
 * Initialize nvme_controller structure.  Read model name from sysfs,
 * trimming off whitespaces.
 */
bool initialize_nvme_controller(struct nvme_controller *ctrl, const char *name)
{
    char model_path[sizeof(ctrl->sys_path) + sizeof("/model")];

    snprintf(ctrl->name, sizeof(ctrl->name), "%s", name);
    snprintf(ctrl->dev_path, sizeof(ctrl->dev_path), "/dev/%s", ctrl->name);
    snprintf(ctrl->sys_path, sizeof(ctrl->sys_path), "%s/%s", SYS_CLASS_NVME_PATH, ctrl->name);
    snprintf(model_path, sizeof(model_path), "%s/model", ctrl->sys_path);

    FILE *file = fopen(model_path, "r");
    if (file == NULL)
    {
        fprintf(stderr, "failed to open %s: %m\n", model_path);
        return false;
    }

    char *result = fgets(ctrl->model, sizeof(ctrl->model), file);
    if (result == NULL)
    {
        if (ferror(file))
        {
            fprintf(stderr, "failed to read model name from %s: %m\n", model_path);
        }
        else
        {
            fprintf(stderr, "failed to read model name from %s: unexpected end of file\n", model_path);
        }
        fclose(file);
        return false;
    }

    fclose(file);
    trim_trailing_whitespace(ctrl->model);
    return true;
}

/**
 * Enumerate Microsoft Azure NVMe controllers and identify disks.
 */
int identify_disks(struct context *ctx)
{
    struct dirent **namelist = NULL;
    int result = EXIT_CODE_SUCCESS;
    json_object *namespaces_array = json_object_new_array_checked();

    int n = scandir(SYS_CLASS_NVME_PATH, &namelist, is_azure_nvme_controller, versionsort);
    if (n < 0)
    {
        // Systems without NVMe devices may have no controller directory.
        result = errno == ENOENT ? EXIT_CODE_SUCCESS : EXIT_CODE_CONTROLLER_SCAN;
        fprintf(stderr, "no NVMe devices in %s: %m\n", SYS_CLASS_NVME_PATH);
        n = 0;
    }

    DEBUG_PRINTF("found %d controllers\n", n);
    for (int i = 0; i < n; i++)
    {
        struct nvme_controller ctrl;

        if (initialize_nvme_controller(&ctrl, namelist[i]->d_name))
        {
            result = enumerate_namespaces_for_controller(&ctrl, ctx, namespaces_array);
            if (result != EXIT_CODE_SUCCESS)
            {
                break;
            }
        }
        else
        {
            // Skip controllers with unavailable model metadata and continue enumeration.
            fprintf(stderr, "failed to initialize NVMe controller %s\n", namelist[i]->d_name);
        }
    }

    for (int i = 0; i < n; i++)
    {
        free(namelist[i]);
    }
    free(namelist);

    if (result == EXIT_CODE_SUCCESS && ctx->output_format == JSON)
    {
        int flags = JSON_C_TO_STRING_NOSLASHESCAPE | JSON_C_TO_STRING_PRETTY | JSON_C_TO_STRING_SPACED;

        const char *json_output = json_object_to_json_string_ext_checked(namespaces_array, flags);
        printf("%s\n", json_output);
    }

    json_object_put(namespaces_array);
    return result;
}
