/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

// clange-format off
#include <cmocka.h>
// clange-format on

#include "capture.h"

static int stdout_fd = -1;
static int stderr_fd = -1;
static int stdout_pipe[2] = {-1, -1};
static int stderr_pipe[2] = {-1, -1};

#define BUFFER_SIZE 128 * 1024
char capture_stdout_buffer[BUFFER_SIZE];
char capture_stderr_buffer[BUFFER_SIZE];

/**
 * Bypass potentially mocked close using dlsym().
 */
static int (*real_close)(int) = NULL;
static int capture_close(int fd)
{
    if (!real_close)
    {
        real_close = (int (*)(int))dlsym(RTLD_NEXT, "close");
    }

    return real_close(fd);
}

/**
 * Capture stdout and stderr using non-blocking pipes.
 */
void capture_setup(void **state)
{
    (void)state; // Unused parameter

    memset(capture_stdout_buffer, 0, BUFFER_SIZE);
    memset(capture_stderr_buffer, 0, BUFFER_SIZE);

    if (pipe(stdout_pipe) == -1 || pipe(stderr_pipe) == -1)
    {
        perror("pipe failed");
        exit(EXIT_FAILURE);
    }

    stdout_fd = dup(STDOUT_FILENO);
    stderr_fd = dup(STDERR_FILENO);

    if (stdout_fd == -1 || stderr_fd == -1)
    {
        perror("dup failed");
        exit(EXIT_FAILURE);
    }

    if (dup2(stdout_pipe[1], STDOUT_FILENO) == -1 || dup2(stderr_pipe[1], STDERR_FILENO) == -1)
    {
        perror("dup2 failed");
        exit(EXIT_FAILURE);
    }

    capture_close(stdout_pipe[1]);
    capture_close(stderr_pipe[1]);

    // Set pipes to non-blocking mode
    fcntl(stdout_pipe[0], F_SETFL, O_NONBLOCK);
    fcntl(stderr_pipe[0], F_SETFL, O_NONBLOCK);
}

/**
 * Synchronize captured stdout and return buffer.
 */
const char *capture_stdout()
{
    if (stdout_pipe[0] != -1)
    {
        fflush(stdout);

        // Read data from stdout pipe
        ssize_t bytes_read;
        size_t offset = strlen(capture_stdout_buffer);
        while ((bytes_read = read(stdout_pipe[0], capture_stdout_buffer + offset, BUFFER_SIZE - 1 - offset)) > 0)
        {
            offset += bytes_read;
            if (offset >= BUFFER_SIZE - 1)
            {
                break;
            }
        }
        capture_stdout_buffer[offset] = '\0';
    }

    return capture_stdout_buffer;
}

/**
 * Synchronize captured stderr and return buffer.
 */
const char *capture_stderr()
{
    if (stderr_pipe[0] != -1)
    {
        fflush(stderr);

        ssize_t bytes_read;
        size_t offset = strlen(capture_stderr_buffer);
        while ((bytes_read = read(stderr_pipe[0], capture_stderr_buffer + offset, BUFFER_SIZE - 1 - offset)) > 0)
        {
            offset += bytes_read;
            if (offset >= BUFFER_SIZE - 1)
            {
                break;
            }
        }
        capture_stderr_buffer[offset] = '\0';
    }
    return capture_stderr_buffer;
}

/**
 * Restore stdout and stderr after syncing final time.
 */
void capture_teardown(void **state)
{
    (void)state; // Unused parameter

    if (stdout_fd != -1)
    {
        dup2(stdout_fd, STDOUT_FILENO);
        capture_close(stdout_fd);
        stdout_fd = -1;
    }

    if (stderr_fd != -1)
    {
        dup2(stderr_fd, STDERR_FILENO);
        capture_close(stderr_fd);
        stderr_fd = -1;
    }

    if (stdout_pipe[0] != -1)
    {
        capture_stdout();
        capture_close(stdout_pipe[0]);
        stdout_pipe[0] = -1;
    }

    if (stderr_pipe[0] != -1)
    {
        capture_stderr();
        capture_close(stderr_pipe[0]);
        stderr_pipe[0] = -1;
    }

    fprintf(stderr, ">> TEST STDOUT: %s\n", capture_stdout_buffer);
    fprintf(stderr, ">> TEST STDERR: %s\n", capture_stderr_buffer);
}
