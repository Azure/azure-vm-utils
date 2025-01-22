/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 *
 * Basic mocks for system calls (open, posix_memalign, ioctl, close, etc.) to be used in tests.
 * Tests can control the mock function pointers (e.g. mock_open_ptr) while defines
 * are in effect to redirect system calls to the mock functions without requiring changes
 * to the code under test.
 *
 * This mock module aims to be generic, so by default these mocks call the real syscall unless
 * reconfigured by a test as needed.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

int (*mock_open_ptr)(const char *, int, ...) = open;
int (*mock_posix_memalign_ptr)(void **, size_t, size_t) = posix_memalign;
int (*mock_ioctl_ptr)(int, unsigned long, ...) = ioctl;
int (*mock_close_ptr)(int) = close;

/**
 * Reset all mock function pointers to the real system calls.
 */
void mock_syscalls_reset() {
    mock_open_ptr = open;
    mock_posix_memalign_ptr = posix_memalign;
    mock_ioctl_ptr = ioctl;
    mock_close_ptr = close;
}

int mock_open(const char *pathname, int flags, ...) {
    if (mock_open_ptr == NULL) {
        fprintf(stderr, "Error: mock_open_ptr is not set\n");
        return -1;
    }

    va_list args;
    va_start(args, flags);

    // If O_CREAT is specified, retrieve and pass the mode argument.
    if (flags & O_CREAT) {
        mode_t mode = va_arg(args, mode_t);
        va_end(args);
        return mock_open_ptr(pathname, flags, mode);
    } else {
        va_end(args);
        return mock_open_ptr(pathname, flags);
    }
}


int mock_posix_memalign(void **memptr, size_t alignment, size_t size) {
    return mock_posix_memalign_ptr(memptr, alignment, size);
}

int mock_ioctl(int fd, unsigned long request, ...) {
    if (mock_ioctl_ptr == NULL) {
        fprintf(stderr, "Error: mock_ioctl_ptr is not set\n");
        return -1;
    }

    va_list args;
    va_start(args, request);

    // Always pass the third argument (variadic).
    void *arg = va_arg(args, void *);
    va_end(args);

    return mock_ioctl_ptr(fd, request, arg);
}

int mock_close(int fd) {
    return mock_close_ptr(fd);
}
