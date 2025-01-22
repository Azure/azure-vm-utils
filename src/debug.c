/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

#include "debug.h"

bool debug = false;
extern char **environ;

/**
 * Dump environment variables.
 */
void debug_environment_variables()
{
    int i = 0;

    DEBUG_PRINTF("Environment Variables:\n");
    while (environ[i])
    {
        DEBUG_PRINTF("%s\n", environ[i]);
        i++;
    }
}
