/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <string.h>

#include "debug.h"
#include "identify_disks.h"
#include "identify_udev.h"
#include "util.h"
#include "version.h"

int main(int argc, const char **argv)
{
    bool udev_mode = false;

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
            printf("azure-nvme-id %s\n", VERSION);
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
        return identify_udev_device();
    }

    return identify_disks();
}
