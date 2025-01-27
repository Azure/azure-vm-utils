/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __NVME_H__
#define __NVME_H__

#include <linux/types.h>

struct nvme_lbaf
{
    __le16 ms;
    __u8 ds;
    __u8 rp;
};

struct nvme_id_ns
{
    __le64 nsze;
    __le64 ncap;
    __le64 nuse;
    __u8 nsfeat;
    __u8 nlbaf;
    __u8 flbas;
    __u8 mc;
    __u8 dpc;
    __u8 dps;
    __u8 nmic;
    __u8 rescap;
    __u8 fpi;
    __u8 dlfeat;
    __le16 nawun;
    __le16 nawupf;
    __le16 nacwu;
    __le16 nabsn;
    __le16 nabo;
    __le16 nabspf;
    __le16 noiob;
    __u8 nvmcap[16];
    __le16 npwg;
    __le16 npwa;
    __le16 npdg;
    __le16 npda;
    __le16 nows;
    __u8 rsvd74[18];
    __le32 anagrpid;
    __u8 rsvd96[3];
    __u8 nsattr;
    __le16 nvmsetid;
    __le16 endgid;
    __u8 nguid[16];
    __u8 eui64[8];
    struct nvme_lbaf lbaf[16];
    __u8 rsvd192[192];
    __u8 vs[3712];
};

#define NVME_ADMIN_IDENTFY_NAMESPACE_OPCODE 0x06

int nvme_nsid_from_namespace_device_path(const char *namespace_path);
struct nvme_id_ns *nvme_identify_namespace(const char *device_path, int nsid);
char *nvme_identify_namespace_vs(const char *device_path, int nsid);

int get_nsid_from_namespace_device_path(const char *namespace_path);
char *nvme_identify_namespace_vs_for_namespace_device(const char *namespace_path);

#endif // __NVME_H__
