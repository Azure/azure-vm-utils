cmake_minimum_required(VERSION 3.0.0)
project(azure-nvme-utils VERSION 0.1.0 LANGUAGES C)

include(cmake/cppcheck.cmake)
include(cmake/clangformat.cmake)

include(CTest)
enable_testing()

add_compile_options(-Wextra -Wall -Werror -std=gnu11 -D_GNU_SOURCE=1)
add_executable(azure-nvme-id src/main.c)

install(TARGETS azure-nvme-id DESTINATION bin)
install(FILES udev/80-azure-nvme.rules DESTINATION /lib/udev/rules.d)

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)
