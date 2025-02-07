/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __IDENTIFY_DISKS_H__
#define __IDENTIFY_DISKS_H__

#include <dirent.h>
#include <json-c/json.h>
#include <stdio.h>

#define MAX_PATH 4096
#define MICROSOFT_NVME_VENDOR_ID 0x1414
#define SYS_CLASS_NVME_PATH "/sys/class/nvme"

#ifdef UNIT_TESTING_SYS_CLASS_NVME
extern char *fake_sys_class_nvme_path;
#undef SYS_CLASS_NVME_PATH
#define SYS_CLASS_NVME_PATH fake_sys_class_nvme_path
#endif

struct nvme_controller
{
    char name[256];
    char dev_path[MAX_PATH];
    char sys_path[MAX_PATH];
    char model[MAX_PATH];
};

struct context
{
    enum
    {
        PLAIN,
        JSON
    } output_format;
};

void trim_trailing_whitespace(char *str);
int is_microsoft_nvme_device(const char *device_name);
int is_nvme_namespace(const struct dirent *entry);
void enumerate_namespaces_for_controller(struct nvme_controller *ctrl, struct context *ctx,
                                         json_object *namespaces_array);
int is_azure_nvme_controller(const struct dirent *entry);
int identify_disks(struct context *ctx);

#endif // __IDENTIFY_DISKS_H__
