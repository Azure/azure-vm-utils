find_program(PANDOC_EXECUTABLE pandoc)

string(TIMESTAMP TODAY "%B %d, %Y")

if(PANDOC_EXECUTABLE)
        add_custom_command(
                OUTPUT ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.1
                COMMAND ${PANDOC_EXECUTABLE}
                        ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md
                        --standalone --from markdown --to man
                        --variable footer="azure-nvme-id ${VERSION}"
                        --variable date="${TODAY}"
                        -o ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.1
                DEPENDS ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md
                COMMENT "Generating manpage for azure-nvme-id"
        )
else()
        message(WARNING "Pandoc not found, will not generate manpages")
endif()

add_custom_target(
        doc ALL
        DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/doc/azure-nvme-id.1
)
