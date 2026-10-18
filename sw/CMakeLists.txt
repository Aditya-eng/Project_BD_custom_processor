cmake_minimum_required(VERSION 3.16)
project(bd_host CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
# -ffp-contract=off: no fused multiply-add, so results match the Python reference exactly.
add_compile_options(-Wall -Wextra -Wpedantic -Werror -ffp-contract=off)

add_library(bdhost src/loops.cpp src/records.cpp)
target_include_directories(bdhost PUBLIC include)

add_executable(bd_loopcheck tools/bd_loopcheck.cpp)
target_link_libraries(bd_loopcheck bdhost)

add_executable(bd_selftest tests/selftest.cpp)
target_link_libraries(bd_selftest bdhost)

enable_testing()
add_test(NAME selftest COMMAND bd_selftest)
