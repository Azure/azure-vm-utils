
find_package(PkgConfig REQUIRED)
pkg_check_modules(CRITERION REQUIRED criterion)

set(TEST_SOURCE_FILES
    src/debug.c
    src/nvme.c
    tests/debug_tests.c
    tests/mock_syscalls.c
    tests/nvme_tests.c
)

add_executable(nvme_tests ${TEST_SOURCE_FILES})
target_include_directories(nvme_tests PRIVATE ${CRITERION_INCLUDE_DIRS} src tests)
target_link_directories(nvme_tests PRIVATE ${CRITERION_LIBRARY_DIRS})
add_definitions(${CRITERION_CFLAGS_OTHER})
target_compile_options(nvme_tests PRIVATE -include mock_syscalls.h)
target_link_libraries(nvme_tests PRIVATE ${CRITERION_LIBRARIES})
add_test(NAME nvme_tests COMMAND nvme_tests)
target_compile_options(nvme_tests PRIVATE -Wno-unused-parameter)
