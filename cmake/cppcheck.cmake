file(GLOB ALL_SOURCE_FILES src/*.[ch] tests/*.[ch])

set(CPPCHECK_COMMAND
    cppcheck
    --enable=all
    --suppress=missingIncludeSystem
    -I${CMAKE_SOURCE_DIR}/src
    ${ALL_SOURCE_FILES}
)

add_custom_target(cppcheck
    COMMAND ${CPPCHECK_COMMAND}
    COMMENT "Running cppcheck on source files"
)
