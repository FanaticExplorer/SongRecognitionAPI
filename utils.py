from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
import os
from pydub import AudioSegment
import statistics
from json import load


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
        self.yt_dlp_settings = {"N": 10, 'noplaylist': True}

    @property
    def exist(self):
        exist_check_settings = {"quiet": False,
                                # 'logger': QuietLogger()
                                }
        print({**self.yt_dlp_settings, **exist_check_settings})
        with YoutubeDL({**self.yt_dlp_settings, **exist_check_settings}) as ydl:
            try:
                ydl.extract_info(self.url, download=False)
            except DownloadError:
                return False
            except Exception as e:
                print(e)
            else:
                return True

    def download(self):
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(self.output_folder, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False
        }

        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(self.url, download=True)
            title = info_dict.get('title', None)
            if title:
                audio_path = os.path.join(self.output_folder, f"{title}.mp3")
                relative_audio_path = os.path.relpath(audio_path)
                return relative_audio_path
            else:
                return None


def split_audio_to_clips(file_path, output_dir, clip_length=10000):
    """
    Splits an audio file into 10-second clips and returns their path names as a generator.

    :param file_path: Path to the input audio file.
    :param output_dir: Directory where the clips will be saved.
    :param clip_length: Length of each clip in milliseconds (default is 10000 ms).
    :return: A generator yielding the path names of the clips.
    """
    # Load the audio file
    audio = AudioSegment.from_file(file_path)
    file_name = os.path.splitext(os.path.basename(file_path))[0]

    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Get the duration of the audio in milliseconds
    duration = len(audio)

    # Initialize the start time
    start_time = 0

    while start_time < duration:
        # End time is the start time plus the length of the clip
        end_time = min(start_time + clip_length, duration)

        # Extract the clip
        clip = audio[start_time:end_time]

        # Create a filename for the clip
        clip_filename = os.path.join(output_dir, f"{file_name}_clip_{start_time // 1000}_{end_time // 1000}.mp3")

        # Export the clip to a file
        clip.export(clip_filename, format="mp3")

        # Yield the path to the clip
        yield clip_filename

        # Move to the next 10-second segment
        start_time = end_time


def get_average_id(results: list) -> int:
    ids = []
    for result in results:
        for match in result["matches"]:
            ids.append(int(match["id"]))
    return statistics.mean(ids)
