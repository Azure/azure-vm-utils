find_program(PANDOC_EXECUTABLE pandoc)
if(NOT PANDOC_EXECUTABLE)
        message(WARNING "Pandoc not found, will not generate manpages")
        return()
endif()

string(TIMESTAMP TODAY "%B %d, %Y")

add_custom_command(
	OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.1
	COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/doc
	COMMAND ${PANDOC_EXECUTABLE}
		${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md
		--standalone --from markdown --to man
		--variable footer="azure-nvme-id ${VERSION}"
		--variable date="${TODAY}"
		-o ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.1
	DEPENDS ${CMAKE_SOURCE_DIR}/doc/azure-nvme-id.md
	COMMENT "Generating manpage for azure-nvme-id"
)

add_custom_target(
        doc ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.1
)

set(MANPAGES_INSTALL_DIR "${CMAKE_INSTALL_PREFIX}/share/man")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/doc/azure-nvme-id.1
        DESTINATION ${MANPAGES_INSTALL_DIR}/man1)
