file(GLOB_RECURSE SHELL_SOURCES *.sh
                        ephemeral-disk-setup/azure-ephemeral-disk-setup
                        )

add_custom_target(shellcheck
    COMMAND shellcheck ${SHELL_SOURCES}
    COMMENT "Running shellcheck on source files"
)
