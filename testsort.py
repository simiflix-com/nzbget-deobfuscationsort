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

# GuessIt supported video extensions
_VIDEO_EXTENSIONS = ["avi", "mkv", "mov", "mp4", "webm", "wmv"]
# GuessIt supported subtitle extensions
_SATELLITE_EXTENSIONS = ["srt", "idx", "sub", "ssa", "ass"]

cleanup = False
preview = False
verbose = False
test_ids = []

options, _ = getopt.getopt(
    sys.argv[1:], "v:c:p:t", ["verbose", "preview", "cleanup", "testid="]
)
for opt, arg in options:
    if opt in ("-v", "--verbose"):
        verbose = True
    elif opt in ("-p", "--preview"):
        preview = True
    elif opt in ("-c", "--cleanup"):
        cleanup = True
    elif opt in ("-t", "--testid"):
        test_ids.append(arg)


# Configure logging for debugging
logging.basicConfig(
    level=(verbose and logging.DEBUG or logging.WARN),
    format="%(message)s",
)

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
    os.environ["NZBPO_VIDEOEXTENSIONS"] = ",".join(_VIDEO_EXTENSIONS)
    os.environ["NZBPO_SATELLITEEXTENSIONS"] = ",".join(_SATELLITE_EXTENSIONS)
    os.environ["NZBPO_MULTIPLEEPISODES"] = "list"
    os.environ["NZBPO_EPISODESEPARATOR"] = "-"
    os.environ["NZBPO_MINSIZE"] = "0"
    os.environ["NZBPO_TVCATEGORIES"] = "tv"
    os.environ["NZBPO_MOVIESFORMAT"] = "%fn"
    os.environ["NZBPO_SERIESFORMAT"] = "%fn"
    os.environ["NZBPO_OTHERTVFORMAT"] = "%fn"
    os.environ["NZBPO_DATEDFORMAT"] = "%fn"
    os.environ["NZBPO_LOWERWORDS"] = "the,of,and,at,vs,a,an,but,nor,for,on,so,yet"
    os.environ["NZBPO_UPPERWORDS"] = "III,II,IV"
    os.environ["NZBPO_DEOBFUSCATEWORDS"] = (
        "RP,1,NZBGeek,Obfuscated,Obfuscation,Scrambled,sample,Pre,postbot,xpost,Rakuv,WhiteRev,BUYMORE,AsRequested,AlternativeToRequested,GEROV,Z0iDS3N,Chamele0n,4P,4Planet,AlteZachen,RePACKPOST,RARBG,SirUppington"
    )
    os.environ["NZBPO_DNZBHEADERS"] = "no"
    os.environ["NZBPO_PREFERNZBNAME"] = "no"
    os.environ["NZBPO_RELEASEGROUPS"] = (
        "3DM,AJP69,BHDStudio,BMF,BTN,BV,BeyondHD,CJ,CLASS,CMRG,CODEX,CONSPIR4CY,CRX,CRiSC,Chotab,CtrlHD,D-Z0N3,DEViANCE,DON,Dariush,DrinkOrDie,E.N.D,E1,EA,EDPH,ESiR,EVO,EViLiSO,EXCiSION,EbP,Echelon,FAiRLiGHT,FLUX,FTW-HD,FilmHD,FoRM,FraMeSToR,GALAXY,GS88,Geek,HANDJOB,HATRED,HDMaNiAcS,HYBRID,HiDt,HiFi,HiP,Hoodlum,IDE,KASHMiR,KRaLiMaRKo,Kalisto,LEGi0N,LiNG,LoRD,MZABI,Myth,NCmt,NTb,NyHD,ORiGEN,P0W4HD,PARADOX,PTer,Penumbra,Positive,RELOADED,REVOLT,Radium,Risciso,SA89,SKIDROW,SMURF,STEAMPUNKS,SaNcTi,SbR,SiMPLE,TBB,TDD,TEPES,TayTo,ThD,VLAD,ViTALiTY,VietHD,W4NK3R,WMING,ZIMBO,ZQ,c0ke,de[42],decibeL,hdalx,iFT,iON,luvBB,maVen,nmd,playHD,playWEB"
    )
    os.environ["NZBPO_SERIESYEAR"] = "yes"
    os.environ["NZBPO_OVERWRITE"] = "no"
    os.environ["NZBPO_VERBOSE"] = verbose and "yes" or "no"
    os.environ["NZBPO_PREVIEW"] = preview and "yes" or "no"
    os.environ["NZBPO_CLEANUP"] = cleanup and "yes" or "no"

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


def _difference_line(expected, actual, prefix=""):
    """Prints a caret (^) at positions where the expected and actual strings differ."""
    diff_line = ""
    if prefix != "":
        diff_line += len(prefix) * " "
    diff_line += "".join("^" if e != a else " " for e, a in zip(expected, actual))
    # Extend the diff_line to match the length of the longer string
    diff_line += (
        "^" * (len(expected) - len(actual))
        if len(expected) > len(actual)
        else " " * (len(actual) - len(expected))
    )
    if diff_line.strip() != "":
        return diff_line + "\n"
    return ""


def get_test_dir_path_file(file_path):
    # Ensure the argument is a Path object
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    relative_base_path = None
    if file_path.is_absolute():
        # Convert absolute file path to relative
        relative_base_path = file_path.relative_to("/").parent
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
        relative_base_path = file_path.relative_to("/").parent
    else:
        # Use the parent directory of the relative file path
        relative_base_path = file_path.parent
    return relative_base_path


