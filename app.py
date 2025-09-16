# app.py
import os
import io
import json
import re
import random
from typing import List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import fitz  # PyMuPDF
from PIL import Image
import pytesseract

try:
    import openai
except Exception:
    openai = None

app = FastAPI(title="MCQ Generator API")

# Allow requests from your frontend server
origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------- TEXT EXTRACTION HELPERS --------------

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = []
    for page in doc:
        txt = page.get_text()
        full_text.append(txt)
    return "\n--- Page End ---\n".join(full_text)


def extract_text_from_image_bytes(img_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    text = pytesseract.image_to_string(img)
    return text


# ----------- FALLBACK MCQ GENERATOR ----------------

def basic_fallback_mcqs(text: str, n: int = 5):
    sentences = re.split(r'(?<=[\.\?\!])\s+', text)
    candidates = [s.strip() for s in sentences if 40 <= len(s.strip()) <= 220]

    if not candidates:
        candidates = [line.strip() for line in text.splitlines() if len(line.strip()) > 30]

    chosen = candidates[:n] if candidates else [text[:200]] * n
    common_distractors = [
        'process', 'system', 'method', 'model', 'result',
        'data', 'analysis', 'function', 'energy', 'structure'
    ]

    mcqs = []
    for s in chosen:
        words = re.findall(r"\w+", s)
        candidate_words = [w for w in words if len(w) >= 4]
        if candidate_words:
            key = max(candidate_words, key=len)
        elif words:
            key = words[0]
        else:
            key = "answer"

        question = s.replace(key, "____", 1)
        options = [key]
        pool = list(dict.fromkeys(words + common_distractors))
        random.shuffle(pool)
        for w in pool:
            if len(options) >= 4:
                break
            if w.lower() != key.lower() and w not in options:
                options.append(w)
        while len(options) < 4:
            cand = random.choice(common_distractors)
            if cand not in options:
                options.append(cand)
        random.shuffle(options)
        answer_index = options.index(key)
        mcqs.append({
            "question": question,
            "options": options,
            "answer_index": answer_index
        })
    return mcqs


# ------------- MAIN ENDPOINT ----------------------

@app.post("/generate-mcqs")
async def generate_mcqs(file: UploadFile = File(...), num_questions: int = Form(5)):
    # ✅ Limit free users
    if num_questions > 15:
        return JSONResponse(
            status_code=403,
            content={
                "status": "error",
                "message": "Free users can generate up to 15 MCQs. Upgrade to premium for more.",
                "redirect": "plan.html"
            }
        )

    contents = await file.read()
    filename = (file.filename or "").lower()
    text = ""

    # Extract text
    try:
        if filename.endswith(".pdf") or file.content_type == "application/pdf":
            text = extract_text_from_pdf_bytes(contents)
        else:
            text = extract_text_from_image_bytes(contents)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Text extraction failed: {e}")

    # Trim long text for model
    MAX_CHARS = 4000
    text_for_model = text if len(text) <= MAX_CHARS else text[:MAX_CHARS]

    # If OPENAI key available → use GPT, else fallback
    OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
    if OPENAI_KEY and openai is not None:
        openai.api_key = OPENAI_KEY
        prompt = f"""
You are an MCQ generator. From the following text produce {num_questions} multiple-choice questions.
Return **only valid JSON**: a JSON array where each item has keys:
  - question: string
  - options: array of 4 strings
  - answer_index: integer (0-3) indicating the correct option position

Text:
\"\"\"{text_for_model}\"\"\"
"""
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates MCQs in JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=900,
            )
            raw = resp["choices"][0]["message"]["content"].strip()
            start = raw.find("[")
            if start != -1:
                json_text = raw[start:]
            else:
                json_text = raw
            mcqs = json.loads(json_text)
            return JSONResponse({"status": "ok", "source": "openai", "mcqs": mcqs})
        except Exception as e:
            mcqs = basic_fallback_mcqs(text, num_questions)
            return JSONResponse({
                "status": "partial",
                "error": str(e),
                "source": "fallback",
                "mcqs": mcqs
            })
    else:
        mcqs = basic_fallback_mcqs(text, num_questions)
        return JSONResponse({"status": "fallback_no_key", "source": "fallback", "mcqs": mcqs})
