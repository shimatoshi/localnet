cmake_minimum_required(VERSION 3.10)
project(python_launcher)

add_library(python_launcher SHARED python_launcher.c)

# libpython3.13.soへのリンク
find_library(python-lib python3.13)
target_link_libraries(python_launcher ${python-lib})
