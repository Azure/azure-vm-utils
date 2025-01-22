/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

#ifndef __MOCKS_H__
#define __MOCKS_H__

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

extern int (*mock_open_ptr)(const char *, int, ...);
extern int (*mock_posix_memalign_ptr)(void **, size_t, size_t);
extern int (*mock_ioctl_ptr)(int, unsigned long, ...);
extern int (*mock_close_ptr)(int);

int mock_open(const char *pathname, int flags, ...);
int mock_posix_memalign(void **memptr, size_t alignment, size_t size);
int mock_ioctl(int fd, unsigned long request, ...);
int mock_close(int fd);
void mock_syscalls_reset();

#define open mock_open
#define posix_memalign mock_posix_memalign
#define ioctl mock_ioctl
#define close mock_close

#endif // __MOCKS_H__
