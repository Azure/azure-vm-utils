function(generate_manpage manpage_name)
    set(manpage_in "${CMAKE_SOURCE_DIR}/doc/${manpage_name}.8.in")
    set(manpage_output "${CMAKE_CURRENT_BINARY_DIR}/doc/${manpage_name}.8")

    configure_file(
        "${manpage_in}"
        "${manpage_output}"
        @ONLY
    )

    set(MANPAGES_OUTPUT ${MANPAGES_OUTPUT} ${manpage_output} PARENT_SCOPE)
endfunction()

string(TIMESTAMP TODAY "%B %d, %Y")
set(PANDOC_GENERATE_COMMAND
    pandoc --standalone --from markdown --to man
    --template "${CMAKE_SOURCE_DIR}/doc/pandoc.template"
    --variable footer="${manpage_name} ${VERSION}"
    --variable date="${TODAY}"
)
set(PANDOC_FIXUPS_COMMAND sed -i -e 's/f\\[C]/f[CR]/g' -e 's/f\\[V]/f[CB]/g')

add_custom_target(
    generate-manpages
    COMMAND ${PANDOC_GENERATE_COMMAND} "${CMAKE_SOURCE_DIR}/doc/azure-ephemeral-disk-setup.md" -o "${CMAKE_SOURCE_DIR}/doc/azure-ephemeral-disk-setup.8.in"
    COMMAND ${PANDOC_FIXUPS_COMMAND} "${CMAKE_SOURCE_DIR}/doc/azure-ephemeral-disk-setup.8.in"
    COMMAND ${PANDOC_GENERATE_COMMAND} "${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md" -o "${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.8.in"
    COMMAND ${PANDOC_FIXUPS_COMMAND} "${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.8.in"
    COMMAND ${PANDOC_GENERATE_COMMAND} "${CMAKE_SOURCE_DIR}/doc/azure-vm-utils-selftest.md" -o "${CMAKE_SOURCE_DIR}/doc/azure-vm-utils-selftest.8.in"
    COMMAND ${PANDOC_FIXUPS_COMMAND} "${CMAKE_SOURCE_DIR}/doc/azure-vm-utils-selftest.8.in"
)

generate_manpage("azure-ephemeral-disk-setup")
generate_manpage("azure-nvme-id")
generate_manpage("azure-vm-utils-selftest")

add_custom_target(
    doc
    DEPENDS ${MANPAGES_OUTPUT}
)

set(MANPAGES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/share/man")
install(FILES ${MANPAGES_OUTPUT} DESTINATION ${MANPAGES_INSTALL_DIR}/man8)
