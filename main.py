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
import math
from datetime import datetime, timedelta, timezone

models.Base.metadata.create_all(bind=database.engine)
excel_manager.initialize_excel()

app = FastAPI(title="AttendX")

templates = Jinja2Templates(directory=".")

# Haversine formula to calculate distance between two points in meters
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Radius of the Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

@app.get("/style.css")
def get_style():
    return FileResponse("style.css")

@app.get("/logo.png")
def get_logo():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    raise HTTPException(status_code=404)

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

class QRGenerateRequest(BaseModel):
    faculty_username: str
    latitude: float
    longitude: float
    duration_minutes: int

class ScanData(BaseModel):
    token: str
    roll_number: str
    latitude: float
    longitude: float

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
def generate_qr(request: QRGenerateRequest, db: Session = Depends(get_db)):
    # Deactivate any existing active sessions for this faculty
    db.query(models.AttendanceSession).filter(
        models.AttendanceSession.faculty_username == request.faculty_username,
        models.AttendanceSession.is_active == True
    ).update({"is_active": False})
    
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=request.duration_minutes)
    
    new_session = models.AttendanceSession(
        token=token,
        faculty_username=request.faculty_username,
        latitude=request.latitude,
        longitude=request.longitude,
        created_at=now,
        expires_at=expires_at
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    # Send as ISO format with Z suffix to ensure browser treats it as UTC
    return {"token": token, "expires_at": expires_at.isoformat().replace("+00:00", "Z")}

@app.post("/api/scan_qr")
def scan_qr(data: ScanData, db: Session = Depends(get_db)):
    session = db.query(models.AttendanceSession).filter(
        models.AttendanceSession.token == data.token,
        models.AttendanceSession.is_active == True
    ).first()
    
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or deactivated session.")
    
    # Check expiry (ensuring both are timezone aware for comparison if needed, 
    # but SQLAlchemy usually returns naive. However, if stored as UTC, we compare with UTC)
    now = datetime.now(timezone.utc)
    
    # If the database stored time is naive (common in SQLite), we make it aware for comparison
    session_expiry = session.expires_at
    if session_expiry.tzinfo is None:
        session_expiry = session_expiry.replace(tzinfo=timezone.utc)

    if now > session_expiry:
        session.is_active = False
        db.commit()
        raise HTTPException(status_code=400, detail="Session has expired.")
    
    # Check distance (radius: 5 meters)
    distance = calculate_distance(data.latitude, data.longitude, session.latitude, session.longitude)
    if distance > 5:
        raise HTTPException(status_code=400, detail=f"Location mismatch. You are {round(distance, 1)}m away. Allowed radius: 5m")
    
    # Check if already marked for THIS specific session
    marked = db.query(models.Attendance).filter(
        models.Attendance.session_id == session.id,
        models.Attendance.student_username == data.roll_number
    ).first()
    
    if marked:
        raise HTTPException(status_code=400, detail="Attendance already marked for this session")
    
    # Mark in database
    new_attendance = models.Attendance(
        session_id=session.id,
        student_username=data.roll_number
    )
    db.add(new_attendance)
    db.commit()
    
    # Mark in Excel for historical records
    excel_manager.mark_attendance(data.roll_number, session.id, session.created_at)
    
    return {"message": f"Attendance marked for {data.roll_number}"}

@app.get("/api/download_excel")
def download_excel():
    return FileResponse(excel_manager.EXCEL_FILE, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="Attendance_Sheet.xlsx")

