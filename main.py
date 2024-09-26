from fastapi import FastAPI, Request, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import HttpUrl
from utils import Media, DirectMedia, process_audio
import os
from loguru import logger
from sys import stderr
import uuid
import asyncio
from tempfile import NamedTemporaryFile
from contextlib import asynccontextmanager
import filetype
import subprocess

# Configure Loguru
logger.configure(handlers=[{"sink": stderr, "level": "INFO"}])
logger.add("logs/{time:YYYY-MM-DD}.log", rotation="00:00", level="DEBUG")

ALLOWED_CONTENT_TYPES = [
    "audio/mpeg",  # MP3
    "audio/wav",  # WAV
    "video/mp4",  # MP4
    "video/avi",  # AVI
]


@asynccontextmanager
async def lifespan(api_app: FastAPI):
    os.makedirs("user_files", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    print("Folders initialized")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("Event loop initialized")
    yield
    print("Bye!")


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=RedirectResponse, include_in_schema=False)
def read_root():
    return "/docs"


# Utility function for async ffmpeg execution
async def convert_to_mp3(input_file: str, output_file: str):
    await asyncio.to_thread(
        subprocess.run,
        [
            "ffmpeg",
            "-i", input_file,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-filter:a", "aresample=async=1",
            "-y", output_file
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


# Endpoint to recognize a link
@app.get("/recognize/link", tags=["Recognition"], summary="Process media from a link")
@logger.catch()
async def recognize_link(link: HttpUrl):
    media = Media(link)
    if not await media.exist:
        return HTTPException(status_code=404, detail="No video is given in the link")
    audio_file = await media.download()

    parsed_result = await process_audio(audio_file)

    return parsed_result


@app.post(
    "/recognize/file",
    tags=["Recognition"],
    summary="Upload a media file for recognition",
)
@logger.catch()
async def recognize_file(file: UploadFile = File(...)):
    """
    Upload an audio or video file to extract and process its audio content.
    """
    # Use filetype library to check the actual file type
    file_data = await file.read(1024)  # Read first 1024 bytes
    kind = filetype.guess(file_data)
    file.file.seek(0)  # Reset file pointer after reading

    if kind is None or (not kind.mime.startswith("audio") and not kind.mime.startswith("video")):
        return HTTPException(
            status_code=400,
            detail=f"Invalid file type: {kind.mime if kind else 'Unknown'}",
        )

    # Use a temporary file to save the uploaded file
    with NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(await file.read())
        temp_file.flush()
        temp_file_name = temp_file.name

    # Generate output filename for the mp3
    audio_file = f"audio/{uuid.uuid4()}.mp3"

    # Convert file asynchronously using ffmpeg
    await convert_to_mp3(temp_file_name, audio_file)

    # Remove the temporary original file
    os.remove(temp_file_name)

    # Process the audio and return the result
    parsed_result = await process_audio(audio_file)
    return parsed_result


@app.get(
    "/recognize/direct_link",
    tags=["Recognition"],
    summary="Process media from the direct link",
)
@logger.catch()
async def recognize_direct_link(link: HttpUrl):
    media = DirectMedia(link)
    if not await media.exist:
        return HTTPException(
            status_code=404, detail="No video/audio is given in the link"
        )

    # Use a temporary file for the download
    original_filename = f"user_files/{uuid.uuid4()}.{media.extension}"
    await media.download(original_filename)

    # Generate output filename for the mp3
    audio_file = f"audio/{uuid.uuid4()}.mp3"

    # Convert file asynchronously using ffmpeg
    await convert_to_mp3(original_filename, audio_file)

    # Remove the original downloaded file
    os.remove(original_filename)

    parsed_result = await process_audio(audio_file)
    return parsed_result


# Custom exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(status_code=400, content={"detail": "Invalid input"})


# Custom exception handler for generic exceptions
@app.exception_handler(Exception)
async def any_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Unexpected error occurred: {type(exc).__name__}"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
