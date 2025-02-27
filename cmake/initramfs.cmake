find_program(INITRAMFS_TOOLS update-initramfs)
find_program(DRACUT dracut)
if(INITRAMFS_TOOLS AND INITRAMFS_HOOKS_INSTALL_DIR)
    message(STATUS "initramfs-tools found, installing initramfs hooks")
    install(FILES ${CMAKE_SOURCE_DIR}/initramfs/initramfs-tools/hooks/azure-disk ${CMAKE_SOURCE_DIR}/initramfs/initramfs-tools/hooks/azure-unmanaged-sriov
        DESTINATION ${INITRAMFS_HOOKS_INSTALL_DIR}
        PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ OWNER_EXECUTE GROUP_EXECUTE WORLD_EXECUTE)
elseif(DRACUT AND DRACUT_MODULES_INSTALL_DIR)
    message(STATUS "dracut found, installing dracut modules")
    install(FILES ${CMAKE_SOURCE_DIR}/initramfs/dracut/modules.d/97azure-disk/module-setup.sh
        DESTINATION ${DRACUT_MODULES_INSTALL_DIR}/97azure-disk
        PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ OWNER_EXECUTE GROUP_EXECUTE WORLD_EXECUTE)
    install(FILES ${CMAKE_SOURCE_DIR}/initramfs/dracut/modules.d/97azure-unmanaged-sriov/module-setup.sh
        DESTINATION ${DRACUT_MODULES_INSTALL_DIR}/97azure-unmanaged-sriov
        PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ OWNER_EXECUTE GROUP_EXECUTE WORLD_EXECUTE)
else()
    message(STATUS "initramfs-tools and dracut not found, skipping installation of azure-disk hook")
endif()
