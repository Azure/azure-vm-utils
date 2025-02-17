string(TIMESTAMP TODAY "%B %d, %Y")

option(GENERATE_MANPAGES "Generate manpages with pandoc" OFF)

function(generate_manpage manpage_name)
    set(manpage_md "${CMAKE_SOURCE_DIR}/doc/${manpage_name}.md")
    set(manpage_output "${CMAKE_CURRENT_BINARY_DIR}/doc/${manpage_name}.8")

    if(GENERATE_MANPAGES)
        find_program(PANDOC_EXECUTABLE pandoc)
        if(NOT PANDOC_EXECUTABLE)
            message(WARNING "Pandoc not found, will not generate manpages")
            return()
        endif()

        add_custom_command(
            OUTPUT ${manpage_output}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/doc
            COMMAND ${PANDOC_EXECUTABLE}
                ${manpage_md}
                --standalone --from markdown --to man
                --variable footer="${manpage_name} ${VERSION}"
                --variable date="${TODAY}"
                -o ${manpage_output}
            DEPENDS ${manpage_md}
            COMMENT "Generating manpage for ${manpage_name}"
        )
    else()
        configure_file(
            "${CMAKE_SOURCE_DIR}/doc/${manpage_name}.8.in"
            "${manpage_output}"
            @ONLY
        )
    endif()

    set(MANPAGES_OUTPUT ${MANPAGES_OUTPUT} ${manpage_output} PARENT_SCOPE)
endfunction()

generate_manpage("azure-nvme-id")
generate_manpage("azure-vm-utils-selftest")

add_custom_target(
    doc ALL
    DEPENDS ${MANPAGES_OUTPUT}
)

set(MANPAGES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/share/man")
install(FILES ${MANPAGES_OUTPUT} DESTINATION ${MANPAGES_INSTALL_DIR}/man8)
