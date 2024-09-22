from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from pydantic import HttpUrl
from shazamio import Shazam
import asyncio
from utils import Media, split_audio_to_clips, get_average_id
import os

# FastAPI app
app = FastAPI()


# Initialize the Shazam object
shazam = Shazam()
loop = asyncio.get_event_loop()


@app.get("/", response_class=RedirectResponse, include_in_schema=False)
def read_root():
    return "/docs"


# Endpoint to recognize a link
@app.get("/recognize/link")
async def recognize(link: HttpUrl):
    media = Media(link)
    if not media.exist:
        return HTTPException(status_code=404, detail="No video is given in the link", )
    audio_file = media.download()
    results = []
    for clip in split_audio_to_clips(audio_file, "clips"):
        clip_result = await shazam.recognize(audio_file)
        results.append(clip_result)
        os.remove(clip)
    os.remove(audio_file)
    average_id = get_average_id(results)
    return await shazam.track_about(average_id)


# noinspection PyUnusedLocal
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return HTTPException(status_code=400, detail="The string given is not a valid URL", )

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
