cmake_minimum_required(VERSION 3.5)
project(azure-vm-utils VERSION 0.1.0 LANGUAGES C)

if(NOT DEFINED VERSION)
    execute_process(
        COMMAND git describe --tags --always --dirty
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        OUTPUT_VARIABLE VERSION
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
endif()

set(AZURE_NVME_ID_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/sbin" CACHE PATH "azure-nvme-id installation directory")
set(DRACUT_MODULES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/lib/dracut/modules.d" CACHE PATH "dracut modules installation directory")
set(INITRAMFS_HOOKS_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/share/initramfs-tools/hooks" CACHE PATH "initramfs-tools hooks installation directory")
set(NETWORKD_CONFIGS_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/lib/systemd/network" CACHE PATH "networkd configs installation directory")
set(UDEV_RULES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/lib/udev/rules.d" CACHE PATH "udev rules installation directory")

include(cmake/cppcheck.cmake)
include(cmake/clangformat.cmake)
include(cmake/doc.cmake)
include(cmake/initramfs.cmake)
include(cmake/networkd.cmake)
include(cmake/python.cmake)
include(cmake/udev.cmake)

include(CTest)
enable_testing()

find_package(PkgConfig REQUIRED)
pkg_check_modules(JSON_C REQUIRED json-c)
include_directories(
    ${CMAKE_SOURCE_DIR}/src
    ${JSON_C_INCLUDE_DIRS}
)

add_compile_options(-Wextra -Wall $<$<CONFIG:Debug>:-Werror> -std=gnu11 -D_GNU_SOURCE=1)
add_executable(azure-nvme-id src/debug.c src/identify_disks.c src/identify_udev.c src/main.c src/nvme.c)
target_link_libraries(azure-nvme-id ${JSON_C_LIBRARIES})

configure_file(
    "${CMAKE_SOURCE_DIR}/src/version.h.in"
    "${CMAKE_SOURCE_DIR}/src/version.h"
    @ONLY
)

install(TARGETS azure-nvme-id DESTINATION ${AZURE_NVME_ID_INSTALL_DIR})
install(FILES ${CMAKE_SOURCE_DIR}/selftest/selftest.py
        DESTINATION ${AZURE_NVME_ID_INSTALL_DIR}
        RENAME azure-vm-utils-selftest
        PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ GROUP_EXECUTE GROUP_READ WORLD_EXECUTE WORLD_READ)

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)

option(ENABLE_TESTS "Enable unit tests" ON)
if(ENABLE_TESTS)
    include(cmake/tests.cmake)
endif()
