import os
from pathlib import Path

from tools.git2_patch import prepare_source


def build_library(env, deps):
    config = {
        "CMAKE_BUILD_TYPE": "RelWithDebInfo" if env["debug_symbols"] else "Release",
        "OPENSSL_USE_STATIC_LIBS": 1,
        "OPENSSL_INCLUDE_DIR": env["SSL_INCLUDE"],
        "OPENSSL_SSL_LIBRARY": env["SSL_LIBRARY"],
        "OPENSSL_CRYPTO_LIBRARY": env["SSL_CRYPTO_LIBRARY"],
        "OPENSSL_ROOT_DIR": env["SSL_INSTALL"],
        "BUILD_TESTS": "OFF",
        "BUILD_CLI": "OFF",
        "BUILD_EXAMPLES": "OFF",
        "BUILD_FUZZERS": "OFF",
        "USE_SSH": "ON",
        "USE_HTTPS": "OpenSSL",
        "USE_SHA1": "CollisionDetection",
        "USE_BUNDLED_ZLIB": "ON",
        "USE_HTTP_PARSER": "builtin",
        "REGEX_BACKEND": "builtin",
        "BUILD_SHARED_LIBS": 0,
        "LINK_WITH_STATIC_LIBRARIES": 1,
        "CMAKE_POLICY_VERSION_MINIMUM": "3.10",
        "LIBSSH2_INCLUDE_DIRS": env.Dir("#thirdparty/ssh2/libssh2/include").abspath,
        "LIBSSH2_RESOLVED": deps[-1].abspath,
        "LIBSSH2_LIBRARIES": "LIBSSH2",
        "LIBSSH2_FOUND": 1,
        "STATIC_CRT": env.get("use_static_cpp", True),
    }

    if env["platform"] != "windows":
        config["CMAKE_C_FLAGS"] = "-fPIC"
    else:
        config["OPENSSL_ROOT_DIR"] = env["SSL_BUILD"]

    is_msvc = env.get("is_msvc", False)
    lib_ext = ".lib" if is_msvc else ".a"
    lib_prefix = "" if is_msvc else "lib"
    libs = ["{}git2{}".format(lib_prefix, lib_ext)]

    source = prepare_source(
        Path(env.Dir("#thirdparty/git2/libgit2").abspath),
        Path(env.Dir("#bin/thirdparty/libgit2-source").abspath),
        Path(env.File("#thirdparty/git2/patches/0001-restrict-redirect-origin.patch").abspath),
    )

    git2 = env.CMakeBuild(
        "#bin/thirdparty/git2-origin/",
        str(source),
        cmake_options=config,
        cmake_outputs=libs,
        cmake_targets=[],
        dependencies=deps + [
            env.File("#thirdparty/git2/patches/0001-restrict-redirect-origin.patch"),
            env.File("#tools/git2_patch.py"),
            env.File(str(source / ".redirect-patch")),
        ],
        languages=["C"],
    )

    env.Append(CPPPATH=["#thirdparty/git2/libgit2/include"])
    env.Prepend(LIBS=git2[1:])
    if env["platform"] == "windows":
        env.PrependUnique(LIBS=["secur32"])
    elif env["platform"] == "macos":
        env.Append(LIBS=["iconv"])

    return git2


def exists(env):
    return "CMake" in env


def generate(env):
    env.AddMethod(build_library, "BuildGIT2")