def get_video_file_in_finaldir(finaldir_path):
    # Ensure the argument is a Path object
    if not isinstance(finaldir_path, Path):
        finaldir_path = Path(finaldir_path)

    # Ensure path is inside TEST_DIR before making it relative
    if not finaldir_path.is_relative_to(TEST_DIR):  # Python 3.9+
        raise Exception(f"Destination path {finaldir_path} is not inside {TEST_DIR}.")

    for entry in finaldir_path.iterdir():
        if entry.is_file():
            if entry.suffix.lower().lstrip(".") in _VIDEO_EXTENSIONS:
                return Path("/") / entry.relative_to(TEST_DIR)
    return None


def get_absolute_path_from_test_dir_(file_path):
    # Ensure the argument is a Path object
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    relative_base_path = None
    if file_path.is_absolute():
        # Convert absolute file path to relative
        relative_base_path = file_path.relative_to("/").parent
    else:
        # Use the parent directory of the relative file path
        relative_base_path = file_path.parent
    return relative_base_path
    return Path(TEST_DIR) / relative_base_path / file_path.name


def create_test_file(test_file, test_file_size):
    """Creates a test file with the specified size in the appropriate directory."""

    # Ensure the directory exists
    test_file.parent.mkdir(parents=True, exist_ok=True)

    # Create the file with the specified size
    with test_file.open("wb") as f:
        f.write(b"0" * test_file_size)

    logging.info(f"Created file: {test_file} with size {test_file_size}")


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

    stdout = out.decode()
    stderr = err.decode()
    logging.info(f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}")

    # Initialize destination variable
    dest = ""
    dest_file = None
    final_dir = None
    try:
        if ret == POSTPROCESS_SUCCESS:
            match = re.search(r"^\[NZB\] FINALDIR=(.+)", stdout, re.MULTILINE)
            if match:
                final_dir = Path(match.group(1))
                logging.debug(f"NZB FINALDIR: {final_dir}")
                dest_file = get_video_file_in_finaldir(final_dir)

        elif ret == POSTPROCESS_NONE:
            dest_file = Path("/") / test_file.relative_to(TEST_DIR)

        elif ret == POSTPROCESS_ERROR:
            raise Exception(
                f"DeobfuscationSort returned POSTPROCESS_ERROR\n\n{stdout}\n\n{stderr}"
            )

        else:
            logging.error(
                f"DeobfuscationSort returned unexpected {ret}:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
            )
            raise Exception(f"DeobfuscationSort returned unexpected {ret}")

        # Ensure the destination path is absolute
        assert dest_file is not None
        assert dest_file.is_absolute()
        # Return the destination path as a string
        dest = dest_file.as_posix()

    except Exception as e:
        logging.exception(
            "An error occurred while processing the destination path.", exc_info=e
        )

    return dest


def run_test(testobj):
    set_defaults()
    for prop_name in testobj:
        if str(prop_name) in [
            "NZBPO_MOVIESDIR",
            "NZBPO_SERIESDIR",
            "NZBPO_DATEDDIR",
            "NZBPO_OTHERTVDIR",
        ]:
            os.environ[str(prop_name)] = get_test_dir_path_file(
                str(testobj[prop_name])
            ).as_posix()
        else:
            os.environ[str(prop_name)] = str(testobj[prop_name])
        logging.info("%s: %s" % (prop_name, os.environ[prop_name]))

    # Clean and recreate TEST_DIR for a clean start
    shutil.rmtree(TEST_DIR, True)
    os.makedirs(TEST_DIR, exist_ok=False)

    if "INPUTFILE" in testobj and "OUTPUTFILE" in testobj:
        input_file_spec = testobj["INPUTFILE"]
        output_file_spec = testobj["OUTPUTFILE"]

        input_file_path = get_test_dir_path_file(input_file_spec)

        # Get the directory of the input file
        # This is used to set the NZBPP_DIRECTORY environment variable
        input_test_dir = get_test_file_parent(input_file_spec)
        if input_test_dir:
            os.environ["NZBPP_DIRECTORY"] = str(input_test_dir)
            # os.environ["NZBPP_FILENAME"] = input_file_name
            logging.info("Using NZB directory: %s" % os.environ["NZBPP_DIRECTORY"])

        input_file_size = testobj.get("INPUTFILESIZE", FILESIZE_DEFAULT)

        # Create input file
        create_test_file(input_file_path, input_file_size)
    else:
        # TODO: Handle this case
        logging.info(f"Test id {testobj['id']}: not implemented")
        return

    # Run deobfuscation sort on the input file
    success = False
    dest = execute_deobfuscation_sort(input_file_path)

    success = dest == output_file_spec

    if success:
        print(f"{testobj['id']}: SUCCESS")
    else:
        print(f"{testobj['id']}: FAILED")

    if verbose:
        max_len = max(len(str(output_file_spec)), len(str(dest))) + len("destination: ")
        logging.info(
            f"""{max_len * (success and "-" or "#")}
id: {testobj["id"]}
expected:    {output_file_spec}
destination: {dest}
{_difference_line(str(output_file_spec), str(dest), "destination: ")}{max_len * (success and "-" or "#")}
"""
        )

    if not success:
        sys.exit(1)


testdata = json.load(open(ROOT_DIR + "/testdata.json", encoding="UTF-8"))
for testobj in testdata:
    if test_ids == [] or testobj["id"] in test_ids:
        run_test(testobj)
