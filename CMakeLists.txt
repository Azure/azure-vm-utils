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

option(AZURE_LUN_CALCULATION_BY_NSID_ENABLED "Enable fallback \"LUN\" calculation via NSID" ON)
if(AZURE_LUN_CALCULATION_BY_NSID_ENABLED)
    set(AZURE_LUN_CALCULATION_BY_NSID_ENABLED 1)
else()
    set(AZURE_LUN_CALCULATION_BY_NSID_ENABLED 0)
endif()

configure_file(
  "${PROJECT_SOURCE_DIR}/udev/80-azure-nvme.rules.in"
  "${PROJECT_BINARY_DIR}/udev/80-azure-nvme.rules"
  @ONLY
)

configure_file(
    "${CMAKE_SOURCE_DIR}/src/version.h.in"
    "${CMAKE_SOURCE_DIR}/src/version.h"
    @ONLY
)

install(TARGETS azure-nvme-id DESTINATION ${AZURE_NVME_ID_INSTALL_DIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/udev/80-azure-nvme.rules DESTINATION ${UDEV_RULES_INSTALL_DIR})

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)
