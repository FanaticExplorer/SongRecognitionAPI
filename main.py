# main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from pydantic import HttpUrl
from shazamio import Shazam
import asyncio
from utils import Media, split_audio_to_clips, get_average_id, parse_music_info
import os
from loguru import logger
from sys import stderr

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
async def recognize(link: HttpUrl):
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
        raise HTTPException(status_code=404, detail="No matches found")
    # If there were matches, get the track with the average id
    result = await shazam.track_about(average_id)
    parsed_result = parse_music_info(result)
    return parsed_result


# noinspection PyUnusedLocal
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return HTTPException(
        status_code=400,
        detail="The string given is not a valid URL",
    )

# Run the app
if __name__ == "__main__":
    import uvicorn
    logger.debug("Starting FastAPI server")
    uvicorn.run(app, host="127.0.0.1", port=8000)
