from pathlib import Path

from fastapi import FastAPI, UploadFile, File

app = FastAPI(title="Document Intelligence Agent")

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    return {"message": "Document Intelligence Agent API"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    filepath = UPLOAD_DIR / file.filename

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "filename": file.filename,
        "saved": True
    }