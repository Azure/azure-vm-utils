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
set(DRACUT_MODULES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/lib/dracut/modules.d/97azure-disk" CACHE PATH "dracut modules installation directory")
set(INITRAMFS_HOOKS_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/share/initramfs-tools/hooks" CACHE PATH "initramfs-tools hooks installation directory")
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

find_program(INITRAMFS_TOOLS update-initramfs)
find_program(DRACUT dracut)
if(INITRAMFS_TOOLS AND INITRAMFS_HOOKS_INSTALL_DIR)
    message(STATUS "initramfs-tools found, installing initramfs hook")
    set(HOOK_SCRIPT ${CMAKE_SOURCE_DIR}/initramfs/initramfs-tools/hooks/azure-disk)
    install(FILES ${HOOK_SCRIPT}
        DESTINATION ${INITRAMFS_HOOKS_INSTALL_DIR}
        PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ OWNER_EXECUTE GROUP_EXECUTE WORLD_EXECUTE)
elseif(DRACUT AND DRACUT_MODULES_INSTALL_DIR)
    message(STATUS "dracut found, installing dracut module")
    install(FILES ${CMAKE_SOURCE_DIR}/initramfs/dracut/modules.d/97azure-disk/module-setup.sh
        DESTINATION ${DRACUT_MODULES_INSTALL_DIR}
        PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ OWNER_EXECUTE GROUP_EXECUTE WORLD_EXECUTE)
else()
    message(STATUS "initramfs-tools and dracut not found, skipping installation of azure-disk hook")
endif()

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)
