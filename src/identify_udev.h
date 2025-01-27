/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __IDENTIFY_UDEV_H__
#define __IDENTIFY_UDEV_H__

void print_udev_key_value(const char *key, const char *value);
int print_udev_key_values_for_vs(char *vs);
int identify_udev_device(void);

#endif // __IDENTIFY_UDEV_H__
