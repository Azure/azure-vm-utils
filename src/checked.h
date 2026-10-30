/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __CHECKED_H__
#define __CHECKED_H__

#include <errno.h>
#include <json-c/json.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Checked allocation helpers terminate the process on failure. */
static inline void json_object_array_add_checked(json_object *array, json_object *value)
{
    if (json_object_array_add(array, value) != 0)
    {
        fprintf(stderr, "json_object_array_add() failed: %m\n");
        exit(ENOMEM);
    }
}

static inline json_object *json_object_new_array_checked(void)
{
    json_object *array = json_object_new_array();
    if (array == NULL)
    {
        fprintf(stderr, "json_object_new_array() failed: %m\n");
        exit(ENOMEM);
    }
    return array;
}

static inline json_object *json_object_new_int_checked(int value)
{
    json_object *property = json_object_new_int(value);
    if (property == NULL)
    {
        fprintf(stderr, "json_object_new_int() failed: %m\n");
        exit(ENOMEM);
    }
    return property;
}

static inline json_object *json_object_new_object_checked(void)
{
    json_object *object = json_object_new_object();
    if (object == NULL)
    {
        fprintf(stderr, "json_object_new_object() failed: %m\n");
        exit(ENOMEM);
    }
    return object;
}

static inline json_object *json_object_new_string_checked(const char *value)
{
    json_object *property = json_object_new_string(value);
    if (property == NULL)
    {
        fprintf(stderr, "json_object_new_string() failed: %m\n");
        exit(ENOMEM);
    }
    return property;
}

static inline void json_object_object_add_checked(json_object *object, const char *key, json_object *value)
{
    if (json_object_object_add(object, key, value) != 0)
    {
        fprintf(stderr, "json_object_object_add() failed for %s: %m\n", key);
        exit(ENOMEM);
    }
}

static inline const char *json_object_to_json_string_ext_checked(json_object *object, int flags)
{
    const char *json = json_object_to_json_string_ext(object, flags);
    if (json == NULL)
    {
        fprintf(stderr, "json_object_to_json_string_ext() failed: %m\n");
        exit(ENOMEM);
    }
    return json;
}

static inline char *strdup_checked(const char *value)
{
    char *copy = strdup(value);
    if (copy == NULL)
    {
        fprintf(stderr, "strdup() failed: %m\n");
        exit(ENOMEM);
    }
    return copy;
}

static inline char *strndup_checked(const char *value, size_t length)
{
    char *copy = strndup(value, length);
    if (copy == NULL)
    {
        fprintf(stderr, "strndup() failed: %m\n");
        exit(ENOMEM);
    }
    return copy;
}

#endif // __CHECKED_H__
