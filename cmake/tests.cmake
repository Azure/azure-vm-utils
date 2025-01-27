find_package(PkgConfig REQUIRED)
pkg_check_modules(CMOCKA REQUIRED cmocka)

function(add_test_executable test_name)
    set(multiValueArgs WRAPPED_FUNCTIONS SOURCES CFLAGS)
    cmake_parse_arguments(TEST "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    add_executable(${test_name} ${TEST_SOURCES} tests/capture.c)
    add_test(NAME ${test_name} COMMAND ${test_name})

    # LTO may be enabled by packaging, but it must be disabled for --wrap to work.
    target_compile_options(${test_name} PRIVATE -g -O0 -fno-lto ${CMOCKA_CFLAGS_OTHER} ${TEST_CFLAGS})
    target_link_options(${test_name} PRIVATE -flto=n)

    target_include_directories(${test_name} PRIVATE ${CMOCKA_INCLUDE_DIRS} src tests)
    target_link_directories(${test_name} PRIVATE ${CMOCKA_LIBRARY_DIRS})
    target_link_libraries(${test_name} PRIVATE ${CMOCKA_LIBRARIES} dl)

    if(TEST_WRAPPED_FUNCTIONS)
        foreach(func ${TEST_WRAPPED_FUNCTIONS})
            target_link_options(${test_name} PRIVATE -Wl,--wrap=${func})
        endforeach()
    endif()
endfunction()

add_test_executable(debug_tests
    WRAPPED_FUNCTIONS
    SOURCES src/debug.c tests/debug_tests.c
)

add_test_executable(identify_disks_tests
    WRAPPED_FUNCTIONS nvme_identify_namespace_vs_for_namespace_device
    SOURCES src/debug.c src/identify_disks.c src/nvme.c tests/identify_disks_tests.c
    CFLAGS -DUNIT_TESTING_SYS_CLASS_NVME=1
)

add_test_executable(identify_udev_tests
    WRAPPED_FUNCTIONS nvme_identify_namespace_vs_for_namespace_device
    SOURCES src/debug.c src/identify_udev.c src/nvme.c tests/identify_udev_tests.c
)

add_test_executable(nvme_tests
    WRAPPED_FUNCTIONS open posix_memalign ioctl close
    SOURCES src/nvme.c tests/nvme_tests.c
)
