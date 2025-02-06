import os
from pathlib import Path
import shutil
from options import Options
from determine import Determine
from nzbget_utils import logdet, loginf, logwar, logerr
import traceback
import difflib

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import guessit


class Apply:
    PREVIEW_PREFIX = "[PREVIEW] "

    def __init__(self, options: Options = None):
        self.options = options and options or Options()

        if not self.options.preview:
            Apply.PREVIEW_PREFIX = ""

        # Indicate if any errors occurred that should prohibit `cleanup`
        self.errors = False

        # Indicate if any files have been moved and NZB needs to be notified
        self.files_moved = False

        # List of moved files (source path)
        self.moved_src_files = []
        # List of moved files (destination path)
        self.moved_dst_files = []

    def unique_name(self, dst_path: Path) -> Path:
        """Adds unique numeric suffix to destination file name to avoid overwriting
        such as "filename.(2).ext", "filename.(3).ext", etc.
        If an existing file was created by the script it is renamed to "filename.(1).ext".
        """
        parent = dst_path.parent
        stem = dst_path.stem
        suffix = dst_path.suffix
        suffix_num = 2
        while True:
            unique_path = (
                parent / f"{stem}{self.determine.dupe_separator}({suffix_num}){suffix}"
            )
            if not unique_path.exists() and unique_path not in self.moved_dst_files:
                break
            suffix_num += 1
        return unique_path

    def _move_file_impl(self, src_file: Path, dst_file: Path):
        try:
            if not self.options.preview:
                # Create the path to the destination file
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                src_file.rename(dst_file)
            logdet(
                f'{Apply.PREVIEW_PREFIX}_move_file_impl:  "{src_file}".rename("{dst_file}") OK'
            )
        except OSError as ex:
            logdet(f"_move_file_impl: rename failed;use shutil.copyfile ({ex})")
            if not self.options.preview:
                shutil.copyfile(src_file, dst_file)
            logdet(
                f'{Apply.PREVIEW_PREFIX}_move_file_impl: shutil.copyfile("{src_file}", "{dst_file}") OK'
            )
            if not self.options.preview:
                src_file.unlink()
            logdet(f'{Apply.PREVIEW_PREFIX}_move_file_impl: "{src_file}".unlink() OK')

    def move_file(self, src_file, dest_file):
        """Moves the file to its sorted location.
        It creates directories to `dst_path` and moves the file from `src_path` there.
        """
        # Ensure the arguments are `Path` objects
        if not isinstance(src_file, Path):
            src_file = Path(src_file)
        if not isinstance(dest_file, Path):
            dest_file = Path(dest_file)

        assert src_file.is_file()

        if dest_file.exists() or dest_file in self.moved_dst_files:
            assert dest_file.is_file()
            if self.options.overwrite and dest_file not in self.moved_dst_files:
                # Overwrite existing file
                loginf(
                    f'move_file: overwrite={self.options.overwrite} and "{dest_file}" not in {self.moved_dst_files}'
                )
                if not self.options.preview:
                    dest_file.unlink()
                loginf(f'{Apply.PREVIEW_PREFIX}move_file: "{dest_file}".unlink() OK')
                self._move_file_impl(src_file, dest_file)
            else:
                # Cannot overwrite existing file because either overwrite is disabled or
                # the destination file was created by the script.
                # Rename to a unique filename instead
                dest_file = self.unique_name(dest_file)
                loginf(
                    f'move_file: overwrite={self.options.overwrite}: resursively call move_file("{src_file}", "{dest_file}")'
                )
                self.move_file(src_file, dest_file)
        else:
            # Destination file does not exist and is not in the list of moved files
            self._move_file_impl(src_file, dest_file)
            loginf(f'move_file: _move_file_impl("{src_file}", "{dest_file})" OK')
        self.moved_src_files.append(src_file)
        self.moved_dst_files.append(dest_file)
        logdet(f"move_file: file at dst_path is {Apply._file_size_human(dest_file)}")
        logdet(f"move_file: returning {dest_file}")
        return dest_file

    def move_satellites(self, src_file: Path, dest_file: Path):
        """Moves satellite files such as subtitles that are associated with the base video
        and stored in the video's directory (or subdirectories) to the correct destination.
        """
        loginf(f'move_satellites("{src_file}", "{dest_file}")')

        # Define the source and destination directories.
        src_dir = src_file.parent
        dest_dir = dest_file.parent

        # Assert that both directories exist to ensure we're working with valid directories.
        assert src_dir.is_dir()
        assert dest_dir.is_dir()

        # The base for satellite files: the video filename without its extension.
        base = src_file.with_suffix("").name

        # Iterate recursively over all files under the source video's directory.
        for sat_file in src_dir.rglob("*"):
            if not sat_file.is_file():
                continue

            filename = sat_file.name
            file_stem = sat_file.stem
            fext = sat_file.suffix
            fextlo = fext.lower()

            if fextlo in self.options._SATELLITE_EXTENSIONS:
                subpart = ""
                if fextlo[1:] in self.options._SATELLITE_EXTENSIONS:
                    guess = guessit.guessit(filename)
                    if guess and "subtitle_language" in guess:
                        # Remove the last dot and subsequent characters from the file stem.
                        idx = file_stem.rfind(".")
                        if idx != -1:
                            file_stem = file_stem[:idx]
                        # Use alpha2 subtitle language (e.g. en, es) from GuessIt.
                        subpart = "." + guess["subtitle_language"].alpha2

                    if subpart:
                        loginf(
                            "Satellite: %s is a subtitle [%s]"
                            % (filename, guess["subtitle_language"])
                        )
                    else:
                        loginf("Satellite: %s is a subtitle" % filename)

                elif (file_stem.lower() != base.lower()) and fextlo == ".nfo":
                    if self.options.deep_scan:
                        guess = self.deep_scan_nfo(str(sat_file))
                        if guess is not None:
                            file_stem = base

                if file_stem.lower() == base.lower():
                    # Build the new satellite file name using the destination video's stem.
                    new_sat = dest_dir / f"{dest_file.stem}{subpart}{fext}"
                    loginf("Satellite: %s" % new_sat.name)
                    self.move_file(sat_file, new_sat)

    def deep_scan_nfo(self, filename, ratio=None):
        if ratio is None:
            ratio = self.options.deep_scan_ratio
        loginf("Deep scanning satellite: %s (ratio=%.2f)" % (filename, ratio))
        best_guess = None
        best_ratio = 0.00
        try:
            nfo = open(filename)
            # Convert file content into iterable words
            for word in "".join([item for item in nfo.readlines()]).split():
                try:
                    guess = guessit.guessit(word + ".nfo")
                    # Series = TV, Title = Movie
                    if any(item in guess for item in ("title")):
                        # Compare word against NZB name
                        diff = difflib.SequenceMatcher(
                            None, word, self.options.nzb_name
                        )
                        # Evaluate ratio against threshold and previous matches
                        loginf("Tested: %s (ratio=%.2f)" % (word, diff.ratio()))
                        if diff.ratio() >= ratio and diff.ratio() > best_ratio:
                            loginf(
                                "Possible match found: %s (ratio=%.2f)"
                                % (word, diff.ratio())
                            )
                            best_guess = guess
                            best_ratio = diff.ratio()
                except UnicodeDecodeError:
                    # Ignore non-unicode words (common in nfo "artwork")
                    pass
            nfo.close()
        except IOError as e:
            logerr("%s" % str(e))
        return best_guess

    def cleanup_download_dir(self):
        """Remove the download directory if it (or any subfolder) does not contain
        "important" files (important = size >= min_size).
        """
        download_dir = Path(self.options.download_dir)
        loginf(f'cleanup_download_dir("{download_dir}")')

        # Check if there are any big files remaining
        keep_download_dir = False
        for path in download_dir.rglob("*"):
            if path.is_file():
                if path in self.moved_dst_files:
                    keep_download_dir = True
                    continue
                if path.stat().st_size >= self.options.min_size and (
                    not self.options.preview or (path not in self.moved_src_files)
                ):
                    logwar(
                        "Skipping clean up due to large files remaining in the directory"
                    )
                    return

        # Now delete all files with nice logging.
        for path in list(download_dir.rglob("*")):
            if path.is_file():
                if path in self.moved_dst_files:
                    continue
                if not self.options.preview or (path not in self.moved_src_files):
                    if not self.options.preview:
                        path.unlink()
                    loginf(f'Deleted: "{path}"')

        # Delete the download directory if no moved destination files exist.
        if not keep_download_dir:
            if not self.options.preview:
                shutil.rmtree(download_dir)
            loginf(f'Deleted: "{download_dir}"')

    @staticmethod
    def _file_size_human(file_path):
        """Converts file size to human readable format"""
        size = file_path.stat().st_size
        for unit in ["B", "kB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.2f}{unit}"
            size /= 1024.0
        return f"{size:.2f}PB"

    @staticmethod
    def _describe_file(file_path):
        """Returns a string describing the file at the given path"""
        return f'"{str(file_path)}[{Apply._file_size_human(file_path)}]"'

    def apply(self):
        # Process all the files in download_dir and its subdirectories
        video_files = []

        for root, dirs, downloaded_files in os.walk(self.options.download_dir):
            for downloaded_file in downloaded_files:
                try:
                    downloaded_file_path = Path(root) / downloaded_file

                    # Check extension
                    if (
                        downloaded_file_path.suffix.lower().lstrip(".")
                        not in self.options._VIDEO_EXTENSIONS
                    ):
                        continue

                    # Check minimum file size
                    downloaded_file_size = downloaded_file_path.stat().st_size
                    if downloaded_file_size < self.options.min_size:
                        loginf(
                            f'Skipping "{str(downloaded_file)}" as its size={downloaded_file_size} < {self.options.min_size}'
                        )
                        continue

                    # This is our video file, we should process it
                    video_files.append(downloaded_file_path)

                except Exception as e:
                    self.errors = True
                    logerr("Failed: %s" % downloaded_file)
                    logerr("Exception: %s" % e)
                    traceback.print_exc()

        determine = Determine(video_files, self.options)

        for video_file_path in video_files:
            try:
                dest = determine.construct_path(str(video_file_path))

                if dest:
                    dest_file = Path(dest)
                    # Move video file
                    self.move_file(video_file_path, dest_file)
                    self.files_moved = True

                    if self.files_moved and self.options.satellites:
                        # Move satellite files
                        self.move_satellites(video_file_path, dest_file)

            except Exception as e:
                self.errors = True
                logerr(f'Exception when renaming video file "{video_file_path}": {e}')
                logerr(traceback.format_exc())

        # Inform NZBGet about new destination path
        finaldir = ""
        uniquedirs = []
        for filename in self.moved_dst_files:
            dir = os.path.dirname(filename)
            if dir not in uniquedirs:
                uniquedirs.append(dir)
                finaldir += "|" if finaldir != "" else ""
                finaldir += dir

        if finaldir != "":
            # Ensure that this is output without a prefix like `INFO` or `WARNING`
            # so that NZBGet can parse this output correctly based on the prefix
            print("[NZB] FINALDIR=%s" % finaldir)

        # Cleanup if:
        # 1) files were moved AND
        # 2) no errors happen AND
        # 3) all remaining files are smaller than <MinSize>
        if self.options.cleanup and self.files_moved and not self.errors:
            self.cleanup_download_dir()
