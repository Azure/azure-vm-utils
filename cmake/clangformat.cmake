file(GLOB_RECURSE ALL_SOURCE_FILES *.c *.h)

add_custom_target(
    clangformat
    COMMAND /usr/bin/clang-format
    -style=Microsoft
    -i
    ${ALL_SOURCE_FILES}
)
