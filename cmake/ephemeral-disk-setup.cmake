configure_file(
    "${CMAKE_SOURCE_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup"
    "${CMAKE_BINARY_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup"
    @ONLY
)
configure_file(
    "${CMAKE_SOURCE_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup.service"
    "${CMAKE_BINARY_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup.service"
    @ONLY
)

install(FILES ${CMAKE_SOURCE_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup.conf
        DESTINATION ${AZURE_EPHEMERAL_DISK_SETUP_CONF_INSTALL_DIR}
        PERMISSIONS OWNER_WRITE OWNER_READ GROUP_READ WORLD_READ)
install(FILES ${CMAKE_BINARY_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup.service
        DESTINATION ${AZURE_EPHEMERAL_DISK_SETUP_SERVICE_INSTALL_DIR}
        PERMISSIONS OWNER_WRITE OWNER_READ GROUP_READ WORLD_READ)
install(FILES ${CMAKE_BINARY_DIR}/ephemeral-disk-setup/azure-ephemeral-disk-setup
        DESTINATION ${AZURE_EPHEMERAL_DISK_SETUP_INSTALL_DIR}
        PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ GROUP_EXECUTE GROUP_READ WORLD_EXECUTE WORLD_READ)
