#!/usr/bin/env python3
#
# Test for DeobfuscationSort post-processing script for NZBGet.
#
# Copyright (C) 2014-2017 Andrey Prygunkov <hugbug@users.sourceforge.net>
# Copyright (C) 2024 Denis <denis@nzbget.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with the program.  If not, see <https://www.gnu.org/licenses/>.
#

import sys
from os.path import dirname
import os
import shutil
import subprocess
import json
import getopt
from pathlib import Path
import re
import logging

# Exit codes used by NZBGet
POSTPROCESS_SUCCESS = 93
POSTPROCESS_NONE = 95
POSTPROCESS_ERROR = 94

# The root directory of the DeobfuscationSort module
ROOT_DIR = dirname(__file__)
# The directory to store the test files
TEST_DIR = ROOT_DIR + "/__"
# The entrypoint of the DeobfuscationSort module
DEOBFUSCATION_SORT_ENTRYPOINT = Path(ROOT_DIR) / "main.py"
# The default size of the files to create for testing
FILESIZE_DEFAULT = 10

cleanup = False
preview = False
verbose = False
test_ids = []

options, _ = getopt.getopt(sys.argv[1:], "t:v", ["testid=", "verbose"])
for opt, arg in options:
    if opt in ("-v", "--verbose"):
        verbose = True
    elif opt in ("-c", "--cleanup"):
        cleanup = True
    elif opt in ("-p", "--preview"):
        preview = True
    elif opt in ("-t", "--testid"):
        test_ids.append(arg)


# Configure logging for debugging
logging.basicConfig(level=(verbose and logging.DEBUG or logging.WARN), format="%(levelname)s: %(message)s")

logging.debug("Test script for DeobfuscationSort")

def get_python():
    if os.name == "nt":
        return "python"
    return "python3"

def set_defaults():
    # script options
    os.environ["NZBPO_MOVIESDIR"] = get_test_dir_path_file("movies").as_posix()
    os.environ["NZBPO_SERIESDIR"] = get_test_dir_path_file("series").as_posix()
    os.environ["NZBPO_DATEDDIR"] = get_test_dir_path_file("dated").as_posix()
    os.environ["NZBPO_OTHERTVDIR"] = get_test_dir_path_file("tv").as_posix()
    os.environ["NZBPO_VIDEOEXTENSIONS"] = ".mkv,.mp4,.avi"
    os.environ["NZBPO_SATELLITEEXTENSIONS"] = ".srt"
    os.environ["NZBPO_MULTIPLEEPISODES"] = "list"
    os.environ["NZBPO_EPISODESEPARATOR"] = "-"
    os.environ["NZBPO_MINSIZE"] = "0"
    os.environ["NZBPO_TVCATEGORIES"] = "tv"
    os.environ["NZBPO_MOVIESFORMAT"] = "%fn"
    os.environ["NZBPO_OTHERTVFORMAT"] = "%fn"
    os.environ["NZBPO_SERIESFORMAT"] = "%fn"
    os.environ["NZBPO_DATEDFORMAT"] = "%fn"
    os.environ["NZBPO_LOWERWORDS"] = "the,of,and,at,vs,a,an,but,nor,for,on,so,yet"
    os.environ["NZBPO_UPPERWORDS"] = "III,II,IV"
    os.environ["NZBPO_DEOBFUSCATEWORDS"] = "RP,1,NZBGeek,Obfuscated,Obfuscation,Scrambled,sample,Pre,postbot,xpost,Rakuv,WhiteRev,BUYMORE,AsRequested,AlternativeToRequested,GEROV,Z0iDS3N,Chamele0n,4P,4Planet,AlteZachen,RePACKPOST,RARBG,SirUppington"
    os.environ["NZBPO_RELEASEGROUPS"] = "3DM,AJP69,BHDStudio,BMF,BTN,BV,BeyondHD,CJ,CLASS,CMRG,CODEX,CONSPIR4CY,CRX,CRiSC,Chotab,CtrlHD,D-Z0N3,D-Z0N3,D-Z0N3,DEViANCE,DON,Dariush,DrinkOrDie,E.N.D,E1,EA,EDPH,ESiR,EVO,EVO,EViLiSO,EXCiSION,EbP,Echelon,FAiRLiGHT,FLUX,FTW-HD,FilmHD,FoRM,FraMeSToR,FraMeSToR,GALAXY,GS88,Geek,HANDJOB,HATRED,HDMaNiAcS,HYBRID,HiDt,HiFi,HiP,Hoodlum,IDE,KASHMiR,KRaLiMaRKo,Kalisto,LEGi0N,LiNG,LoRD,MZABI,Myth,NCmt,NTb,NTb,NyHD,ORiGEN,P0W4HD,PARADOX,PTer,Penumbra,Positive,RELOADED,REVOLT,Radium,Risciso,SA89,SKIDROW,SMURF,STEAMPUNKS,SaNcTi,SbR,SiMPLE,TBB,TDD,TEPES,TayTo,ThD,VLAD,ViTALiTY,VietHD,W4NK3R,WMING,ZIMBO,ZQ,c0ke,de[42],decibeL,hdalx,iFT,iON,luvBB,maVen,nmd,playHD,playWEB"
    os.environ["NZBPO_SERIESYEAR"] = "yes"
    os.environ["NZBPO_OVERWRITE"] = "no"
    os.environ["NZBPO_CLEANUP"] = cleanup and "yes" or "no"
    os.environ["NZBPO_PREVIEW"] = preview and "yes" or "no"
    os.environ["NZBPO_VERBOSE"] = "yes"

    # properties of nzb-file
    os.environ["NZBPP_DIRECTORY"] = TEST_DIR
    os.environ["NZBPP_NZBNAME"] = "test"
    os.environ["NZBPP_PARSTATUS"] = "2"
    os.environ["NZBPP_UNPACKSTATUS"] = "2"
    os.environ["NZBPP_CATEGORY"] = ""

    # pp-parameters of nzb-file, including DNZB-headers
    os.environ["NZBPR__DNZB_USENZBNAME"] = "no"
    os.environ["NZBPR__DNZB_PROPERNAME"] = ""
    os.environ["NZBPR__DNZB_EPISODENAME"] = ""


