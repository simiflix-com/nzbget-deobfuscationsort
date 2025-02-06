import os
import sys
import re
from nzbget_utils import POSTPROCESS_ERROR, logerr, loginf, logwar
from pathlib import Path


class NzbProperties:
    """
    Holds the NZB properties extracted from environment variables with prefixes NZBPP and NZBPR.
    """

    def __init__(self):
        self.nzb_name = os.environ["NZBPP_NZBNAME"]
        self.download_dir = Path(os.environ["NZBPP_DIRECTORY"])
        self.category = os.environ.get("NZBPP_CATEGORY", "")
        self.dnzb_proper_name = os.environ.get("NZBPR__DNZB_PROPERNAME", "")
        self.dnzb_episode_name = os.environ.get("NZBPR__DNZB_EPISODENAME", "")
        self.dnzb_movie_year = os.environ.get("NZBPR__DNZB_MOVIEYEAR", "")
        self.dnzb_more_info = os.environ.get("NZBPR__DNZB_MOREINFO", "")


class ProcessingParameters:
    """
    Holds the post-processing parameters extracted from environment variables with the prefix NZBPO.
    """

    def __init__(self):
        self.video_type_map = None
        self.movies_format = os.environ["NZBPO_MOVIESFORMAT"]
        self.series_format = os.environ["NZBPO_SERIESFORMAT"]
        self.dated_format = os.environ["NZBPO_DATEDFORMAT"]
        self.othertv_format = os.environ["NZBPO_OTHERTVFORMAT"]
        self.multiple_episodes = os.environ["NZBPO_MULTIPLEEPISODES"]
        self.episode_separator = os.environ["NZBPO_EPISODESEPARATOR"]
        self.movies_dir = Path(os.environ["NZBPO_MOVIESDIR"])
        self.series_dir = Path(os.environ["NZBPO_SERIESDIR"])
        self.dated_dir = Path(os.environ["NZBPO_DATEDDIR"])
        self.othertv_dir = Path(os.environ["NZBPO_OTHERTVDIR"])

        self.video_extensions = (
            os.environ["NZBPO_VIDEOEXTENSIONS"].replace(" ", "").lower().split(",")
        )
        self.satellite_extensions = (
            os.environ["NZBPO_SATELLITEEXTENSIONS"].replace(" ", "").lower().split(",")
        )
        self.lower_words = os.environ["NZBPO_LOWERWORDS"].replace(" ", "").split(",")
        self.upper_words = os.environ["NZBPO_UPPERWORDS"].replace(" ", "").split(",")
        self.deobfuscate_words = (
            os.environ["NZBPO_DEOBFUSCATEWORDS"].replace(" ", "").split(",")
        )
        self.release_groups = (
            os.environ["NZBPO_RELEASEGROUPS"].replace(" ", "").split(",")
        )
        self.series_year = os.environ.get("NZBPO_SERIESYEAR", "yes") == "yes"
        self.tv_categories = os.environ["NZBPO_TVCATEGORIES"].lower().split(",")
        self.dnzb_headers = os.environ.get("NZBPO_DNZBHEADERS", "yes") == "yes"
        self.prefer_nzb_name = os.environ.get("NZBPO_PREFERNZBNAME", "") == "yes"
        self.deep_scan = self.dnzb_headers
        self.deep_scan_ratio = 0.60


class Options:
    """
    Holds script options and combines NzbProperties and ProcessingParameters.

    The required options (mostly NZBPO variables) are checked before instantiating the other classes.
    """

    def __init__(self):
        self.required_options = (
            "NZBPO_MOVIESDIR",
            "NZBPO_SERIESDIR",
            "NZBPO_DATEDDIR",
            "NZBPO_OTHERTVDIR",
            "NZBPO_VIDEOEXTENSIONS",
            "NZBPO_SATELLITEEXTENSIONS",
            "NZBPO_MINSIZE",
            "NZBPO_MOVIESFORMAT",
            "NZBPO_SERIESFORMAT",
            "NZBPO_OTHERTVFORMAT",
            "NZBPO_DATEDFORMAT",
            "NZBPO_EPISODESEPARATOR",
            "NZBPO_OVERWRITE",
            "NZBPO_CLEANUP",
            "NZBPO_LOWERWORDS",
            "NZBPO_UPPERWORDS",
            "NZBPO_DEOBFUSCATEWORDS",
            "NZBPO_RELEASEGROUPS",
            "NZBPO_TVCATEGORIES",
            "NZBPO_PREVIEW",
            "NZBPO_VERBOSE",
        )
        self._check_required_options()

        # Instantiate refactored classes.
        self.nzb_properties = NzbProperties()
        self.processing_parameters = ProcessingParameters()

        # Script options from NZBPO
        self.min_size = int(os.environ["NZBPO_MINSIZE"]) << 20
        self.overwrite = os.environ["NZBPO_OVERWRITE"] == "yes"
        self.cleanup = os.environ["NZBPO_CLEANUP"] == "yes"
        self.preview = os.environ["NZBPO_PREVIEW"] == "yes"
        self.verbose = os.environ["NZBPO_VERBOSE"] == "yes"

        if self.preview:
            logwar("*** PREVIEW MODE ON - NO CHANGES TO FILE SYSTEM ***")

    def _check_required_options(self):
        for optname in self.required_options:
            if optname.upper() not in os.environ:
                logerr(
                    f"Option {optname[6:]} is missing in configuration file. Please check script settings"
                )
                sys.exit(POSTPROCESS_ERROR)
