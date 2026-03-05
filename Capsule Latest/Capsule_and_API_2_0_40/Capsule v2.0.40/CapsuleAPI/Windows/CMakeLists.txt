cmake_minimum_required(VERSION 3.13)

project(CapsuleClientExample)

find_library(CAPSULE_CLIENT_LIB CapsuleClient PATHS "${CMAKE_CURRENT_SOURCE_DIR}/Lib")

set(CCESources
    Source/main.cpp
)

set(SignalExampleSources
    Source/SignalExample.cpp
)

set(CCEHeaders
    Include/CCapsuleAPI.h
)

add_executable(CapsuleClientExample ${CCESources} ${CCEHeaders})
target_include_directories(CapsuleClientExample
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/Include
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/Include/Core)

add_executable(CapsuleSignalExample ${SignalExampleSources} ${CCEHeaders})
target_include_directories(CapsuleSignalExample
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/Include
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/Include/Core)

set_target_properties(CapsuleClientExample CapsuleSignalExample PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/build
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON)

if (APPLE)
    set_target_properties(CapsuleClientExample CapsuleSignalExample PROPERTIES
        BUILD_WITH_INSTALL_RPATH TRUE
        INSTALL_RPATH "@executable_path/")
endif()

target_link_libraries(CapsuleClientExample ${CAPSULE_CLIENT_LIB})
target_link_libraries(CapsuleSignalExample ${CAPSULE_CLIENT_LIB})
