file(GLOB_RECURSE ALL_SOURCE_FILES *.c *.h)

add_custom_target(
        cppcheck
        COMMAND /usr/bin/cppcheck
        --enable=all
        --suppress=missingIncludeSystem
        ${ALL_SOURCE_FILES}
)
