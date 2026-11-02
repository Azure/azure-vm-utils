/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "exit_code.h"
#include "nvme.h"

/**
 * Print a udev key-value pair for environment variable.
 */
void print_udev_key_value(const char *key, const char *value)
{
    printf("AZURE_DISK_");
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
 *     AZURE_DISK_TYPE=local
 *     AZURE_DISK_INDEX=2
 *     AZURE_DISK_NAME=nvme-600G-2
 */
int print_udev_key_values_for_vs(char *vs)
{
    char *vs_copy = strdup(vs);
    if (vs_copy == NULL)
    {
        fprintf(stderr, "strdup() failed: %m\n");
        return EXIT_CODE_NO_MEMORY;
    }

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
            return EXIT_CODE_UDEV_INVALID_PROPERTIES;
        }

        print_udev_key_value(key, value);
        pair = strtok_r(NULL, ",", &outer_saveptr);
    }

    free(vs_copy);
    return EXIT_CODE_SUCCESS;
}

/**
 * Execute udev mode, printing out environment variables for import.
 *
 * The udev rules will trigger for Azure NVMe controllers, so no additional
 * checks are needed.  The device path will be in DEVNAME environment variable.
 *
 * Environment variables printed include:
 * - AZURE_DISK_VS: <vendor specific data>
 * - AZURE_DISK_TYPE: <type, if specified>
 * - AZURE_DISK_INDEX: <index for data disk, if specified>
 * - AZURE_DISK_NAME: <name for disk, if specified>
 *
 * @return 0 on success, non-zero on error.
 */
int identify_udev_device(void)
{
    const char *dev_name = getenv("DEVNAME");
    if (dev_name == NULL)
    {
        fprintf(stderr, "environment variable 'DEVNAME' not set\n");
        return EXIT_CODE_UDEV_MISSING_DEVNAME;
    }

    char *vs = nvme_identify_namespace_vs_for_namespace_device(dev_name);
    printf("AZURE_DISK_VS=%s\n", vs);
    int result = print_udev_key_values_for_vs(vs);
    free(vs);

    return result;
}
