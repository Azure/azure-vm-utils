/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __CAPTURE_H__
#define __CAPTURE_H__

#include <sys/types.h>

pid_t capture_fork(void);
void capture_wait(pid_t child, int expected_status);
int capture_setup(void **state);
int capture_teardown(void **state);
const char *capture_stdout();
const char *capture_stderr();

#endif // __CAPTURE_H__
