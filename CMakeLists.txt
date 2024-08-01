cmake_minimum_required(VERSION 3.0.0)
project(azure-nvme-utils VERSION 0.1.0 LANGUAGES C)

if(NOT DEFINED VERSION)
    execute_process(
        COMMAND git describe --tags --always --dirty
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        OUTPUT_VARIABLE VERSION
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
endif()

include(cmake/cppcheck.cmake)
include(cmake/clangformat.cmake)
include(cmake/doc.cmake)

include(CTest)
enable_testing()

add_compile_options(-Wextra -Wall $<$<CONFIG:Debug>:-Werror> -std=gnu11 -D_GNU_SOURCE=1)
add_executable(azure-nvme-id src/main.c)

set(AZURE_NVME_ID_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/sbin")
set(UDEV_RULES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/lib/udev/rules.d" CACHE PATH "udev rules.d installation directory")

configure_file(
    "${CMAKE_SOURCE_DIR}/src/version.h.in"
    "${CMAKE_SOURCE_DIR}/src/version.h"
    @ONLY
)

install(TARGETS azure-nvme-id DESTINATION ${AZURE_NVME_ID_INSTALL_DIR})

# Install udev rules after updating "/usr/sbin/azure-nvme-id" with installed path $AZURE_NVME_ID_INSTALL_DIR.
file(READ ${CMAKE_SOURCE_DIR}/udev/80-azure-disk.rules CONTENT)
string(REPLACE "/usr/sbin/azure-nvme-id" "${AZURE_NVME_ID_INSTALL_DIR}/azure-nvme-id" CONTENT "${CONTENT}")
file(WRITE ${CMAKE_BINARY_DIR}/udev/80-azure-disk.rules ${CONTENT})
install(FILES ${CMAKE_BINARY_DIR}/udev/80-azure-disk.rules DESTINATION ${UDEV_RULES_INSTALL_DIR})

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)
