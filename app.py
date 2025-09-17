# app.py
import os, io, json, re, random, sqlite3
from datetime import datetime, timedelta

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

import fitz
from PIL import Image
import pytesseract

# ---------- CONFIG ----------
SECRET_KEY = "supersecretkey"   # change in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ---------- DB INIT ----------
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    usage_count INTEGER DEFAULT 0
)""")
conn.commit()

# ---------- FASTAPI APP ----------
app = FastAPI(title="MCQ Generator with Login")

origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- HELPERS ----------
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------- AUTH ROUTES ----------
@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    hashed = get_password_hash(password)
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        conn.commit()
        return {"msg": "User registered successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    cursor.execute("SELECT password FROM users WHERE username=?", (form_data.username,))
    row = cursor.fetchone()
    if not row or not verify_password(form_data.password, row[0]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": form_data.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

# ---------- MCQ GENERATION ----------
def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join([p.get_text() for p in doc])

def extract_text_from_image_bytes(img_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return pytesseract.image_to_string(img)

def basic_fallback_mcqs(text: str, n: int = 5):
    sentences = re.split(r'(?<=[\.\?\!])\s+', text)
    candidates = [s.strip() for s in sentences if 40 <= len(s.strip()) <= 220]
    chosen = candidates[:n] if candidates else [text[:200]] * n
    mcqs = []
    for s in chosen:
        words = re.findall(r"\w+", s)
        key = words[0] if words else "answer"
        q = s.replace(key, "____", 1)
        options = [key] + random.sample(words, min(3, len(words)))
        while len(options) < 4:
            options.append("dummy")
        random.shuffle(options)
        mcqs.append({"question": q, "options": options, "answer_index": options.index(key)})
    return mcqs

@app.post("/generate-mcqs")
async def generate_mcqs(file: UploadFile = File(...), num_questions: int = Form(5), username: str = Depends(get_current_user)):
    # check usage
    cursor.execute("SELECT usage_count FROM users WHERE username=?", (username,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    usage_count = row[0]
    if usage_count >= 15:
        raise HTTPException(status_code=403, detail="Free limit reached. Upgrade to premium.")

    contents = await file.read()
    if file.filename.lower().endswith(".pdf"):
        text = extract_text_from_pdf_bytes(contents)
    else:
        text = extract_text_from_image_bytes(contents)

    mcqs = basic_fallback_mcqs(text, num_questions)

    # increment usage
    cursor.execute("UPDATE users SET usage_count = usage_count + 1 WHERE username=?", (username,))
    conn.commit()

    return {"status": "ok", "mcqs": mcqs}
