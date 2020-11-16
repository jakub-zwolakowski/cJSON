#! /usr/bin/env python3

# This script regenerates TrustInSoft CI configuration.

# Run from the root of the JSON-C project:
# $ python3 trustinsoft/regenerate.py

import re # sub
import json # dumps, load
import os # path, makedirs
import binascii # hexlify
import shutil # copyfileobj
import glob # iglob
import argparse # ArgumentParser, add_argument, parse_args

# Outputting JSON.
def string_of_json(obj):
    # Output standard pretty-printed JSON (RFC 7159) with 4-space indentation.
    s = json.dumps(obj, indent=4)
    # Sometimes we need to have multiple "include" fields in the outputted
    # JSON, which is unfortunately impossible in the internal python
    # representation (OK, it is technically possible, but too cumbersome to
    # bother implementing it here), so we can name these fields 'include_',
    # 'include__', etc, and they are all converted to 'include' before
    # outputting as JSON.
    s = re.sub(r'"include_+"', '"include"', s)
    return s

# Make a command line from a dictionary of lists.
def string_of_options(options):
    elts = []
    for opt_prefix in options: # e.g. opt_prefix == "-D"
        for opt_value in options[opt_prefix]: # e.g. opt_value == "HAVE_OPEN"
            elts.append(opt_prefix + opt_value) # e.g. "-DHAVE_OPEN"
    return " ".join(elts)


test_files_dir = "tests"
fuzz_input_dir = os.path.join("fuzzing", "inputs")

# --------------------------------------------------------------------------- #
# ---------------------------------- CHECKS --------------------------------- #
# --------------------------------------------------------------------------- #

def check_dir(dir):
    if os.path.isdir(dir):
        print("   > OK! Directory '%s' exists." % dir)
    else:
        exit("Directory '%s' not found." % dir)

# Initial check.
print("1. Check if all necessary directories and files exist...")
check_dir("trustinsoft")
check_dir(test_files_dir)
check_dir(fuzz_input_dir)

# --------------------------------------------------------------------------- #
# -------------------- GENERATE trustinsoft/common.config ------------------- #
# --------------------------------------------------------------------------- #

common_config_path = os.path.join("trustinsoft", "common.config")

def make_common_config():
    # C files.
    c_files = [
        "cJSON_Utils.c",
        os.path.join("tests", "unity", "src", "unity.c"),
    ]
    # Compilation options.
    compilation_cmd = (
        {
            "-I": [],
            "-D": [
                "UNITY_EXCLUDE_SETJMP_H"
            ],
            "-U": [],
        }
    )
    # Filesystem.
    json_patch_tests = sorted(
        glob.iglob(os.path.join("tests", "json-patch-tests", "*.json"), recursive=False)
    )
    json_patch_tests = list(
        map(lambda file:
            {
                "name": os.path.join("json-patch-tests", os.path.basename(file)),
                "from": os.path.join("..", file),
            },
        json_patch_tests)
    )
    tests_and_expected = sorted(
        glob.iglob(os.path.join("tests", "inputs", "test*"), recursive=False)
    )
    tests_and_expected = list(
        map(lambda file:
            {
                "name": os.path.join("inputs", os.path.basename(file)),
                "from": os.path.join("..", file),
            },
        tests_and_expected)
    )
    # Whole common.config JSON.
    config = (
        {
            "files": list(map(lambda file: os.path.join("..", file), c_files)),
            "compilation_cmd": string_of_options(compilation_cmd),
            "val-clone-on-recursive-calls-max-depth": 10000,
            "val-warn-pointer-arithmetic-out-of-bounds": False,
            "filesystem": { "files": json_patch_tests + tests_and_expected },
        }
    )
    # Done.
    return config

common_config = make_common_config()
with open(common_config_path, "w") as file:
    print("2. Generate the 'trustinsoft/common.config' file.")
    file.write(string_of_json(common_config))

# --------------------------------------------------------------------------- #
# -------------------- GENERATE trustinsoft/fuzz.config --------------------- #
# --------------------------------------------------------------------------- #

fuzz_config_path = os.path.join("trustinsoft", "fuzz.config")

def make_fuzz_config():
    # C files.
    c_files = [
        "cJSON.c",
    ]
    # Filesystem.
    fuzzing_files = sorted(
        glob.iglob(os.path.join("fuzzing", "inputs", "test*"), recursive=False)
    )
    fuzzing_files = list(
        map(lambda file:
            {
                "name": os.path.join("fuzzing", "include", os.path.basename(file)),
                "from": os.path.join("..", file),
            },
        fuzzing_files)
    )
    # Whole fuzz.config JSON.
    config = (
        {
            "files": list(map(lambda file: os.path.join("..", file), c_files)),
            "filesystem": { "files": fuzzing_files },
        }
    )
    # Done.
    return config

fuzz_config = make_fuzz_config()
with open(fuzz_config_path, "w") as file:
    print("3. Generate the 'trustinsoft/fuzz.config' file.")
    file.write(string_of_json(fuzz_config))

# --------------------------------------------------------------------------- #
# -------------------------------- tis.config ------------------------------- #
# --------------------------------------------------------------------------- #

test_files = sorted(
    glob.iglob(os.path.join(test_files_dir, "*.c"), recursive=False)
)

def make_test(test_file):
    basename = os.path.basename(test_file)
    tis_test = (
        {
            "name": basename,
            "files": [ test_file ],
            "include": common_config_path,
        }
    )
    if basename == "parse_hex4.c":
        tis_test["no-results"] = True
    return tis_test

generalized_tests = [
    {
        "name": "parse_hex4.c - GENERALIZED",
        "main": "parse_hex4_should_parse_all_combinations",
        "compilation_cmd":
            string_of_options (
                {
                    "-D": [
                        "UNITY_EXCLUDE_SETJMP_H",
                        "TIS_GENERALIZED_MODE"
                    ]
                }
            ),
        "files": [
            "tests/parse_hex4.c",
            "tests/unity/src/unity.c",
            "cJSON_Utils.c"
        ],
        "value-profile": "analyzer",
        "val-slevel-merge-after-loop": "-@all",
        "slevel": 1000
    }
]

fuzz_input_files = sorted(
    glob.iglob(os.path.join(fuzz_input_dir, "test*"), recursive=False)
)

def make_fuzz_test(fuzz_input_file):
    basename = os.path.basename(fuzz_input_file)
    return (
        {
            "name": ("afl.c " + basename),
            "files": [ os.path.join("fuzzing", "afl.c") ],
            "val-args": " " + os.path.join("fuzzing", "include", basename),
            "include": common_config_path,
            "include_": fuzz_config_path,
        }
    )

tis_config = (
    list(map(make_test, test_files)) +
    generalized_tests +
    list(map(make_fuzz_test, fuzz_input_files))
)
with open("tis.config", "w") as file:
    print("4. Generate the tis.config file.")
    file.write(string_of_json(tis_config))
