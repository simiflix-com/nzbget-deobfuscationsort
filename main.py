#!/usr/bin/env python
#
# DeobfuscationSort post-processing script for NZBGet.
#
# Copyright (C) 2025 Simi Flix <simiflix.com@gmail.com>
# Copyright (C) 2013-2020 Andrey Prygunkov <hugbug@users.sourceforge.net>
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

import os
import sys
import json
from pathlib import Path

from apply import Apply

from nzbget_utils import (
    POSTPROCESS_ERROR,
    POSTPROCESS_NONE,
    POSTPROCESS_SUCCESS,
    loginf,
    logwar,
)

sys.stdout.reconfigure(encoding="utf-8")

COMMIT_HASH = "c2a734c322f67ffa9b798204c2f8f030f29e4940"


def get_version():
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        manifest_path = os.path.join(script_dir, "manifest.json")

        # Read the JSON file
        with open(manifest_path, "r") as f:
            data = json.load(f)
            return data.get("version", "Unknown")
    except (FileNotFoundError, json.JSONDecodeError):
        return "Unknown"


EXTENSION_VERSION = get_version()
loginf(f"Running version {EXTENSION_VERSION}")

# Check if directory still exist (for post-process again)
nzbp_directory = os.environ["NZBPP_DIRECTORY"]
if not (nzbp_directory and Path(nzbp_directory).is_dir()):
    loginf(f'NZBP directory "{nzbp_directory}" does not exist, exiting')
    sys.exit(POSTPROCESS_NONE)

# Check par and unpack status for errors
if (
    os.environ["NZBPP_PARSTATUS"] == "1"
    or os.environ["NZBPP_PARSTATUS"] == "4"
    or os.environ["NZBPP_UNPACKSTATUS"] == "1"
):
    logwar(f'Download of "{os.environ["NZBPP_NZBNAME"]}" has failed, exiting')
    sys.exit(POSTPROCESS_NONE)

apply = Apply().run()

# Returing status to NZBGet
if apply.errors:
    sys.exit(POSTPROCESS_ERROR)
elif apply.files_moved:
    sys.exit(POSTPROCESS_SUCCESS)
else:
    sys.exit(POSTPROCESS_NONE)
