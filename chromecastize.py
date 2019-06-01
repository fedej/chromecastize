#!/usr/bin/env python3

import argparse
import sys

from pathlib import Path
from magic import Magic
from pymediainfo import MediaInfo
import ffmpeg

_SUPPORTED_EXTENSIONS = ['mkv', 'avi', 'mp4', '3gp', 'mov', 'mpg', 'mpeg', 'qt', 'wmv', 'm2ts', 'flv']
_SUPPORTED_SUBTITLE_EXTENSIONS = ['srt', 'ssa']

_SUPPORTED_GFORMATS = ['MPEG-4', 'Matroska']
_SUPPORTED_VCODECS = ['AVC']
_SUPPORTED_ACODECS = ['AAC', 'MPEG Audio', 'Vorbis', 'Ogg', 'Opus']

_DEFAULT_VCODEC='h264'
_DEFAULT_ACODEC='libvorbis'
_DEFAULT_GFORMAT='mp4'

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument("--mkv", action="store_true")
group.add_argument("--mp4", action="store_true")
parser.add_argument("--config", type=lambda p: Path(p).absolute(), default=None)
parser.add_argument("videofile", nargs='+', type=lambda p: Path(p).absolute())

def is_supported_acodec(codec, channels):
    return not (codec == "AAC" and channels > 2) and codec in _SUPPORTED_ACODECS

def mark_as_good(video_file, processed_files):
    with processed_files.open(mode='a') as f:
        f.write(str(video_file) + '\n')

def process_subtitle_file(video_file):
        destination_subtitle = video_file.with_suffix('.vtt')
        if not destination_subtitle.exists():
            generated = False
            for sub_extension in _SUPPORTED_SUBTITLE_EXTENSIONS:
                subtitle = video_file.with_suffix('.' + sub_extension)
                if subtitle.exists():
                    sub_encoding = Magic(mime_encoding=True).from_file(str(subtitle))
                    sub_encoding = "iso-8859-1" if sub_encoding == "unknown-8bit" else sub_encoding # :(
                    try:
                        ffmpeg.input(str(subtitle), sub_charenc=sub_encoding) \
                          .output(str(destination_subtitle)) \
                          .global_args('-loglevel', 'error').global_args('-y') \
                          .run()

                        print("- generated subtitle " + str(destination_subtitle))
                    except ffmpeg.Error as e:
                        print(e.stderr.decode(), file=sys.stderr)
                    break

def on_success(original_file, destination_file, processed_files):
        print("- conversion succeeded; file " + str(destination_file) + " saved")
        original_backup = original_file.with_suffix(original_file.suffix + '.bak')
        print("- renaming original file as " + str(original_backup))
        original_file.replace(original_backup)
        mark_as_good(destination_file, processed_files)

def on_failure(video_file, destination_file):
    print('- failed to convert ' + str(video_file) + ' (or conversion has been interrupted)')
    if destination_file.exists():
        print("- deleting partially converted file...")
        destination_file.unlink()

def process_file(video_file, override_gformat=None):
        print("===========")
        print("Processing: " + str(video_file))

        # test extension
        extension=video_file.suffix
        if not extension.replace('.', '') in _SUPPORTED_EXTENSIONS:
            print("- not a video format, skipping " + extension)
            return

        process_subtitle_file(video_file)
        processed_files = Path('~/.chromecastize/processed_files').expanduser()
        with processed_files.open() as f:
            for line in f:
                if str(video_file) + '\n' == line:
                    print('- file was generated by `chromecastize`, skipping')
                    return

        # test general format
        media_info = MediaInfo.parse(video_file)
        general_track = next(filter(lambda t: t.track_type == 'General', media_info.tracks))

        if not general_track.format:
            print("- error reading track info, skipping ")
            return

        if general_track.format in _SUPPORTED_GFORMATS and not override_gformat or override_gformat == extension:
            output_gformat = "ok"
        else:
            # if override format is specified, use it; otherwise fall back to default format
            output_gformat = override_gformat or _DEFAULT_GFORMAT
        print("- general: " + general_track.format + " -> " + output_gformat)

        # test video codec
        video_track = next(filter(lambda t: t.track_type == 'Video', media_info.tracks))
        output_vcodec = "copy" if video_track.format in _SUPPORTED_VCODECS else _DEFAULT_VCODEC
        print("- video: " + video_track.format + " -> " + output_vcodec)

        # test audio codec
        audio_track = next(filter(lambda t: t.track_type == 'Audio', media_info.tracks))
        output_acodec = "copy" if is_supported_acodec(audio_track.format, audio_track.channel_s) else _DEFAULT_ACODEC
        print("- audio: " + audio_track.format + " -> " + output_acodec)

        if output_vcodec == "copy" and output_acodec == "copy" and output_gformat == "ok":
            print("- file should be playable by Chromecast!")
            mark_as_good(video_file, processed_files)
        else:
            print("- video length: " + str(general_track.duration))
            output_gformat = extension if output_gformat == "ok" else output_gformat

            # Define the destination filename, stripping the original extension.
            destination_file = video_file.with_suffix('.' + output_gformat)
            try:
                ffmpeg.input(str(video_file)) \
                .output(str(destination_file), vcodec=output_vcodec, acodec=output_acodec, scodec="copy") \
                .global_args('-loglevel','error').overwrite_output() \
                .run(quiet=True)

                on_success(video_file, destination_file, processed_files)
            except ffmpeg.Error as e:
                print(e.stderr.decode(), file=sys.stderr)
                on_failure(video_file, destination_file)


def main(paths):
    for path in paths:
        if not path.exists():
            print("File not found (" + str(path) + "). Skipping...")
        elif path.is_dir():
            for video_file in path.iterdir():
                process_file(video_file)
        elif path.is_file():
                process_file(path)
        else:
            print("Invalid file (" + str(path) + "). Skipping...")

if __name__ == "__main__":
    args = parser.parse_args()
    # TODO Config
    main(args.videofile)
