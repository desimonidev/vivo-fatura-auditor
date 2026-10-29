from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import tempfile, os
from parser import extrair_mensalidades

app = FastAPI(title="Vivo Fatura API", version="0.1.0")

@app.post("/parse")
async def parse_fatura(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Envie um arquivo .pdf")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        caminho = tmp.name

    try:
        return JSONResponse(extrair_mensalidades(caminho))
    finally:
        os.unlink(caminho)