/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/nvme_ioctl.h>

#include "nvme.h"

/**
 * Execute identify namespace command.
 *
 * @param device_path Path to the NVMe device, either controller or namespace.
 * @param nsid Namespace ID to identify.
 *
 * @return Pointer to the namespace structure or NULL on failure.
 *
 */
struct nvme_id_ns *nvme_identify_namespace(const char *device_path, int nsid)
{
    int fd = open(device_path, O_RDONLY);
    if (fd < 0)
    {
        fprintf(stderr, "failed to open %s: %m\n", device_path);
        return NULL;
    }

    struct nvme_id_ns *ns = NULL;
    if (posix_memalign((void **)&ns, sysconf(_SC_PAGESIZE), sizeof(struct nvme_id_ns)) != 0)
    {
        fprintf(stderr, "failed posix_memalign for %s: %m\n", device_path);
        close(fd);
        return NULL;
    }

    struct nvme_admin_cmd cmd = {
        .opcode = 0x06, // Identify namespace command
        .nsid = nsid,
        .addr = (unsigned long)ns,
        .data_len = sizeof(ns),
    };

    if (ioctl(fd, NVME_IOCTL_ADMIN_CMD, &cmd) < 0)
    {
        fprintf(stderr, "failed NVME_IOCTL_ADMIN_CMD ioctl for %s: %m\n", device_path);
        free(ns);
        close(fd);
        return NULL;
    }

    close(fd);
    return ns;
}
