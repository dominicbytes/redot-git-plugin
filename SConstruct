#!/usr/bin/env python

import os

EnsureSConsVersion(3, 1, 2)
EnsurePythonVersion(3, 6)

opts = Variables([], ARGUMENTS)

env = Environment(ENV=os.environ)

# Define our options
opts.Add(PathVariable("target_path",
         "The path where the lib is installed.", "addons/godot-git-plugin/", PathVariable.PathAccept))
opts.Add(PathVariable("target_name", "The library name.",
         "libgit_plugin", PathVariable.PathAccept))
opts.Add(BoolVariable("test_harness",
         "Expose test-only bindings for the provider endpoints.", False))

# Updates the environment with the option variables.
opts.Update(env)
test_harness = env["test_harness"]
plugin_paths = {
    "target_name": env["target_name"],
    "target_path": env.Dir(env["target_path"]).abspath,
}
for plugin_option in ["target_name", "target_path", "test_harness"]:
    ARGUMENTS.pop(plugin_option, None)

if ARGUMENTS.get("custom_api_file", "") != "":
    ARGUMENTS["custom_api_file"] = env.File(ARGUMENTS["custom_api_file"]).abspath

ARGUMENTS["target"] = "editor"
env = SConscript("godot-cpp/SConstruct")

# Update the binding builders' environment before cloning it for the plugin.
source_root = env.Dir("#").abspath
if env.get("is_msvc", False):
    env.AppendUnique(CCFLAGS=[
        "/experimental:deterministic",
        "/pathmap:{}=.".format(source_root),
        "/d1trimfile:{}".format(source_root),
    ])
    env.AppendUnique(LINKFLAGS=["/Brepro"])
else:
    env.AppendUnique(CCFLAGS=[
        "-ffile-prefix-map={}=.".format(source_root),
        "-fdebug-prefix-map={}=.".format(source_root),
    ])
env = env.Clone()
env.__class__.msvc = env.get("is_msvc", False)

# Force linking with LTO on windows MSVC, silence the linker complaining that libgit uses LTO but we are not linking with it.
if env["platform"] == "windows" and env.get("is_msvc", False):
    env.AppendUnique(LINKFLAGS=["/LTCG"])

# OpenSSL Builder
env.Tool("openssl", toolpath=["tools"])

# SSH2 Builder
env.Tool("cmake", toolpath=["tools"])
env.Tool("ssh2", toolpath=["tools"])
env.Tool("git2", toolpath=["tools"])

opts.Update(env)
env.Replace(**plugin_paths)

ssl = env.OpenSSL()
ssh2 = env.BuildSSH2(ssl)
ssl += ssh2
git2 = env.BuildGIT2(ssl)

if test_harness:
    env.AppendUnique(CPPDEFINES=["REDOT_GIT_TEST_HARNESS"])

Export("ssl")
Export("env")

SConscript("godot-git-plugin/SCsub")

# Generates help for the -h scons option.
Help(opts.GenerateHelpText(env))
