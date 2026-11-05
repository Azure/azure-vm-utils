/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __EXIT_CODE_H__
#define __EXIT_CODE_H__

enum exit_code
{
    EXIT_CODE_INVALID_ARGUMENT = 1,
    EXIT_CODE_CONTROLLER_SCAN = 2,
    EXIT_CODE_NAMESPACE_SCAN = 3,
    EXIT_CODE_NO_MEMORY = 4,
    EXIT_CODE_NVME_DEVICE_OPEN = 5,
    EXIT_CODE_NVME_IDENTIFY_NAMESPACE_IOCTL = 6,
    EXIT_CODE_NVME_IDENTIFY_NAMESPACE_STATUS = 7,
    EXIT_CODE_NVME_NAMESPACE_ID_IOCTL = 8,
    EXIT_CODE_NVME_PAGE_SIZE = 9,
    EXIT_CODE_SUCCESS = 0,
    EXIT_CODE_UDEV_INVALID_PROPERTIES = 10,
    EXIT_CODE_UDEV_MISSING_DEVNAME = 11,
};

#endif // __EXIT_CODE_H__