def print_difference(expected, actual, prefix=""):
    """Prints a caret (^) at positions where the expected and actual strings differ."""
    diff_line = ""
    if prefix != "":
        diff_line += len(prefix) * " "
    diff_line += ''.join('^' if e != a else ' ' for e, a in zip(expected, actual))
    # Extend the diff_line to match the length of the longer string
    diff_line += '^' * (len(expected) - len(actual)) if len(expected) > len(actual) else ' ' * (len(actual) - len(expected))
    print(diff_line)


def get_test_dir_path_file(file_path):
    # Ensure the argument is a Path object
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    relative_base_path = None
    if file_path.is_absolute():
        # Convert absolute file path to relative
        relative_base_path = file_path.relative_to('/').parent
    else:
        # Use the parent directory of the relative file path
        relative_base_path = file_path.parent
    return Path(TEST_DIR) / relative_base_path / file_path.name


def get_test_file_parent(file_path):
    # Ensure the argument is a Path object
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    relative_base_path = None
    if file_path.is_absolute():
        # Convert absolute file path to relative
        relative_base_path = file_path.relative_to('/').parent
    else:
        # Use the parent directory of the relative file path
        relative_base_path = file_path.parent
    return relative_base_path


def create_test_file(test_file, test_file_size):
    """Creates a test file with the specified size in the appropriate directory."""
    
    # Ensure the directory exists
    test_file.parent.mkdir(parents=True, exist_ok=True)

    # Create the file with the specified size
    with test_file.open("wb") as f:
        f.write(b"0" * test_file_size)

    if verbose:
        print(f"Created file: {test_file} with size {test_file_size}")


