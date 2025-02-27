# Install Azure unmanaged SR-IOV rules and configuration.
install(FILES ${CMAKE_SOURCE_DIR}/udev/10-azure-unmanaged-sriov.rules DESTINATION ${UDEV_RULES_INSTALL_DIR})

# Install udev rules after updating "/usr/sbin/azure-nvme-id" with installed path $AZURE_NVME_ID_INSTALL_DIR.
file(READ ${CMAKE_SOURCE_DIR}/udev/80-azure-disk.rules CONTENT)
string(REPLACE "/usr/sbin/azure-nvme-id" "${AZURE_NVME_ID_INSTALL_DIR}/azure-nvme-id" CONTENT "${CONTENT}")
file(WRITE ${CMAKE_BINARY_DIR}/udev/80-azure-disk.rules ${CONTENT})
install(FILES ${CMAKE_BINARY_DIR}/udev/80-azure-disk.rules DESTINATION ${UDEV_RULES_INSTALL_DIR})
