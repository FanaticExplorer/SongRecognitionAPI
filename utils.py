# utils.py
import yt_dlp
import os
from pydub import AudioSegment
import statistics
import asyncio
from functools import lru_cache
import uuid
import io
from json import dump


class QuietLogger:
    @staticmethod
    def error(msg):
        if "Unsupported URL:" not in msg:
            print(msg)

    @staticmethod
    def warning(msg):
        pass

    @staticmethod
    def debug(msg):
        pass


class Media:
    def __init__(self, url):
        self.url = url
        self.output_folder = "audio"
        self.yt_dlp_settings = {"N": 10, "noplaylist": True}
        self.unique_filename = f"{uuid.uuid4()}"

    @property
    async def exist(self):
        exist_check_settings = {"quiet": True}
        combined_settings = {**self.yt_dlp_settings, **exist_check_settings}

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._check_exist, combined_settings
            )
            return True
        except yt_dlp.DownloadError:
            return False
        except Exception as e:
            print(f"Error checking existence: {e}")
            return False

    def _check_exist(self, settings):
        with yt_dlp.YoutubeDL(settings) as ydl:
            ydl.extract_info(self.url, download=False)

    @lru_cache(maxsize=100)
    def _get_ydl_opts(self):
        return {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(
                self.output_folder, f"{self.unique_filename}.%(ext)s"
            ),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
        }

    async def download(self):
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        ydl_opts = self._get_ydl_opts()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download_audio, ydl_opts)

        audio_path = os.path.join(
            self.output_folder, f"{self.unique_filename}.mp3"
        )  # Use .mp3 here
        relative_audio_path = os.path.relpath(audio_path)
        return relative_audio_path

    def _download_audio(self, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(self.url)


def split_audio_to_clips(file_path, clip_length=10000):
    """
    Splits an audio file into 10-second clips and yields them as bytes.

    :param file_path: Path to the input audio file.
    :param clip_length: Length of each clip in milliseconds (default is 10000 ms).
    :return: A generator yielding the audio clips as bytes.
    """
    # Load the audio file
    audio = AudioSegment.from_file(file_path)

    # Get the duration of the audio in milliseconds
    duration = len(audio)

    # Initialize the start time
    start_time = 0

    while start_time < duration:
        # End time is the start time plus the length of the clip
        end_time = min(start_time + clip_length, duration)

        # Extract the clip
        clip = audio[start_time:end_time]

        # Create a BytesIO object to hold the clip bytes
        clip_bytes_io = io.BytesIO()

        # Export the clip to the BytesIO object
        clip.export(clip_bytes_io, format="mp3")

        # Get the bytes from the BytesIO object
        clip_bytes = clip_bytes_io.getvalue()

        # Yield the bytes of the clip
        yield clip_bytes

        # Move to the next 10-second segment
        start_time = end_time


def get_average_id(results: list) -> int | None:
    ids = []
    for result in results:
        for match in result["matches"]:
            ids.append(int(match["id"]))
    print(ids)
    if len(ids) == 0:
        return None
    return statistics.mean(ids)
