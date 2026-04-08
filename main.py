from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
import models, database
import excel_manager
import uuid
import os

models.Base.metadata.create_all(bind=database.engine)
excel_manager.initialize_excel()

app = FastAPI(title="AttendX")

# Create directories if they don't exist
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Mount static files (css, js, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models for API
class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserLogin(BaseModel):
    username: str
    password: str
    role: str

# Current active QR session token (in memory for simplicity)
current_session_token = None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/student", response_class=HTMLResponse)
async def student_portal(request: Request):
    return templates.TemplateResponse(request=request, name="student.html")

@app.get("/faculty", response_class=HTMLResponse)
async def faculty_portal(request: Request):
    return templates.TemplateResponse(request=request, name="faculty.html")

@app.post("/api/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = models.User(username=user.username, password=user.password, role=user.role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

@app.post("/api/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username, models.User.role == user.role).first()
    if not db_user or db_user.password != user.password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    return {"message": "Login successful", "username": db_user.username, "role": db_user.role}

@app.post("/api/generate_qr")
def generate_qr():
    global current_session_token
    current_session_token = str(uuid.uuid4())
    return {"token": current_session_token}

class ScanData(BaseModel):
    token: str
    roll_number: str

@app.post("/api/scan_qr")
def scan_qr(data: ScanData):
    global current_session_token
    if current_session_token is None or data.token != current_session_token:
        raise HTTPException(status_code=400, detail="Invalid or expired QR code session.")
    
    success = excel_manager.mark_attendance(data.roll_number)
    if success:
        return {"message": f"Attendance marked for {data.roll_number}"}
    else:
        return {"message": f"Attendance already marked for {data.roll_number} today"}

@app.get("/api/download_excel")
def download_excel():
    return FileResponse(excel_manager.EXCEL_FILE, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="Attendance_Sheet.xlsx")

