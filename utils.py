# utils.py
import yt_dlp
import os
from pydub import AudioSegment
import statistics
import asyncio
from functools import lru_cache, wraps
import uuid
import io
from loguru import logger
import aiohttp
from fastapi import HTTPException
import sys

from shazamio import Shazam

shazam = Shazam()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class QuietLogger:
    @staticmethod
    def error(msg):
        if "Unsupported URL:" not in msg:
            logger.error(msg)

    @staticmethod
    def warning(msg):
        logger.warning(msg)

    @staticmethod
    def debug(msg):
        logger.debug(msg)


def retry(retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in {func.__name__}: {type(e)}: {e}")
                    attempt += 1
                    if attempt == retries:
                        raise
                    await asyncio.sleep(delay * (backoff ** (attempt - 1)))

        return wrapper

    return decorator


class Media:
    def __init__(self, url):
        self.url = url
        self.output_folder = "audio"
        self.yt_dlp_settings = {"N": 10, "noplaylist": True}
        self.unique_filename = f"{uuid.uuid4()}"

    @property
    @retry(retries=3, delay=1, backoff=2)
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

    @retry(retries=3, delay=1, backoff=2)
    async def download(self):
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        ydl_opts = self._get_ydl_opts()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download_audio, ydl_opts)

        audio_path = os.path.join(self.output_folder, f"{self.unique_filename}.mp3")
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
    if len(ids) == 0:
        return None
    return statistics.mean(ids)


def parse_music_info(data):
    def get_metadata_value(metadata_list, title):
        return next(
            (item.get("text") for item in metadata_list if item.get("title") == title),
            None,
        )

    parsed_info = {
        "title": data.get("title"),
        "subtitle": data.get("subtitle"),
        "artist": data.get("artists")[0].get("alias") if data.get("artists") else None,
        "album": get_metadata_value(
            data.get("sections", [])[0].get("metadata", []), "Album"
        ),
        "label": get_metadata_value(
            data.get("sections", [])[0].get("metadata", []), "Label"
        ),
        "released": get_metadata_value(
            data.get("sections", [])[0].get("metadata", []), "Released"
        ),
        "genre": data.get("genres", {}).get("primary"),
        "coverart": data.get("images", {}).get("coverart"),
        "apple_music_url": next(
            (
                option.get("actions")[0].get("uri")
                for option in data.get("hub", {}).get("options", [])
                if option.get("actions")
            ),
            None,
        ),
        "youtube_music_url": next(
            (
                provider.get("actions")[0].get("uri")
                for provider in data.get("hub", {}).get("providers", [])
                if provider.get("type") == "YOUTUBEMUSIC"
            ),
            None,
        ),
        "shazam_url": data.get("url"),
    }
    return parsed_info


class DirectMedia:
    def __init__(self, url):
        self.url = url
        self.sem = asyncio.Semaphore(30)
        self.extension = None

    @property
    async def exist(self) -> bool:
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.head(self.url, allow_redirects=True) as response:
                content_type = response.headers.get("Content-Type")
                return content_type.startswith("video") or content_type.startswith("audio")

    async def download(self, path):
        async with self.sem:
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                async with session.get(self.url) as response:
                    with open(path, "wb") as fd:
                        async for chunk in response.content.iter_chunked(1024):
                            # noinspection PyTypeChecker
                            fd.write(chunk)


async def process_audio(audio_file):
    results = []
    for clip in split_audio_to_clips(audio_file):
        try:
            # Try to recognize the clip
            clip_result = await shazam.recognize(clip)
        except Exception as e:
            # If there was an error, log the error and continue
            logger.error(f"Error recognizing clip: {type(e)}: {e}")
        else:
            # If the recognition was successful, add the result to the list
            results.append(clip_result)
    # Remove the original audio file
    os.remove(audio_file)
    average_id = get_average_id(results)
    if average_id is None:
        # If no matches were found, return a 404
        return HTTPException(status_code=404, detail="No matches found")
    # If there were matches, get the track with the average id
    result = await shazam.track_about(average_id)
    parsed_result = parse_music_info(result)

    return parsed_result


