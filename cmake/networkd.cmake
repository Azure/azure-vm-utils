set(NETWORKD_CONFIGS_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/lib/systemd/network" CACHE PATH "networkd configs installation directory")

install(FILES ${CMAKE_SOURCE_DIR}/networkd/10-azure-unmanaged-sriov.network DESTINATION ${NETWORKD_CONFIGS_INSTALL_DIR})
