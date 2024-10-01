string(TIMESTAMP TODAY "%B %d, %Y")

option(GENERATE_MANPAGES "Generate manpages with pandoc" OFF)
if(GENERATE_MANPAGES)
    find_program(PANDOC_EXECUTABLE pandoc)
    if(NOT PANDOC_EXECUTABLE)
        message(WARNING "Pandoc not found, will not generate manpages")
        return()
    endif()

    add_custom_command(
        OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.8
        COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/doc
        COMMAND ${PANDOC_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md
            --standalone --from markdown --to man
            --variable footer="azure-nvme-id ${VERSION}"
            --variable date="${TODAY}"
            -o ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.8
        DEPENDS ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md
        COMMENT "Generating manpage for azure-nvme-id"
    )
else()
    configure_file(
        "${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.8.in"
        "${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.8"
        @ONLY
    )
endif()

add_custom_target(
        doc ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.8
)

set(MANPAGES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/share/man")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.8
        DESTINATION ${MANPAGES_INSTALL_DIR}/man8)
