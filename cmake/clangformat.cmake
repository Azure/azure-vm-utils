file(GLOB ALL_SOURCE_FILES src/*.[ch] tests/*.[ch])

add_custom_target(clang-format
    COMMAND clang-format -i ${ALL_SOURCE_FILES}
    COMMENT "Running clang-format on source files"
)

add_custom_target(check-clang-format
    COMMAND clang-format --dry-run --Werror ${ALL_SOURCE_FILES}
    COMMENT "Running clang-format check on source files"
)
