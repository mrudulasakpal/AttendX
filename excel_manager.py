import os
import openpyxl
from datetime import datetime

EXCEL_FILE = "Attendance_Sheet.xlsx"

def initialize_excel():
    if not os.path.exists(EXCEL_FILE):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Attendance"
        sheet.append(["Date", "Time", "Roll Number", "Status"])
        workbook.save(EXCEL_FILE)

def mark_attendance(roll_number: str):
    initialize_excel()
    workbook = openpyxl.load_workbook(EXCEL_FILE)
    sheet = workbook.active
    
    # Check if already marked today
    today_str = datetime.now().strftime("%Y-%m-%d")
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if row[0] == today_str and row[2] == roll_number:
            return False # already marked
            
    now = datetime.now()
    sheet.append([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), roll_number, "Present"])
    workbook.save(EXCEL_FILE)
    return True
