import fitz
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi import HTTPException
import os
from openai import OpenAI
import chromadb
from pydantic import BaseModel
from app.matching import parse_document
from app import db_agent
from app.query_intent import generate_query_intent
from app.sql_builder import build_payments_query, execute_parameterized_query

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI(title="Document Intelligence Agent")

class SearchRequest(BaseModel):
    query: str

class AskDBRequest(BaseModel):
    question: str

chroma_client = chromadb.PersistentClient(
    path="data/chroma"
)

collection = chroma_client.get_or_create_collection(
    name="documents"
)
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)



def chunk_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
):
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap

    return chunks

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

@app.post("/index/{filename}")
async def index_file(filename: str):
    filepath = UPLOAD_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    doc = fitz.open(filepath)

    text = ""
    for page in doc:
        text += page.get_text()

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text found in PDF")

    chunks = chunk_text(text)

    collection.add(
        ids=[f"{filename}_{i}" for i in range(len(chunks))],
        documents=chunks,
        metadatas=[
            {"filename": filename, "chunk": i}
            for i in range(len(chunks))
        ]
    )

    return {
        "status": "indexed",
        "filename": filename,
        "chunks": len(chunks),
        "total_chunks_in_db": collection.count()
    }

@app.post("/match/{filename}")
async def match_file(filename: str):
    filepath = UPLOAD_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        result = parse_document(filepath)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {exc}")

    return {
        "filename": filename,
        "parsed": result
    }

@app.post("/search")
async def search(req: SearchRequest):
    result = collection.query(
        query_texts=[req.query],
        n_results=5
    )

    items = []

    for i, doc in enumerate(result["documents"][0]):
        items.append({
            "rank": i + 1,
            "id": result["ids"][0][i],
            "filename": result["metadatas"][0][i]["filename"],
            "distance": result["distances"][0][i],
            "text": doc
        })

    return {
        "query": req.query,
        "results": items
    }

@app.post("/ask-db")
async def ask_db(req: AskDBRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    sql = db_agent.generate_sql_from_question(question, client)
    query_result = db_agent.execute_select_query(db_agent.DEFAULT_DB_PATH, sql)
    answer = db_agent.generate_answer(question, sql, query_result["columns"], query_result["rows"], client)

    return {
        "question": question,
        "sql": sql,
        "columns": query_result["columns"],
        "rows": query_result["rows"],
        "answer": answer,
    }


@app.post("/ask-db-intent")
async def ask_db_intent(req: AskDBRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    intent = generate_query_intent(question, client)
    sql, params = build_payments_query(intent.dict(by_alias=True))
    query_result = execute_parameterized_query(db_agent.DEFAULT_DB_PATH, sql, params)

    answer = ""
    if query_result["rows"]:
        answer = db_agent.generate_answer(question, sql, query_result["columns"], query_result["rows"], client)
    else:
        answer = "No matching rows were found for that question."

    return {
        "question": question,
        "intent": intent.dict(by_alias=True),
        "sql": sql,
        "params": params,
        "rows": query_result["rows"],
        "answer": answer,
    }

@app.delete("/clear")
async def clear_collection():
    ids = collection.get()["ids"]

    if ids:
        collection.delete(ids=ids)

    return {
        "status": "cleared",
        "deleted": len(ids)
    }