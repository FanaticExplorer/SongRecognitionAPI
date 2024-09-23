from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from pydantic import HttpUrl
from shazamio import Shazam
import asyncio
from utils import Media, split_audio_to_clips, get_average_id
import os
from time import time
from loguru import logger

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
@logger.catch()
async def recognize(link: HttpUrl):
    start = time()
    media = Media(link)
    if not await media.exist:
        raise HTTPException(status_code=404, detail="No video is given in the link")
    audio_file = await media.download()
    results = []
    for clip in split_audio_to_clips(audio_file):
        try:
            clip_result = await shazam.recognize(audio_file)
        except Exception as e:
            print(f"{type(e)}: {e}")
        else:
            results.append(clip_result)
        finally:
            try:
                os.remove(clip)
            except ValueError:
                pass
    os.remove(audio_file)
    print(results)
    average_id = get_average_id(results)
    if average_id is None:
        return HTTPException(status_code=404, detail="No matches found")
    result = await shazam.track_about(average_id)
    print(f"Time taken: {time() - start}")
    return result


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

    uvicorn.run(app, host="127.0.0.1", port=8000)