def execute_deobfuscation_sort(test_file):
    """Executes the main.py script for a given file."""
    os.environ["NZBPP_DIRECTORY"] = str(test_file.parent)
    os.environ["NZBPP_NZBFILENAME"] = test_file.name
    proc = subprocess.Popen(
        [get_python(), DEOBFUSCATION_SORT_ENTRYPOINT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    out, err = proc.communicate()
    ret = proc.returncode

    if verbose:
        print("stdout: %s" % out.decode())
        print("stderr: %s" % err.decode())

    dest = None  # Initialize destination variable
    try:
        if ret == POSTPROCESS_SUCCESS:
            match = re.search(r"^(?:\[[A-Z]+\] )?destination path: (.+)", out.decode(), re.MULTILINE)
            if match:
                dest_path = Path(match.group(1))
                logging.debug(f"Extracted destination path: {dest_path}")

                # Ensure path is inside TEST_DIR before making it relative
                if dest_path.is_relative_to(TEST_DIR):  # Python 3.9+
                    dest = (Path("/") / dest_path.relative_to(TEST_DIR)).as_posix()
                else:
                    raise Exception(f"Destination path {dest_path} is not inside {TEST_DIR}.")

        elif ret == POSTPROCESS_NONE:
            dest = (Path("/") / test_file.relative_to(TEST_DIR)).as_posix()

        elif ret == POSTPROCESS_ERROR:
            raise Exception(f"DeobfuscationSort returned error\n\n{out.decode()}\n\n{err.decode()}")

        else:
            raise Exception(f"Unexpected return code: {ret}")
        
        assert(Path(dest).is_absolute())
        test_dir_dest_path = get_test_dir_path_file(dest)
        assert(test_dir_dest_path.is_file())

    except Exception as e:
        logging.exception("An error occurred while processing the destination path.", exc_info=e)

    return out, err, ret, dest


def run_test(testobj):
    set_defaults()
    for prop_name in testobj:
        if str(prop_name) in ["NZBPO_MOVIESDIR", "NZBPO_SERIESDIR", "NZBPO_DATEDDIR", "NZBPO_OTHERTVDIR"]:
            os.environ[str(prop_name)] = get_test_dir_path_file(str(testobj[prop_name])).as_posix()
        else:
            os.environ[str(prop_name)] = str(testobj[prop_name])
        if verbose:
            print("%s: %s" % (prop_name, os.environ[prop_name]))
    input_file_spec = testobj["INPUTFILE"]
    output_file_spec = testobj["OUTPUTFILE"]
    input_file_path = get_test_dir_path_file(input_file_spec)

    # Clean and recreate TEST_DIR for a clean start    
    shutil.rmtree(TEST_DIR, True)
    os.makedirs(TEST_DIR, exist_ok=False)

    # Get the directory of the input file
    # This is used to set the NZBPP_DIRECTORY environment variable
    input_test_dir = get_test_file_parent(input_file_spec)
    if input_test_dir:
        os.environ["NZBPP_DIRECTORY"] = str(input_test_dir)
        # os.environ["NZBPP_FILENAME"] = input_file_name
        if verbose:
            print("Using NZB directory: %s" % os.environ["NZBPP_DIRECTORY"])

    input_file_size = testobj.get("INPUTFILESIZE", FILESIZE_DEFAULT)
    output_file_size = testobj.get("OUTPUTFILESIZE", FILESIZE_DEFAULT)

    success = False

    # Create input file
    create_test_file(input_file_path, input_file_size)

    # Run deobfuscation sort on the input file
    out, err, ret, dest = execute_deobfuscation_sort(input_file_path)

    success = dest == output_file_spec

    if success:
        print("%s: SUCCESS" % testobj["id"])
    if not success:
        if verbose:
            print("********************************************************")
            print("*** FAILURE")
            print("stdout: %s" % out.decode())
            print("stderr: %s" % err.decode())
            print("*** FAILURE")
            print("id: %s" % testobj["id"])
            print("expected:    %s" % output_file_spec)
            print("destination: %s" % dest)
            print_difference(str(output_file_spec), str(dest), "destination: ")
            print("********************************************************")
            sys.exit(1)
        else:
            print("%s: FAILED" % testobj["id"])
            if output_file_spec == "":
                print("destination: %s" % dest)
    elif verbose:
        print("expected:    %s" % output_file_spec)
        print("destination: %s" % dest)

testdata = json.load(open(ROOT_DIR + "/testdata.json", encoding="UTF-8"))
for testobj in testdata:
    if test_ids == [] or testobj["id"] in test_ids:
        run_test(testobj)
