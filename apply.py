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
            unique_path = parent / f"{stem}{self.options.dupe_separator}({suffix_num}){suffix}"
            if not unique_path.exists() and unique_path not in self.moved_dst_files:
                break
            suffix_num += 1
        return unique_path

    def optimized_move(self, src_path: Path, dst_path: Path):
        try:
            if not self.options.preview:
                # Create the path to the destination file
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                src_path.rename(dst_path)
            logdet(
                f'{Apply.PREVIEW_PREFIX}optimized_move:  "{src_path}".rename("{dst_path}") OK'
            )
        except OSError as ex:
            logdet(f"optimized_move: os.rename failed ({ex})")
            if not self.options.preview:
                shutil.copyfile(src_path, dst_path)
            logdet(
                f'{Apply.PREVIEW_PREFIX}optimized_move: shutil.copyfile("{src_path}", "{dst_path}") OK'
            )
            if not self.options.preview:
                src_path.unlink()
            logdet(f'{Apply.PREVIEW_PREFIX}optimized_move: "{src_path}".unlink() OK')

    def rename(self, src_path, dst_path):
        """Moves the file to its sorted location.
        It creates directories to `dst_path` and moves the file from `src_path` there.
        """
        # Ensure the arguments are `Path` objects
        if not isinstance(src_path, Path):
            src_path = Path(src_path)
        if not isinstance(dst_path, Path):
            dst_path = Path(dst_path)

        if dst_path.exists() or dst_path in self.moved_dst_files:
            if self.options.overwrite and dst_path not in self.moved_dst_files:
                # Overwrite existing file
                loginf(
                    f'rename: overwrite={self.options.overwrite} and "{dst_path}" not in {self.moved_dst_files}'
                )
                if not self.options.preview:
                    dst_path.unlink()
                loginf(f'{Apply.PREVIEW_PREFIX}rename: "{dst_path}".unlink() OK')
                self.optimized_move(src_path, dst_path)
            else:
                # Cannot overwrite existing file because either overwrite is disabled or
                # the destination file was created by the script.
                # Rename to a unique filename instead
                dst_path = self.unique_name(dst_path)
                loginf(
                    f'rename: overwrite={self.options.overwrite}: resursively call rename("{src_path}", "{dst_path}")'
                )
                self.rename(src_path, dst_path)
        else:
            # Destination file does not exist and is not in the list of moved files
            self.optimized_move(src_path, dst_path)
            loginf(f'rename: optimized_move("{src_path}", "{dst_path})" OK')
        self.moved_src_files.append(src_path)
        self.moved_dst_files.append(dst_path)
        logdet(f"rename: file at dst_path is {Apply._file_size_human(dst_path)}")
        logdet(f"rename: returning {dst_path}")
        return dst_path

    def move_satellites(self, videofile, dest):
        """Moves satellite files such as subtitles that are associated with base
        and stored in root to the correct dest.
        """
        loginf(f'move_satellites("{videofile}", "{dest}")')

        root = os.path.dirname(videofile)
        destbasenm = os.path.splitext(dest)[0]
        base = os.path.basename(os.path.splitext(videofile)[0])
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                fbase, fext = os.path.splitext(filename)
                fextlo = fext.lower()
                fpath = os.path.join(dirpath, filename)

                if fextlo in self.options._SATELLITE_EXTENSIONS:
                    # Handle subtitles and nfo files
                    subpart = ""
                    # We support GuessIt supported subtitle extensions
                    if fextlo[1:] in self.options._SATELLITE_EXTENSIONS:
                        guess = guessit.guessit(filename)
                        if guess and "subtitle_language" in guess:
                            fbase = fbase[: fbase.rfind(".")]
                            # Use alpha2 subtitle language from GuessIt (en, es, de, etc.)
                            subpart = "." + guess["subtitle_language"].alpha2

                        if subpart != "":
                            loginf(
                                "Satellite: %s is a subtitle [%s]"
                                % (filename, guess["subtitle_language"])
                            )
                        else:
                            # English (or undetermined)
                            loginf("Satellite: %s is a subtitle" % filename)

                    elif (fbase.lower() != base.lower()) and fextlo == ".nfo":
                        # Aggressive match attempt
                        if self.options.deep_scan:
                            guess = self.deep_scan_nfo(fpath)
                            if guess is not None:
                                # Guess details are not important, just that there was a match
                                fbase = base
                    if fbase.lower() == base.lower():
                        old = fpath
                        new = destbasenm + subpart + fext
                        loginf("Satellite: %s" % os.path.basename(new))
                        self.rename(old, new)

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
        """Remove the download directory if it (or any subfodler) does not contain "important" files
        (important = size >= min_size)
        """
        loginf(f'cleanup_download_dir("{self.options.download_dir}")')

        # Check if there are any big files remaining
        keep_download_dir = False
        for root, dirs, files in os.walk(self.options.download_dir):
            for filename in files:
                path = Path(root) / filename
                if path in self.moved_dst_files:
                    keep_download_dir = True
                    continue
                # Check minimum file size
                if os.path.getsize(path) >= self.options.min_size and (
                    not self.options.preview or (path not in self.moved_src_files)
                ):
                    logwar(
                        "Skipping clean up due to large files remaining in the directory"
                    )
                    return

        # Now delete all files with nice logging
        for root, dirs, files in os.walk(self.options.download_dir):
            for filename in files:
                path = Path(root) / filename
                if path in self.moved_dst_files:
                    continue
                if not self.options.preview or path not in self.moved_src_files:
                    if not self.options.preview:
                        path.unlink()
                    loginf("Deleted: %s" % path)
        if not keep_download_dir:
            if not self.options.preview:
                shutil.rmtree(self.options.download_dir)
            loginf("Deleted: %s" % self.options.download_dir)

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

        # Determine whether we can use the NZB name for the destination path
        # Note: The value of self.options.use_nzb_name is used in the `Determine` class
        self.options.use_nzb_name = (
            self.options.prefer_nzb_name and len(video_files) == 1
        )

        determine = Determine(self.options)

        for video_file_path in video_files:
            try:
                dest = determine.construct_path(str(video_file_path))

                if dest:
                    dest_path = Path(dest)
                    # Move video file
                    self.rename(video_file_path, dest_path)
                    self.files_moved = True

                    if self.files_moved and self.options.satellites:
                        # Move satellite files
                        self.move_satellites(video_file_path, dest_path)

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
