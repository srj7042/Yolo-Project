import pandas as pd
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User, Student, Attendance
from werkzeug.utils import secure_filename
import os
import csv
from io import StringIO
from app.services.vision import process_classroom_image

teacher = Blueprint('teacher', __name__)

def teacher_required(f):
    def wrap(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role == 'teacher' and not current_user.is_approved):
            flash("You do not have access.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@teacher.route('/teacher_dashboard', methods=['GET'])
@login_required
@teacher_required
def dashboard():
    filter_date = datetime.utcnow().date()
    # High-level stats
    students_count = Student.query.count()
    attendance_records = Attendance.query.filter_by(date=filter_date).all()
    present_count = len([a for a in attendance_records if a.status == 'Present'])
    
    return render_template('teacher_overview.html', 
                           students_count=students_count, 
                           present_count=present_count,
                           absent_count=students_count - present_count,
                           current_date=filter_date)

@teacher.route('/teacher_attendance', methods=['GET', 'POST'])
@login_required
@teacher_required
def take_attendance():
    filter_date_str = request.args.get('date', datetime.utcnow().date().strftime('%Y-%m-%d'))
    try:
        filter_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
    except:
        filter_date = datetime.utcnow().date()
        
    students = Student.query.all()
    attendance_records = {a.student_id: a for a in Attendance.query.filter_by(date=filter_date).all()}
    
    student_data = []
    for s in students:
        record = attendance_records.get(s.id)
        status = record.status if record else "Absent"
        method = record.method if record else "-"
        student_data.append({'student': s, 'status': status, 'method': method})

    return render_template('teacher_attendance.html', student_data=student_data, current_date=filter_date_str)

@teacher.route('/mark_manual_attendance', methods=['POST'])
@login_required
@teacher_required
def mark_manual():
    student_id = request.form.get('student_id')
    status = request.form.get('status')
    date_str = request.form.get('date')
    mark_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
    
    existing = Attendance.query.filter_by(student_id=student_id, date=mark_date).first()
    if existing:
        existing.status = status
        existing.method = 'manual'
        existing.marked_by_id = current_user.id
    else:
        new_att = Attendance(student_id=student_id, date=mark_date, status=status, method='manual', marked_by_id=current_user.id)
        db.session.add(new_att)
    
    db.session.commit()
    update_live_csv()
    flash(f"Attendance updated for student.", "success")
    return redirect(url_for('teacher.take_attendance', date=date_str))

@teacher.route('/upload_classroom_yolo', methods=['POST'])
@login_required
@teacher_required
def upload_yolo():
    if 'image' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    file = request.files['image']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.url)
        
    date_str = request.form.get('date')
    mark_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
    
    # Save image briefly
    filename = secure_filename(file.filename)
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'classroom_images', filename)
    file.save(filepath)
    
    # Process YOLO + Face Recognition
    detected_student_ids = process_classroom_image(filepath)
    
    # Update DB
    new_marks = 0
    for sid in detected_student_ids:
        existing = Attendance.query.filter_by(student_id=sid, date=mark_date).first()
        if existing:
            if existing.status != 'Present':
                existing.status = 'Present'
                existing.method = 'yolo'
                existing.marked_by_id = current_user.id
                new_marks += 1
        else:
            db.session.add(Attendance(student_id=sid, date=mark_date, status='Present', method='yolo', marked_by_id=current_user.id))
            new_marks += 1
            
    db.session.commit()
    update_live_csv()
    
    flash(f"YOLO process complete. Marked {new_marks} students present based on facial recognition.", "success")
    return redirect(url_for('teacher.take_attendance', date=date_str))

@teacher.route('/teacher_records')
@login_required
@teacher_required
def records():
    today = datetime.utcnow().date()
    first_day = today.replace(day=1)
    
    start_date_str = request.args.get('start_date', first_day.strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        start_date = first_day
        end_date = today
        
    students = Student.query.all()
    # Base query for attendance in range
    att_query = Attendance.query.filter(Attendance.date >= start_date, Attendance.date <= end_date).all()
    
    record_data = []
    for s in students:
        student_records = [r for r in att_query if r.student_id == s.id]
        total_days = len(student_records)
        present = len([r for r in student_records if r.status == 'Present'])
        absent = total_days - present
        percentage = round((present / total_days * 100), 1) if total_days > 0 else 0
        
        record_data.append({
            'student': s,
            'total_days': total_days,
            'present': present,
            'absent': absent,
            'percentage': percentage
        })
        
    # Hook for exports if requested directly from records
    export_format = request.args.get('export', 'none')
    if export_format in ['csv', 'excel']:
        data_rows = []
        for rd in record_data:
            data_rows.append({
                "Student Name": rd['student'].name,
                "Roll Number": rd['student'].roll_number,
                f"Days Count ({start_date} to {end_date})": rd['total_days'],
                "Present Days": rd['present'],
                "Absent Days": rd['absent'],
                "Attendance %": f"{rd['percentage']}%"
            })
            
        df = pd.DataFrame(data_rows)
        if export_format == 'excel':
            path = '/tmp/teacher_records.xlsx'
            df.to_excel(path, index=False)
            return send_file(path, as_attachment=True, download_name=f'records_{start_date}_to_{end_date}.xlsx')
        else:
            path = '/tmp/teacher_records.csv'
            df.to_csv(path, index=False)
            return send_file(path, as_attachment=True, download_name=f'records_{start_date}_to_{end_date}.csv')
            
    return render_template('teacher_records.html', 
                            record_data=record_data, 
                            start_date=start_date_str, 
                            end_date=end_date_str)

@teacher.route('/download_attendance')
@login_required
@teacher_required
def download_excel_csv():
    # Real-time export from DB in requested format
    export_format = request.args.get('format', 'csv')
    records = Attendance.query.all()
    
    data_rows = []
    for r in records:
        data_rows.append({
            'Record ID': r.id,
            'Student Roll': r.student.roll_number,
            'Student Name': r.student.name,
            'Date': r.date,
            'Status': r.status,
            'Method': r.method,
            'Marked By Teacher ID': r.marked_by_id
        })
        
    df = pd.DataFrame(data_rows)
    
    if export_format == 'excel':
        path = '/tmp/attendance_report.xlsx'
        df.to_excel(path, index=False)
        return send_file(path, as_attachment=True, download_name='attendance_report.xlsx')
    else:
        path = '/tmp/attendance_report.csv'
        df.to_csv(path, index=False)
        return send_file(path, as_attachment=True, download_name='attendance_report.csv')

def update_live_csv():
    """ Keeps a persistent real-time master CSV file updated on disk as requested. """
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'master_live_attendance.csv')
    try:
        from app.models import Attendance
        records = Attendance.query.all()
        with open(path, 'w', newline='') as f:
            cw = csv.writer(f)
            cw.writerow(['Record ID', 'Student Roll', 'Student Name', 'Date', 'Status', 'Method'])
            for r in records:
                cw.writerow([r.id, r.student.roll_number, r.student.name, r.date, r.status, r.method])
    except:
        pass
