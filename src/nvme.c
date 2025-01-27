/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <fcntl.h>
#include <linux/nvme_ioctl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "debug.h"
#include "nvme.h"

/**
 * Given the path to a namespace device, determine the namespace id.
 *
 * Examples:
 * - /dev/nvme0n5 -> returns 5
 * - /dev/nvme2n12 -> returns 12
 * - /dev/nvme100n1 -> returns 1
 *
 * @return Namespace ID or -1 on failure.
 */
int get_nsid_from_namespace_device_path(const char *namespace_path)
{
    unsigned int ctrl, nsid;

    if (sscanf(namespace_path, "/dev/nvme%un%u", &ctrl, &nsid) != 2)
    {
        return -1;
    }

    return nsid;
}

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
        .data_len = sizeof(*ns),
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

/**
 * Query the NVMe namespace for the vendor specific data.
 *
 * For Azure devices, the vendor-specific data is current exposed as a string.
 * It will include the type of device and various properties in the format:
 * key1=value1,key2=value2,...\0.
 *
 * Anything beyond the terminating null-byte is currently undefined and
 * consequently ignored.
 *
 * @param device_path Path to the NVMe device, either controller or namespace.
 * @param nsid Namespace ID to identify.
 *
 * @return Vendor specific data string or NULL on failure.
 */
char *nvme_identify_namespace_vs(const char *device_path, int nsid)
{
    DEBUG_PRINTF("identifying namespace id=%d for device=%s...\n", nsid, device_path);
    struct nvme_id_ns *ns = nvme_identify_namespace(device_path, nsid);
    if (ns == NULL)
    {
        fprintf(stderr, "failed to identify namespace for device=%s\n", device_path);
        return NULL;
    }

    char *vs = strndup((const char *)ns->vs, sizeof(ns->vs));
    free(ns);

    return vs;
}

/**
 * Query the NVMe namespace for the vendor specific data.
 *
 * This a helper for nvme_identify_namespace_vs that takes a namespace device
 * path and extracts the namespace id from it.
 *
 * @param namespace_path Path to the NVMe namespace device.
 *
 * @return Vendor specific data string or NULL on failure.
 */
char *nvme_identify_namespace_vs_for_namespace_device(const char *namespace_path)
{
    int nsid = get_nsid_from_namespace_device_path(namespace_path);
    if (nsid < 0)
    {
        fprintf(stderr, "failed to parse namespace id: %s\n", namespace_path);
        return NULL;
    }

    return nvme_identify_namespace_vs(namespace_path, nsid);
}
