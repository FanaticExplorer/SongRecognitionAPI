# main.py
from fastapi import FastAPI, Request, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from pydantic import HttpUrl
from shazamio import Shazam
import asyncio
from utils import Media, split_audio_to_clips, get_average_id, parse_music_info, DirectMedia
import os
from loguru import logger
from sys import stderr
import uuid
import subprocess

# FastAPI app
app = FastAPI()

# Initialize the Shazam object
shazam = Shazam()
loop = asyncio.get_event_loop()

# Configure Loguru
logger.configure(handlers=[{"sink": stderr, "level": "INFO"}])
logger.add("logs/{time:YYYY-MM-DD}.log", rotation="00:00", level="DEBUG")


@app.get("/", response_class=RedirectResponse, include_in_schema=False)
def read_root():
    return "/docs"


# Endpoint to recognize a link
@app.get("/recognize/link")
@logger.catch()
async def recognize_link(link: HttpUrl):
    media = Media(link)
    if not await media.exist:
        raise HTTPException(status_code=404, detail="No video is given in the link")
    audio_file = await media.download()
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


ALLOWED_CONTENT_TYPES = [
    "audio/mpeg",  # MP3
    "audio/wav",  # WAV
    "video/mp4",  # MP4
    "video/avi",  # AVI
]


@app.post("/recognize/file")
@logger.catch()
async def recognize_file(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        return HTTPException(status_code=400, detail="Invalid file type")

    os.makedirs("user_files", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    # Save original file
    original_filename = f"user_files/{uuid.uuid4()}{os.path.splitext(file.filename)[1]}"
    with open(original_filename, "wb") as f:
        f.write(file.file.read())

    # Generate output filename
    audio_file = f"audio/{uuid.uuid4()}.mp3"

    # Convert to MP3 using ffmpeg
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            original_filename,
            "-vn",  # Disable video processing
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-filter:a",
            "aresample=async=1",
            "-y",
            audio_file,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    # Remove original file
    os.remove(original_filename)

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

    result = await shazam.track_about(average_id)
    parsed_result = parse_music_info(result)
    return parsed_result


@app.post("/recognize/direct_link")
@logger.catch()
async def recognize_direct_link(link: HttpUrl):
    media = DirectMedia(link)
    if not await media.exist:
        return HTTPException(status_code=404, detail="No video/audio is given in the link")

    os.makedirs("user_files", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    # Save original file
    original_filename = f"user_files/{uuid.uuid4()}.{media.extension}"
    await media.download(original_filename)

    # Generate output filename
    audio_file = f"audio/{uuid.uuid4()}.mp3"

    # Convert to MP3 using ffmpeg
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            original_filename,
            "-vn",  # Disable video processing
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-filter:a",
            "aresample=async=1",
            "-y",
            audio_file,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    # Remove original file
    os.remove(original_filename)

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

    result = await shazam.track_about(average_id)
    parsed_result = parse_music_info(result)
    return parsed_result


# noinspection PyUnusedLocal
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return HTTPException(
        status_code=400,
        detail="Invalid input",
    )


# noinspection PyUnusedLocal
@app.exception_handler(Exception)
async def any_exception_handler(request: Request, exc: Exception):
    return HTTPException(
        status_code=500,
        detail=f"Unexpected error: {type(exc)}: {exc}",
    )


# Run the app
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
