/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <errno.h>
#include <fcntl.h>
#include <linux/nvme_ioctl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "checked.h"
#include "debug.h"
#include "exit_code.h"
#include "nvme.h"

/**
 * Query the kernel for a namespace device's namespace ID.
 *
 * Exits with:
 * - EXIT_CODE_NVME_DEVICE_OPEN when opening the device fails.
 * - EXIT_CODE_NVME_NAMESPACE_ID_IOCTL when the namespace ID ioctl fails.
 *
 * @return Namespace ID.
 */
int get_nsid_from_namespace_device_path(const char *namespace_path)
{
    int fd = open(namespace_path, O_RDONLY);
    if (fd < 0)
    {
        fprintf(stderr, "failed to open %s: %m\n", namespace_path);
        exit(EXIT_CODE_NVME_DEVICE_OPEN);
    }

    int nsid = ioctl(fd, NVME_IOCTL_ID);
    if (nsid < 0)
    {
        fprintf(stderr, "failed NVME_IOCTL_ID ioctl for %s: %m\n", namespace_path);
        close(fd);
        exit(EXIT_CODE_NVME_NAMESPACE_ID_IOCTL);
    }

    close(fd);
    return nsid;
}

/**
 * Execute identify namespace command.
 *
 * Exits with:
 * - EXIT_CODE_NVME_DEVICE_OPEN when opening the device fails.
 * - EXIT_CODE_NVME_PAGE_SIZE when the page-size lookup fails.
 * - EXIT_CODE_NO_MEMORY when allocating the namespace buffer fails.
 * - EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL when the Identify Namespace ioctl fails.
 * - EXIT_CODE_NVME_IDENTIFY_NAMESPACE_STATUS when Identify Namespace returns a nonzero NVMe status.
 *
 * @param device_path Path to the NVMe device, either controller or namespace.
 * @param nsid Namespace ID to identify.
 *
 * @return Pointer to the namespace structure.
 *
 */
struct nvme_id_ns *nvme_identify_namespace(const char *device_path, int nsid)
{
    int fd = open(device_path, O_RDONLY);
    if (fd < 0)
    {
        fprintf(stderr, "failed to open %s: %m\n", device_path);
        exit(EXIT_CODE_NVME_DEVICE_OPEN);
    }

    long pagesize = sysconf(_SC_PAGESIZE);
    if (pagesize < 0)
    {
        fprintf(stderr, "failed sysconf: %m\n");
        close(fd);
        exit(EXIT_CODE_NVME_PAGE_SIZE);
    }

    struct nvme_id_ns *ns = NULL;
    int error = posix_memalign((void **)&ns, pagesize, sizeof(struct nvme_id_ns));
    if (error != 0)
    {
        fprintf(stderr, "failed posix_memalign for %s: %s\n", device_path, strerror(error));
        exit(EXIT_CODE_NO_MEMORY);
    }

    struct nvme_admin_cmd cmd = {
        .opcode = 0x06, // Identify namespace command
        .nsid = nsid,
        .addr = (unsigned long)ns,
        .data_len = sizeof(*ns),
    };

    int status = ioctl(fd, NVME_IOCTL_ADMIN_CMD, &cmd);
    if (status != 0)
    {
        if (status < 0)
        {
            fprintf(stderr, "failed NVME_IOCTL_ADMIN_CMD ioctl for %s: %m\n", device_path);
        }
        else
        {
            fprintf(stderr, "failed NVME_IOCTL_ADMIN_CMD ioctl for %s: NVMe status %#x\n", device_path, status);
        }

        free(ns);
        close(fd);
        exit(status > 0 ? EXIT_CODE_NVME_IDENTIFY_NAMESPACE_STATUS : EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL);
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
 * Exits with:
 * - EXIT_CODE_NVME_DEVICE_OPEN when opening the device fails.
 * - EXIT_CODE_NVME_PAGE_SIZE when the page-size lookup fails.
 * - EXIT_CODE_NO_MEMORY when allocating the namespace buffer or vendor-specific string fails.
 * - EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL when the Identify Namespace ioctl fails.
 * - EXIT_CODE_NVME_IDENTIFY_NAMESPACE_STATUS when Identify Namespace returns a nonzero NVMe status.
 *
 * @param device_path Path to the NVMe device, either controller or namespace.
 * @param nsid Namespace ID to identify.
 *
 * @return Vendor specific data string.
 */
char *nvme_identify_namespace_vs(const char *device_path, int nsid)
{
    DEBUG_PRINTF("identifying namespace id=%d for device=%s...\n", nsid, device_path);
    struct nvme_id_ns *ns = nvme_identify_namespace(device_path, nsid);
    char *vs = strndup_checked((const char *)ns->vs, sizeof(ns->vs));
    free(ns);

    return vs;
}

/**
 * Query the NVMe namespace for the vendor specific data.
 *
 * This a helper for nvme_identify_namespace_vs that takes a namespace device
 * path and queries the kernel for its namespace ID.
 *
 * Exits with:
 * - EXIT_CODE_NVME_DEVICE_OPEN when opening the device fails.
 * - EXIT_CODE_NVME_NAMESPACE_ID_IOCTL when the namespace ID ioctl fails.
 * - EXIT_CODE_NVME_PAGE_SIZE when the page-size lookup fails.
 * - EXIT_CODE_NO_MEMORY when allocating the namespace buffer or vendor-specific string fails.
 * - EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL when the Identify Namespace ioctl fails.
 * - EXIT_CODE_NVME_IDENTIFY_NAMESPACE_STATUS when Identify Namespace returns a nonzero NVMe status.
 *
 * @param namespace_path Path to the NVMe namespace device.
 *
 * @return Vendor specific data string.
 */
char *nvme_identify_namespace_vs_for_namespace_device(const char *namespace_path)
{
    int nsid = get_nsid_from_namespace_device_path(namespace_path);
    return nvme_identify_namespace_vs(namespace_path, nsid);
}
