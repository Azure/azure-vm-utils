/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

#ifndef __DEBUG_H__
#define __DEBUG_H__

#include <stdbool.h>
#include <stdio.h>

extern bool debug;

#define DEBUG_PRINTF(fmt, ...)                                                                                         \
    do                                                                                                                 \
    {                                                                                                                  \
        if (debug == true)                                                                                             \
        {                                                                                                              \
            fprintf(stderr, "DEBUG: " fmt, ##__VA_ARGS__);                                                             \
        }                                                                                                              \
    } while (0)


void debug_environment_variables();

#endif // __DEBUG_H__
