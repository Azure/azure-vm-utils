/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#include <stdio.h>
#include <stdlib.h>

#include "debug.h"

/**
 * Read file contents as a null-terminated string.
 *
 * For sysfs entries, etc. where the file contents are not null-terminated and
 * we know the contents are just a simple string (e.g. sysfs attributes).
 */
char *read_file_as_string(const char *path)
{
    DEBUG_PRINTF("reading %s...\n", path);

    FILE *file = fopen(path, "r");
    if (file == NULL)
    {
        fprintf(stderr, "failed to fopen %s: %m\n", path);
        return NULL;
    }

    // Determine the file size
    if (fseek(file, 0, SEEK_END) < 0)
    {
        fprintf(stderr, "failed to fseek on %s: %m\n", path);
        fclose(file);
        return NULL;
    }

    long length = ftell(file);
    if (length < 0)
    {
        fprintf(stderr, "failed to ftell on %s: %m\n", path);
        fclose(file);
        return NULL;
    }

    if (fseek(file, 0, SEEK_SET) < 0)
    {
        fprintf(stderr, "failed to fseek on %s: %m\n", path);
        fclose(file);
        return NULL;
    }

    // Allocate size of file plus one byte for null.
    char *contents = malloc(length + 1);
    if (contents == NULL)
    {
        fprintf(stderr, "failed to malloc for %s: %m\n", path);
        fclose(file);
        return NULL;
    }

    // Read file contents.
    size_t bytes_read = fread(contents, 1, length, file);
    if ((long)bytes_read < length)
    {
        DEBUG_PRINTF("short read on %s, contents probably changed", path);
    }

    fclose(file);

    // Null-terminate the string.
    contents[bytes_read] = '\0';

    DEBUG_PRINTF("%s => %s\n", path, contents);
    return contents;
}
