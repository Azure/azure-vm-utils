/**
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license
 * information.
 */

#ifndef __CAPTURE_H__
#define __CAPTURE_H__

void capture_setup(void **state);
void capture_teardown(void **state);
const char *capture_stdout();
const char *capture_stderr();

#endif // __CAPTURE_H__
