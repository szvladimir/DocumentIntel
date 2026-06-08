import fitz
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi import HTTPException
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
@app.get("/extract/{filename}")
async def extract_text(filename: str):
    filepath = UPLOAD_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    doc = fitz.open(filepath)

    text = ""
    for page_number, page in enumerate(doc, start=1):
        page_text = page.get_text()
        text += f"\n\n--- Page {page_number} ---\n"
        text += page_text

    return {
        "filename": filename,
        "pages": len(doc),
        "text_preview": text[:3000]
    }
@app.get("/summary/{filename}")
async def summarize_pdf(filename: str):
    filepath = UPLOAD_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    doc = fitz.open(filepath)

    text = ""
    for page in doc:
        text += page.get_text()

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text found in PDF")

    # пока ограничим текст, чтобы не перегружать модель
    text = text[:12000]

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You summarize documents clearly and accurately."
            },
            {
                "role": "user",
                "content": f"Сделай краткое резюме этого документа на русском языке:\n\n{text}"
            }
        ]
    )

    summary = response.choices[0].message.content

    return {
        "filename": filename,
        "summary": summary
    }    