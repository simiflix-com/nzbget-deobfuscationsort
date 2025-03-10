import os
import re
from pathlib import Path
from nzbget_utils import logerr, logwar, loginf, logdet
from options import Options

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import guessit


# * From SABnzbd+ (with modifications) *
class Determine:
    _BOUNDARY_STRIP_CHARS = ("_", ".", "-")

    _RELEVANT_PATH_PART_RE = re.compile(
        r"[-a-z0-9]*[ ._]+([-a-z0-9]*[ ._][-a-z0-9]*)*", re.IGNORECASE
    )

    _REPLACE_AFTER = {
        "()": "",
        "..": ".",
        "__": "_",
        "  ": " ",
        "//": "/",
        " - - ": " - ",
        "--": "-",
    }
    _RE_UPPERCASE = re.compile(r"{{([^{]*)}}")
    _RE_LOWERCASE = re.compile(r"{([^{]*)}")

    def __init__(self, videofiles: list[Path], options: Options):
        self.videofiles = videofiles
        self.options = options
        self.nzb_properties = self.options.nzb_properties
        self.processing_parameters = self.options.processing_parameters
        # Determine whether we can use the NZB name for the destination path
        self.use_nzb_name = (
            self.processing_parameters.prefer_nzb_name and len(videofiles) == 1
        )
        if self.processing_parameters.prefer_nzb_name:
            if len(videofiles) == 1:
                loginf(
                    f"Processing single video file {videofiles[0]}, using NZB directory to determine destination path"
                )
            else:
                loginf(
                    f"Processing {len(videofiles)} files: {videofiles}, ignoring PreferNZBName configuration option"
                )
        # Determine if we should force the video file to be treated as a TV show
        self.force_tv = (
            self.nzb_properties.category.lower()
            in self.processing_parameters.tv_categories
        )
        # Separator character used between file name and opening brace
        # for duplicate files such as "My Movie (2).mkv"
        # Class name: `ScriptState`
        self.dupe_separator = " "

        self.deobfuscate_re = None
        # Construct deobfuscation regex from words if provided
        if len(self.processing_parameters.deobfuscate_words) and len(
            self.processing_parameters.deobfuscate_words[0]
        ):
            self.deobfuscate_re = re.compile(
                r"(.+?-[.0-9a-z]+)(?:\W+(?:{})[a-z0-9]*\W*)*$".format(
                    "|".join(
                        [
                            re.escape(word)
                            for word in self.processing_parameters.deobfuscate_words
                        ]
                    )
                ),
                flags=re.IGNORECASE,
            )
        # Construct the regex for cases where the NZB directory name contains
        # the video file extension and trailing obfuscation
        video_file_suffix_re = "|".join(self.processing_parameters.video_extensions)
        self.nzb_dir_rstrip_re = re.compile(
            rf"^(.+?)(?:\.(?:{video_file_suffix_re}|\#[0-9]+)\b)+.*$",  # Strip anything following a video file suffix or a numeric suffix
            flags=re.IGNORECASE,
        )

        loginf(
            f"Determine: use_nzb_name={self.use_nzb_name} force_tv={self.force_tv} ({self.nzb_properties.category} {self.force_tv and 'in' or 'not in'} {self.processing_parameters.tv_categories})"
        )

    def path_subst(path, mapping):
        """Replace the sort string elements by real values.
        Non-elements are copied literally.
        path = the sort string
        mapping = array of tuples that maps all elements to their values
        """
        # Determine if the path is absolute so we can validate if we
        # return a mapped path with the same property
        is_absolute = Path(path).is_absolute()

        newpath = []
        plen = len(path)
        n = 0

        # Sort list of mapping tuples by their first elements. First ascending by element,
        # then descending by element length.
        # Preparation to replace elements from longest to shortest in alphabetical order.
        #
        # >>> m = [('bb', 4), ('aa', 3), ('b', 6), ('aaa', 2), ('zzzz', 1), ('a', 5)]
        # >>> m.sort(key=lambda t: t[0])
        # >>> m
        # [('a', 5), ('aa', 3), ('aaa', 2), ('b', 6), ('bb', 4), ('zzzz', 1)]
        # >>> m.sort(key=lambda t: len(t[0]), reverse=True)
        # >>> m
        # [('zzzz', 1), ('aaa', 2), ('aa', 3), ('bb', 4), ('a', 5), ('b', 6)]
        mapping.sort(key=lambda t: t[0])
        mapping.sort(key=lambda t: len(t[0]), reverse=True)

        while n < plen:
            result = path[n]
            if result == "%":
                for key, value, msg in deprecation_support(mapping):
                    if path.startswith(key, n):
                        n += len(key) - 1
                        result = value
                        if msg:
                            logwar("specifier %s is deprecated, %s" % (key, msg))
                        break
            newpath.append(result)
            n += 1
        mapped_path = "".join(
            map(lambda x: ".".join(x) if isinstance(x, list) else str(x), newpath)
        )
        assert Path(mapped_path).is_absolute() == is_absolute
        return mapped_path

    def get_deobfuscated_dirname(self, dirname, name=None):
        """
        Deobfuscate the directory name and properly case all terms, including
        quality identifiers and release terms.

        Args:
            dirname (str): The original directory name to be deobfuscated.
            name (str, optional): The reference name used for title matching.

        Returns:
            dirname (str): The deobfuscated and properly cased directory name.
        """
        dirname_clean = dirname.strip()
        dirname = dirname_clean

        dirname_rigthstripped = re.sub(self.nzb_dir_rstrip_re, r"\1", dirname_clean)
        dirname = dirname_rigthstripped
        logdet(
            f'Right-stripped NZB dirname: "{dirname_clean}" --> "{dirname_rigthstripped}"'
        )

        # Apply deobfuscation regex if provided
        if self.deobfuscate_re:
            dirname_deobfuscated = re.sub(
                self.deobfuscate_re, r"\1", dirname_rigthstripped
            )
            dirname = dirname_deobfuscated
            logdet(
                f'De-obfuscated NZB dirname: "{dirname_rigthstripped}" --> "{dirname_deobfuscated}"'
            )
        else:
            logerr(
                "Cannot de-obfuscate NZB dirname: "
                'invalid value for configuration value "DeobfuscateWords": "{}"'.format(
                    self.processing_parameters.deobfuscate_words
                )
            )

        if name:
            # Determine if file name is likely to be properly cased
            case_check_re = (
                r"^[A-Z0-9]+.+\b\d{3,4}p\b.*-[-A-Za-z0-9]+[A-Z]+[-A-Za-z0-9]*$"
            )
            if re.match(case_check_re, dirname):
                loginf(f"Not fixing a properly cased dirname: '{dirname}'")
            else:
                title, _, _ = self.get_titles(name, True)
                dirname_title = []

                release_groups_list = [
                    re.escape(token)
                    for token in self.processing_parameters.release_groups
                ]
                release_groups_re = "|".join(release_groups_list)

                def re_unescape(escaped_re):
                    return re.sub(r"\\(.)", r"\1", escaped_re)

                def scene_group_case(match):
                    for extra_group in release_groups_list:
                        loginf(
                            f"Comparing extra group '{extra_group}' with match '{match.group(1)}'"
                        )
                        if re.match(
                            f"{extra_group}$", match.group(1), flags=re.IGNORECASE
                        ):
                            return "-" + re_unescape(extra_group)
                    return "-" + re.sub(r"I", "i", match.group(1).upper())

                terms = [
                    (r"(\d{3,4})p", r"\1p"),
                    (r"x(\d{3,4})", r"x\1"),
                    (r"(\d{2,2}Bit)", r"\1Bit"),
                    (r"BluRay", "BluRay"),
                    (r"Web(.?)DL", r"Web\1DL"),
                    (r"Web(.?)Rip", r"Web\1Rip"),
                    (r"AAC", "AAC"),
                    (r"Dolby", "Dolby"),
                    (r"Atmos", "Atmos"),
                    (r"TrueHD", "TrueHD"),
                    (r"DD([57]).?1", "DD\1.1"),
                    (r"DTS.?X", r"DTS-X"),
                    (r"DTS.?HD", r"DTS-HD"),
                    (r"DTS.?ES", r"DTS-ES"),
                    (r"DTS.?HD.?MA", r"DTS-HD.?MA"),
                    (
                        r"-(([A-Za-z0-9]+)|{})$".format(release_groups_re),
                        scene_group_case,
                    ),
                ]

                title_match_re = r"(.+?)\b\d{3,4}p\b"
                title_match = re.search(title_match_re, dirname, flags=re.IGNORECASE)
                if title_match:
                    title_len = min(len(title_match.group(1)), len(title))
                    loginf(
                        f'Comparing dirname "{dirname[0:title_len]}" with titled dirname: "{title[0:title_len]}"'
                    )
                    for idx in range(title_len):
                        if (
                            dirname[idx] != title[idx]
                            and dirname[idx].lower() == title[idx].lower()
                        ):
                            dirname_title.append(title[idx])
                        else:
                            dirname_title.append(dirname[idx])

                    dirname = "".join(dirname_title) + dirname[title_len:]
                else:
                    logwar(f'dirname "{dirname}" does not match {title_match_re}"')

                for term in terms:
                    dirname = re.sub(term[0], term[1], dirname, flags=re.IGNORECASE)

                loginf(f'Case-fixed dirname: "{dirname}"')

        return dirname

    def get_deobfuscated_dirname_mapping(self, dirname, name=None):
        """
        Deobfuscate the directory name and properly case all terms, including
        quality identifiers and release terms.

        Args:
            dirname (str): The original directory name to be deobfuscated.
            name (str, optional): The reference name used for title matching.

        Returns:
            tuple: A tuple containing four variations of the directory name:
                - dirname (str): The deobfuscated and properly cased directory name.
                - dots (str): The dirname with spaces replaced by dots.
                - underscores (str): The dirname with spaces replaced by underscores.
                - spaces (str): The dirname with dots and underscores replaced by spaces.
        """
        dirname = self.get_deobfuscated_dirname(dirname, name)

        # The title with spaces replaced by dots
        dots = dirname.replace(" - ", "-").replace(" ", ".").replace("_", ".")
        dots = dots.replace("(", ".").replace(")", ".").replace("..", ".").rstrip(".")

        # The dirname with spaces replaced by underscores
        underscores = (
            dirname.replace(" ", "_").replace(".", "_").replace("__", "_").rstrip("_")
        )

        # The dirname with dots and underscores replaced by spaces
        spaces = (
            dirname.replace("_", " ").replace(".", " ").replace("  ", " ").rstrip(" ")
        )

        return dirname, dots, underscores, spaces

    def to_title_case(self, text):
        """
        Improved version of Python's title() function.

        Args:
            text (str): The text to convert to title case

        Returns:
            str: The text in title case
        """
        # Apply Python's built-in title() function
        title = text.title()

        # Fix Python's title() bug with apostrophes
        title = title.replace("'S", "'s")

        # Make sure some words such as 'and' or 'of' stay lowercased
        for x in self.processing_parameters.lower_words:
            xtitled = x.title()
            title = Determine.replace_word(title, xtitled, x)

        # Make sure some words such as 'III' or 'IV' stay uppercased
        for x in self.processing_parameters.upper_words:
            xtitled = x.title()
            title = Determine.replace_word(title, xtitled, x)

        # Make sure the first letter of the title is always uppercase
        if title:
            title = title[0].title() + title[1:]

        return title

    def get_titles(self, name, apply_title_case=False):
        """
        Generates three variations of a title with improved title casing.

        Args:
            name (str): The original title name
            apply_title_case (bool): Whether to apply enhanced title casing

        Returns:
            tuple: Three variations of the title (normal, dots, underscores)
        """
        # make valid filename
        title = re.sub(r"[\"\:\?\*\\\/\<\>\|]", " ", name)

        if apply_title_case:
            title = self.to_title_case(title)

        # The title with spaces replaced by dots
        dots = title.replace(" - ", "-").replace(" ", ".").replace("_", ".")
        dots = dots.replace("(", ".").replace(")", ".").replace("..", ".").rstrip(".")

        # The title with spaces replaced by underscores
        underscores = (
            title.replace(" ", "_").replace(".", "_").replace("__", "_").rstrip("_")
        )

        return title, dots, underscores

    @staticmethod
    def replace_word(text, word_old, word_new):
        """
        Replace a word in text while maintaining word boundaries.
        This ensures we only replace whole words, not parts of words.

        Args:
            text (str): The text to process
            word_old (str): The word to find
            word_new (str): The word to replace it with

        Returns:
            str: The text with the word replaced
        """

        def replace_word_case_sensitive(text, word_old, word_new):
            pattern = r"\b" + re.escape(word_old) + r"\b"
            return re.sub(pattern, word_new, text)

        # Try case-sensitive replacement first
        result = replace_word_case_sensitive(text, word_old, word_new)

        # If no replacement was made, try case-insensitive
        if result == text:
            pattern = r"\b" + re.escape(word_old) + r"\b"
            result = re.sub(pattern, word_new, text, flags=re.IGNORECASE)

        return result

    @staticmethod
    def get_decades(year):
        """
        Return 2-digit and 4-digit decades given 'year'.
        For example, for year "2024" or 2024:
        - decade = "20" (2-digit decade)
        - decade2 = "2020" (4-digit decade)

        Args:
            year (str or int): The year to process

        Returns:
            tuple: Two variations of the decade:
                - decade (str): 2-digit decade (e.g., "20" for 2020s)
                - decade2 (str): 4-digit decade (e.g., "2020" for 2020s)
        """
        if year:
            try:
                year_str = str(year)
                decade = year_str[2:3] + "0"  # Take third digit and add 0 (e.g., "20")
                decade2 = (
                    year_str[:3] + "0"
                )  # Take first three digits and add 0 (e.g., "2020")
            except IndexError:
                decade = ""
                decade2 = ""
        else:
            decade = ""
            decade2 = ""
        return decade, decade2

    @staticmethod
    def to_lowercase(path):
        """
        Lowercases any characters enclosed in {}.
        """
        while True:
            m = Determine._RE_LOWERCASE.search(path)
            if not m:
                break
            path = path[: m.start()] + m.group(1).lower() + path[m.end() :]

        # Just in case
        path = path.replace("{", "")
        path = path.replace("}", "")
        return path

    @staticmethod
    def to_uppercase(path):
        """
        Uppercases any characters enclosed in {{}}.
        """
        while True:
            m = Determine._RE_UPPERCASE.search(path)
            if not m:
                break
            path = path[: m.start()] + m.group(1).upper() + path[m.end() :]
        return path

    @staticmethod
    def strip_parts_of_path_str(path_str: str):
        """
        Remove leading and trailing punctuation characters from every part of the path.
        """
        path = Path(path_str)
        is_absolute = path.is_absolute()

        # Operate on all path parts and the stem of the file name
        path_stem = path.with_suffix("")

        def strip_part(part: str):
            """
            Strip all leading/trailing word separators from a part of the path.
            """
            part_prev = ""
            while part != part_prev:
                part_prev = part
                for strip_char in Determine._BOUNDARY_STRIP_CHARS:
                    part = part.strip().strip(strip_char)
            return part

        clean_parts = [strip_part(x) for x in path_stem.parts]
        clean_path = Path(Path().joinpath(*clean_parts).as_posix() + path.suffix)

        assert clean_path.is_absolute() == is_absolute
        assert clean_path.suffix == path.suffix
        return clean_path.as_posix()

    @staticmethod
    def format_matches_dict(matches_dict):
        """
        Formats a MatchesDict into a multi-line string with aligned key-value pairs.

        Keys are right-aligned and the values are left aligned.

        Args:
            matches_dict (dict): The MatchesDict object to format.

        Returns:
            str: A formatted multi-line string of key-value pairs.
        """
        if not matches_dict:
            return ""

        # Determine the maximum key length.
        max_key_length = max(len(str(key)) for key in matches_dict.keys())

        formatted_lines = []
        # Use the "Open Box" (U+2423) as a fill character.
        non_whitespace_space = "\u2423"
        for key, value in matches_dict.items():
            # Format each line so that the colon is placed directly after the key,
            # and the value is aligned in a consistent column.
            formatted_lines.append(
                f"{str(key):{non_whitespace_space}>{max_key_length}}: {value}"
            )

        return "\n".join(formatted_lines)

    def add_common_mapping(self, videofile_path: Path, guess, mapping):
        """Add common mapping elements used by all video types.

        Args:
            videofile_path (Path): Path object representing the video file
            guess (dict): GuessIt results dictionary
            mapping (list): List to add the mapping tuples to
        """
        # Original dir name, file name and extension
        original_dirname = self.nzb_properties.download_dir.name
        original_fname = videofile_path.stem
        original_fext = videofile_path.suffix
        original_category = os.environ.get("NZBPP_CATEGORY", "")

        # Directory name
        title_name = (
            original_dirname.replace("-", " ").replace(".", " ").replace("_", " ")
        )
        fname_tname, fname_tname_two, fname_tname_three = self.get_titles(
            title_name, True
        )
        fname_name, fname_name_two, fname_name_three = self.get_titles(
            title_name, False
        )
        mapping.append(("%dn", original_dirname))
        mapping.append(("%^dn", fname_tname))
        mapping.append(("%.dn", fname_tname_two))
        mapping.append(("%_dn", fname_tname_three))
        mapping.append(("%^dN", fname_name))
        mapping.append(("%.dN", fname_name_two))
        mapping.append(("%_dN", fname_name_three))

        # File name
        title_name = (
            original_fname.replace("-", " ").replace(".", " ").replace("_", " ")
        )
        fname_tname, fname_tname_two, fname_tname_three = self.get_titles(
            title_name, True
        )
        fname_name, fname_name_two, fname_name_three = self.get_titles(
            title_name, False
        )
        mapping.append(("%fn", original_fname))
        mapping.append(("%^fn", fname_tname))
        mapping.append(("%.fn", fname_tname_two))
        mapping.append(("%_fn", fname_tname_three))
        mapping.append(("%^fN", fname_name))
        mapping.append(("%.fN", fname_name_two))
        mapping.append(("%_fN", fname_name_three))

        # File extension
        mapping.append(("%ext", original_fext))
        mapping.append(("%EXT", original_fext.upper()))
        mapping.append(("%Ext", original_fext.title()))

        # Category
        category_tname, category_tname_two, category_tname_three = self.get_titles(
            original_category, True
        )
        category_name, category_name_two, category_name_three = self.get_titles(
            original_category, False
        )
        mapping.append(("%cat", category_tname))
        mapping.append(("%.cat", category_tname_two))
        mapping.append(("%_cat", category_tname_three))
        mapping.append(("%cAt", category_name))
        mapping.append(("%.cAt", category_name_two))
        mapping.append(("%_cAt", category_name_three))

        # Video information
        mapping.append(("%qf", guess.get("source", "")))
        mapping.append(("%qss", guess.get("screen_size", "")))
        mapping.append(("%qvc", guess.get("video_codec", "")))
        mapping.append(("%qac", guess.get("audio_codec", "")))
        mapping.append(("%qah", guess.get("audio_channels", "")))
        mapping.append(("%qrg", guess.get("release_group", "")))

        # De-obfuscated directory name
        (
            deobfuscated_dirname,
            deobfuscated_dirname_dots,
            deobfuscated_dirname_underscores,
            deobfuscated_dirname_spaces,
        ) = self.get_deobfuscated_dirname_mapping(original_dirname)
        mapping.append(("%ddn", deobfuscated_dirname))
        mapping.append(("%.ddn", deobfuscated_dirname_dots))
        mapping.append(("%_ddn", deobfuscated_dirname_underscores))
        mapping.append(("%^ddn", deobfuscated_dirname_spaces))
        (
            deobfuscated_dirname_titled,
            deobfuscated_dirname_titled_dots,
            deobfuscated_dirname_titled_underscores,
            deobfuscated_dirname_titled_spaces,
        ) = self.get_deobfuscated_dirname_mapping(original_dirname, title_name)
        mapping.append(("%ddN", deobfuscated_dirname_titled))
        mapping.append(("%.ddN", deobfuscated_dirname_titled_dots))
        mapping.append(("%_ddN", deobfuscated_dirname_titled_underscores))
        mapping.append(("%^ddN", deobfuscated_dirname_titled_spaces))

    def add_series_mapping(self, guess, mapping):
        # Show name
        series = guess.get("title", "")
        show_tname, show_tname_two, show_tname_three = self.get_titles(series, True)
        show_name, show_name_two, show_name_three = self.get_titles(series, False)
        mapping.append(("%sn", show_tname))
        mapping.append(("%s.n", show_tname_two))
        mapping.append(("%s_n", show_tname_three))
        mapping.append(("%sN", show_name))
        mapping.append(("%s.N", show_name_two))
        mapping.append(("%s_N", show_name_three))

        # season number
        season_num = str(guess.get("season", ""))
        mapping.append(("%s", season_num))
        mapping.append(("%0s", season_num.rjust(2, "0")))

        # episode names
        title = guess.get("episode_title")
        if title:
            ep_tname, ep_tname_two, ep_tname_three = self.get_titles(title, True)
            ep_name, ep_name_two, ep_name_three = self.get_titles(title, False)
            mapping.append(("%en", ep_tname))
            mapping.append(("%e.n", ep_tname_two))
            mapping.append(("%e_n", ep_tname_three))
            mapping.append(("%eN", ep_name))
            mapping.append(("%e.N", ep_name_two))
            mapping.append(("%e_N", ep_name_three))
        else:
            mapping.append(("%en", ""))
            mapping.append(("%e.n", ""))
            mapping.append(("%e_n", ""))
            mapping.append(("%eN", ""))
            mapping.append(("%e.N", ""))
            mapping.append(("%e_N", ""))

        # episode number
        if not isinstance(guess.get("episode"), list):
            episode_num = str(guess.get("episode", ""))
            mapping.append(("%e", episode_num))
            mapping.append(("%0e", episode_num.rjust(2, "0")))
        else:
            # multi episodes
            episodes = [str(item) for item in guess.get("episode")]
            episode_num_all = ""
            episode_num_just = ""
            if self.processing_parameters.multiple_episodes == "range":
                episode_num_all = (
                    episodes[0]
                    + self.processing_parameters.episode_separator
                    + episodes[-1]
                )
                episode_num_just = (
                    episodes[0].rjust(2, "0")
                    + self.processing_parameters.episode_separator
                    + episodes[-1].rjust(2, "0")
                )
            else:  # if multiple_episodes == 'list':
                for episode_num in episodes:
                    ep_prefix = (
                        self.processing_parameters.episode_separator
                        if episode_num_all != ""
                        else ""
                    )
                    episode_num_all += ep_prefix + episode_num
                    episode_num_just += ep_prefix + episode_num.rjust(2, "0")

            mapping.append(("%e", episode_num_all))
            mapping.append(("%0e", episode_num_just))

        # year
        year = str(guess.get("year", ""))
        mapping.append(("%y", year))

        # decades
        decade, decade_two = self.get_decades(year)
        mapping.append(("%decade", decade))
        mapping.append(("%0decade", decade_two))

    def add_movies_mapping(self, guess, mapping):
        # title
        name = guess.get("title", "")
        ttitle, ttitle_two, ttitle_three = self.get_titles(name, True)
        title, title_two, title_three = self.get_titles(name, False)
        mapping.append(("%title", ttitle))
        mapping.append(("%.title", ttitle_two))
        mapping.append(("%_title", ttitle_three))

        # title (short forms)
        mapping.append(("%t", ttitle))
        mapping.append(("%.t", ttitle_two))
        mapping.append(("%_t", ttitle_three))

        mapping.append(("%tT", title))
        mapping.append(("%t.T", title_two))
        mapping.append(("%t_T", title_three))

        # year
        year = str(guess.get("year", ""))
        mapping.append(("%y", year))

        # decades
        decade, decade_two = self.get_decades(year)
        mapping.append(("%decade", decade))
        mapping.append(("%0decade", decade_two))

        # imdb
        mapping.append(("%imdb", guess.get("imdb", "")))
        mapping.append(("%cpimdb", guess.get("cpimdb", "")))

    def add_dated_mapping(self, guess, mapping):
        # title
        name = guess.get("title", "")
        ttitle, ttitle_two, ttitle_three = self.get_titles(name, True)
        title, title_two, title_three = self.get_titles(name, True)
        mapping.append(("%title", title))
        mapping.append(("%.title", title_two))
        mapping.append(("%_title", title_three))

        # title (short forms)
        mapping.append(("%t", title, "consider using %sn"))
        mapping.append(("%.t", title_two, "consider using %s.n"))
        mapping.append(("%_t", title_three, "consider using %s_n"))

        # Show name
        series = guess.get("title", "")
        show_tname, show_tname_two, show_tname_three = self.get_titles(series, True)
        show_name, show_name_two, show_name_three = self.get_titles(series, False)
        mapping.append(("%sn", show_tname))
        mapping.append(("%s.n", show_tname_two))
        mapping.append(("%s_n", show_tname_three))
        mapping.append(("%sN", show_name))
        mapping.append(("%s.N", show_name_two))
        mapping.append(("%s_N", show_name_three))

        # Some older code at this point stated:
        # "Guessit doesn't provide episode names for dated tv shows"
        # but was referring to the invalid field '%desc'
        # In my researches I couldn't find such a case, but just to be sure
        ep_title = guess.get("episode_title")
        if ep_title:
            ep_tname, ep_tname_two, ep_tname_three = self.get_titles(ep_title, True)
            ep_name, ep_name_two, ep_name_three = self.get_titles(ep_title, False)
            mapping.append(("%en", ep_tname))
            mapping.append(("%e.n", ep_tname_two))
            mapping.append(("%e_n", ep_tname_three))
            mapping.append(("%eN", ep_name))
            mapping.append(("%e.N", ep_name_two))
            mapping.append(("%e_N", ep_name_three))
        else:
            mapping.append(("%en", ""))
            mapping.append(("%e.n", ""))
            mapping.append(("%e_n", ""))
            mapping.append(("%eN", ""))
            mapping.append(("%e.N", ""))
            mapping.append(("%e_N", ""))

        # date
        date = guess.get("date")

        # year
        year = str(date.year)
        mapping.append(("%year", year))
        mapping.append(("%y", year))

        # decades
        decade, decade_two = self.get_decades(year)
        mapping.append(("%decade", decade))
        mapping.append(("%0decade", decade_two))

        # month
        month = str(date.month)
        mapping.append(("%m", month))
        mapping.append(("%0m", month.rjust(2, "0")))

        # day
        day = str(date.day)
        mapping.append(("%d", day))
        mapping.append(("%0d", day.rjust(2, "0")))

    def strip_useless_parts(self, videofile_path: Path):
        """
        Strips useless parts from the videofile_path.

        Args:
            videofile_path (Path): The videofile to process.

        Returns:
            str: The cleaned-up filename.
        """
        candidate_path = videofile_path.relative_to(
            self.nzb_properties.download_dir.parent
        )
        logdet(f"Stripped filename: {candidate_path.as_posix()}")

        path_parts_list = [*candidate_path.parts]
        logdet(f"Path parts: {path_parts_list}")

        relevant_path = Path()
        # Process directory name parts
        for directory_part in path_parts_list[:-1]:
            if re.search(Determine._RELEVANT_PATH_PART_RE, directory_part):
                relevant_path = relevant_path / directory_part
            else:
                loginf(
                    f'Skipping obfuscated directory part {directory_part}". Relevant path so far: "{relevant_path.as_posix()}"'
                )

        # Process file name part
        if re.search(Determine._RELEVANT_PATH_PART_RE, candidate_path.stem):
            relevant_path = relevant_path / candidate_path.name
        else:
            if relevant_path.parts:
                # Skip the obfuscated filename and append the suffix to the parent directory of the relevant path
                relevant_path = relevant_path.parent / (
                    relevant_path.name + candidate_path.suffix
                )
                loginf(
                    f'Ignoring obfuscated filename "{candidate_path.name}", appending suffix to parent directory: "{relevant_path.as_posix()}"'
                )
            else:
                # As a last resort, use the obfuscated NZB name
                relevant_path = Path(candidate_path.stem + candidate_path.suffix)
                loginf(
                    f'No relevant path parts found in "{candidate_path.stem}", using obfuscated NZB name "{relevant_path.as_posix()}"'
                )

        return relevant_path

    def remove_year(self, title):
        """
        Removes the year from the series name if it exists.

        Args:
            title (str): The title to process.

        Returns:
            str: The title without the year.
        """
        m = re.compile(r"..*(\((19|20)\d\d\))").search(title)
        if not m:
            m = re.compile(r"..*((19|20)\d\d)").search(title)
        if m:
            loginf("Removing year from series name")
            title = title.replace(m.group(1), "").strip()
        return title

    def apply_dnzb_headers(self, guess):
        """
        Applies DNZB headers if they exist.

        Args:
            guess (dict): The guess dictionary to modify.
        """
        dnzb_used = False
        if self.nzb_properties.dnzb_proper_name != "":
            dnzb_used = True
            logdet("Using DNZB-ProperName")
            if guess["vtype"] == "series":
                proper_name = self.nzb_properties.dnzb_proper_name
                if not self.processing_parameters.series_year:
                    proper_name = self.remove_year(proper_name)
                guess["title"] = proper_name
            else:
                guess["title"] = self.nzb_properties.dnzb_proper_name

        if self.nzb_properties.dnzb_episode_name != "" and guess["vtype"] == "series":
            dnzb_used = True
            logdet("Using DNZB-EpisodeName")
            guess["episode_title"] = self.nzb_properties.dnzb_episode_name

        if self.nzb_properties.dnzb_movie_year != "":
            dnzb_used = True
            logdet("Using DNZB-MovieYear")
            guess["year"] = self.nzb_properties.dnzb_movie_year

        if self.nzb_properties.dnzb_more_info != "":
            dnzb_used = True
            logdet("Using DNZB-MoreInfo")
            if guess["type"] == "movie":
                regex = re.compile(
                    r"^http://www.imdb.com/title/(tt[0-9]+)/$", re.IGNORECASE
                )
                matches = regex.match(self.nzb_properties.dnzb_more_info)
                if matches:
                    guess["imdb"] = matches.group(1)
                    guess["cpimdb"] = "cp(" + guess["imdb"] + ")"

        if dnzb_used:
            loginf(f"Guess after applying DNZB headers: {guess}")

    def year_and_season_equal(self, guess):
        """
        Checks if the season number and year are equal.

        Args:
            guess (dict): The guess dictionary to check.

        Returns:
            bool: True if season and year are equal, False otherwise.
        """
        equal = (
            guess.get("season")
            and guess.get("year")
            and guess.get("season") == guess.get("year")
        )
        logdet(f"year_and_season_equal: {equal}")
        return equal

    def is_movie(self, guess):
        """
        Determines if the guess represents a movie.

        Args:
            guess (dict): The guess dictionary to check.

        Returns:
            bool: True if it's a movie, False otherwise.
        """
        has_no_episode = guess.get("type") == "episode" and guess.get("episode") is None
        is_movie = (
            has_no_episode
            or guess.get("edition")
            or (self.year_and_season_equal(guess) and guess.get("type") != "episode")
        )
        logdet(f"is_movie: {is_movie}")
        return is_movie

    def guess_info(self, videofile_path: Path):
        """Guess information about the video using GuessIt.

        Args:
            videofile_path (Path): Path object representing the video file

        Returns:
            dict: GuessIt results dictionary with video information
        """
        if self.use_nzb_name:
            guessfilename = self.get_deobfuscated_dirname(
                self.nzb_properties.download_dir.name
            )
            # If the videofile_path has a videofile suffix, append it
            if (
                videofile_path.suffix.lower().lstrip(".")
                in self.processing_parameters.video_extensions
            ):
                guessfilename = guessfilename + videofile_path.suffix
            logdet(
                f'Input for GuessIt: NZB name "{self.nzb_properties.download_dir.as_posix()}" from download_dir "{self.nzb_properties.download_dir.name}" --> "{guessfilename}"'
            )
        else:
            # Get filename and apply basic cleanup
            guessfilename = self.strip_useless_parts(videofile_path)
            logdet(
                f'Input for GuessIt: Stripped useless parts from filename "{videofile_path.as_posix()}" --> "{guessfilename}"'
            )

        # workaround for titles starting with numbers (which guessit has problems with) (part 1)
        path, tmp_filename = os.path.split(guessfilename)
        pad_start_digits = tmp_filename[0].isdigit()
        if pad_start_digits:
            guessfilename = os.path.join(path, "T" + tmp_filename)

        logdet(f'Calling GuessIt with "{guessfilename}"')

        # Use guessit directly as Python 3 handles Unicode by default
        guess = guessit.api.guessit(
            guessfilename, {"allowed_languages": [], "allowed_countries": []}
        )

        logdet(f"GuessIt result:\n{Determine.format_matches_dict(guess)}")

        # workaround for titles starting with numbers (part 2)
        if pad_start_digits:
            guess["title"] = guess["title"][1:]
            if guess["title"] == "":
                guess["title"] = os.path.splitext(os.path.basename(guessfilename))[0][
                    1:
                ]
                logdet("use filename as title for recovery")

        # fix some strange guessit guessing:
        # if guessit doesn't find a year in the file name it thinks it is episode,
        # but we prefer it to be handled as movie instead

        if self.is_movie(guess):
            guess["type"] = "movie"
            logdet("episode without episode-number is a movie")

        # treat parts as episodes ("Part.2" or "Part.II")
        if guess.get("type") == "movie" and guess.get("part") is not None:
            guess["type"] = "episode"
            guess["episode"] = guess.get("part")
            logdet("treat parts as episodes")

        # add season number if not present
        if guess["type"] == "episode" and (
            guess.get("season") is None or self.year_and_season_equal(guess)
        ):
            guess["season"] = 1
            logdet("force season 1")

        # detect if year is part of series name
        if guess["type"] == "episode":
            if self.processing_parameters.series_year:
                if (
                    guess.get("year") is not None
                    and guess.get("title") is not None
                    and guess.get("season") != guess.get("year")
                    and guess["title"] == self.remove_year(guess["title"])
                ):
                    guess["title"] += " " + str(guess["year"])
                    logdet("year is part of title")
            else:
                guess["title"] = self.remove_year(guess["title"])

        if guess["type"] == "movie":
            date = guess.get("date")
            if date:
                guess["vtype"] = "dated"
            elif self.force_tv:
                guess["vtype"] = "othertv"
            else:
                guess["vtype"] = "movie"
        elif guess["type"] == "episode":
            guess["vtype"] = "series"
        else:
            guess["vtype"] = guess["type"]

        if self.processing_parameters.dnzb_headers:
            self.apply_dnzb_headers(guess)

        logdet(f"Final GuessIt structure:\n{Determine.format_matches_dict(guess)}")
        return guess

    def guess_dupe_separator(self, format):
        """Determine most suitable character for dupe_separator"""

        self.dupe_separator = " "
        format_fname = os.path.basename(format)

        for x in ("%.t", "%s.n", "%s.N", "%e.n", "%e.N"):
            if format_fname.find(x) > -1:
                self.dupe_separator = "."
                return

        for x in ("%_t", "%s_n", "%s_N", "%e_n", "%e_N"):
            if format_fname.find(x) > -1:
                self.dupe_separator = "_"
                return

    def get_video_type_map(self, video_type: str):
        """
        Returns a tuple (dest_dir, fmt, mapping_func) based solely on the environment parameters.
        This processing of configuration values remains constant for all video files,
        independent of GuessIt parsing.

        Args:
            video_type (str): The video type (e.g., "movie", "series", "dated", "othertv").

        Returns:
            tuple: (dest_dir, fmt, mapping_func) where dest_dir is the destination directory,
                fmt is the format string, and mapping_func is the function to add
                type-specific mapping details.
                Returns (None, None, None) if the type isn't recognized.
        """
        if not self.processing_parameters.video_type_map:
            video_type_params = {
                "movie": (
                    self.processing_parameters.movies_dir,
                    self.processing_parameters.movies_format,
                    self.add_movies_mapping,
                ),
                "series": (
                    self.processing_parameters.series_dir,
                    self.processing_parameters.series_format,
                    self.add_series_mapping,
                ),
                "dated": (
                    self.processing_parameters.dated_dir,
                    self.processing_parameters.dated_format,
                    self.add_dated_mapping,
                ),
                "othertv": (
                    self.processing_parameters.othertv_dir,
                    self.processing_parameters.othertv_format,
                    self.add_movies_mapping,
                ),
            }
            self.processing_parameters.video_type_map = video_type_params.get(
                video_type, (None, None, None)
            )
        self.dest_dir = self.processing_parameters.video_type_map[0]

        logdet(
            f'NZBPO_MOVIESDIR="{os.environ["NZBPO_MOVIESDIR"]}", '
            f'NZBPO_SERIESDIR="{os.environ["NZBPO_SERIESDIR"]}", '
            f'NZBPO_DATEDDIR="{os.environ["NZBPO_DATEDDIR"]}", '
            f'NZBPO_OTHERTVDIR="{os.environ["NZBPO_OTHERTVDIR"]}"'
        )

        if self.dest_dir and self.dest_dir.is_absolute():
            logdet(
                f'Using destination directory: "{self.dest_dir}" [from video_type_map="{self.processing_parameters.video_type_map}"]'
            )
        else:
            # Fallback if the destination directory is not set
            self.dest_dir = self.nzb_properties.download_dir.parent
            loginf(
                f'Using fallback destination directory: "{self.dest_dir}" [parent of nzb_properties.download_dir="{self.nzb_properties.download_dir}"]'
            )

        return self.processing_parameters.video_type_map[1:]

    def clean_videofile_path(self, videofile_path: Path) -> Path:
        """
        Cleans up the videofile_path by removing unnecessary parts.

        Args:
            videofile_path (Path): The videofile to process.

        Returns: Path: The cleaned-up videofile path.
        """

        nzb_dir = videofile_path.parent.name
        clean_nzb_dir = self.get_deobfuscated_dirname(nzb_dir)
        if clean_nzb_dir == nzb_dir:
            return videofile_path

        clean_videofile_path = videofile_path.parent.parent.joinpath(
            clean_nzb_dir
        ).joinpath(videofile_path.name)
        loginf(f'clean_videofile_path: clean_videofile_path: "{clean_videofile_path}"')
        return clean_videofile_path

    def construct_path(self, videofile_path: Path) -> Path:
        """Parses the filename and generates a new name for renaming.

        Expects `filename` to be a Path object and works exclusively with pathlib.
        """
        loginf(f'construct_path("{videofile_path}")')
        clean_videofile_path = self.clean_videofile_path(videofile_path)

        # Parse the filename using GuessIt.
        guess = self.guess_info(clean_videofile_path)
        mapping = []
        self.add_common_mapping(clean_videofile_path, guess, mapping)

        # Determine settings based solely on environment variables.
        video_type = guess.get("vtype")
        fmt, specific_mapping = self.get_video_type_map(video_type)
        if not self.dest_dir or not fmt:
            loginf(
                f"Could not determine video type for {clean_videofile_path} [from {videofile_path}]"
            )
            return None

        # Apply video type–specific mapping.
        specific_mapping(guess, mapping)

        # Determine character to use for dupe separator
        self.guess_dupe_separator(fmt)

        # Ensure that the format string ends with the extension.
        if fmt.rstrip("}")[-5:].lower() != ".%ext":
            fmt += ".%ext"

        # Canoniicalize slashes and backslashes
        fmt = fmt.replace("\\", "/")
        loginf(f"format: {fmt}")

        # Replace mapping specifiers.
        path_str = Determine.path_subst(fmt, mapping)
        logdet(f"path after subst: {path_str}")

        # Clean up the path until nothing changes.
        old_path = ""
        while old_path != path_str:
            old_path = path_str
            for key, name in Determine._REPLACE_AFTER.items():
                path_str = path_str.replace(key, name)

        # Apply case modifications.
        path_str = Determine.to_uppercase(path_str)
        path_str = Determine.to_lowercase(path_str)

        # Use pathlib to split into stem and suffix and clean the folder names.
        path_str = Determine.strip_parts_of_path_str(path_str)

        # Allow going up one level, for example if the destination directory is
        # determined based on the category or the decade
        if "%up" in path_str:
            path_str = path_str.replace("%up", "..")

        # Build the new path by joining destination directory with the relative path parts.
        videofile_dest_relative = Path(path_str)

        videofile_dest = self.dest_dir.joinpath(
            *videofile_dest_relative.parts
        ).resolve()

        logdet(
            f'construct_path: combine videofile_dest_relative="{videofile_dest_relative}" with dest_dir="{self.dest_dir}" --> videofile_dest="{videofile_dest}"'
        )

        # If the new path equals the original filename on a case-insensitive basis, do nothing.
        if videofile_path.as_posix().upper() == videofile_dest.as_posix().upper():
            loginf(
                f'construct_path: "{videofile_path}" == "{videofile_dest}": return None'
            )
            return None

        loginf(f'construct_path: "{videofile_path}" --> "{videofile_dest}"')

        # Validate the new path
        assert videofile_dest.is_absolute()
        # NOTE: The assertion of a is not valid for paths that go up one level
        if "%up" not in fmt:
            assert videofile_dest.is_relative_to(self.dest_dir)
        return videofile_dest


class deprecation_support:
    """Class implementing iterator for deprecation message support"""

    def __init__(self, mapping):
        self.iter = iter(mapping)

    def __iter__(self):
        return self

    def __next__(self):
        map_entry = next(self.iter)
        return map_entry if len(map_entry) >= 3 else list(map_entry) + [None]

    def next(self):
        return self.__next__()
