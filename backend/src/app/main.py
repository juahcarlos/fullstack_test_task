from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.exceptions import EmptyFileError, FileNotFoundInStorageError
from app.api.router import api_router




app = FastAPI()

@app.exception_handler(FileNotFoundInStorageError)
async def file_not_found_handler(request: Request, exc: FileNotFoundInStorageError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(EmptyFileError)
async def empty_file_handler(request: Request, exc: EmptyFileError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)