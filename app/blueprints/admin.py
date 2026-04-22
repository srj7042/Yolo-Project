import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User, Student, Attendance
from werkzeug.utils import secure_filename
import os
import csv
from io import StringIO
from app.services.vision import generate_face_encoding
import uuid

admin = Blueprint('admin', __name__)

def admin_required(f):
    def wrap(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("You need to be an admin to view this page.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@admin.route('/admin_dashboard')
@login_required
@admin_required
def dashboard():
    pending_teachers = User.query.filter_by(role='teacher', is_approved=False).all()
    students_count = Student.query.count()
    return render_template('admin_dashboard.html', pending_teachers=pending_teachers, students_count=students_count)

@admin.route('/approve_teacher/<int:user_id>')
@login_required
@admin_required
def approve_teacher(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f"Teacher {user.username} approved successfully.", "success")
    return redirect(url_for('admin.dashboard'))

@admin.route('/students', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_students():
    if request.method == 'POST':
        roll_number = request.form.get('roll_number')
        name = request.form.get('name')
        image = request.files.get('image')
        
        student = Student.query.filter_by(roll_number=roll_number).first()
        if student:
            flash("Student with this roll number already exists.", "danger")
        else:
            new_student = Student(roll_number=roll_number, name=name)
            
            if image and image.filename:
                # Need to run face encoder
                encoding = generate_face_encoding(image)
                if encoding is not None:
                    new_student.set_encoding(encoding)
                    
                    # Physically save image
                    # generate unique name using roll number + secure name
                    image.seek(0) # reset file cursor after face generator
                    filename = secure_filename(f"{roll_number}_{image.filename}")
                    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'known_faces', filename)
                    image.save(save_path)
                    new_student.image_filename = filename
                else:
                    flash("Could not detect a clear face in the uploaded image. Added without face data.", "warning")
            
            db.session.add(new_student)
            db.session.commit()
            flash("Student added successfully.", "success")
            
    students = Student.query.all()
    return render_template('admin_students.html', students=students)

@admin.route('/bulk_upload_students', methods=['POST'])
@login_required
@admin_required
def bulk_upload_students():
    file = request.files.get('file')
    if file and file.filename.endswith(('.csv', '.xlsx')):
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
                
            count = 0
            for index, row in df.iterrows():
                roll = str(row.get('roll_number', row.get('Roll Number', '')))
                name = str(row.get('name', row.get('Name', '')))
                if roll and name:
                    if not Student.query.filter_by(roll_number=roll).first():
                        ns = Student(roll_number=roll, name=name)
                        db.session.add(ns)
                        count += 1
            db.session.commit()
            flash(f"Successfully uploaded {count} new students.", "success")
        except Exception as e:
            flash(f"Error parsing file: {str(e)}", "danger")
    return redirect(url_for('admin.manage_students'))

@admin.route('/delete_student/<int:student_id>')
@login_required
@admin_required
def delete_student(student_id):
    s = Student.query.get_or_404(student_id)
    db.session.delete(s)
    db.session.commit()
    flash("Student deleted.", "success")
    return redirect(url_for('admin.manage_students'))

@admin.route('/analytics')
@login_required
@admin_required
def analytics():
    # Setup default dates
    today = datetime.utcnow().date()
    # Default: first day of current month to today
    first_day = today.replace(day=1)
    
    start_date_str = request.args.get('start_date', first_day.strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        start_date = first_day
        end_date = today
        
    # Get all students
    students = Student.query.all()
    
    # Get attendances in range
    records = Attendance.query.filter(Attendance.date >= start_date, Attendance.date <= end_date).all()
    
    # Process aggregates
    analytics_data = []
    
    for s in students:
        student_records = [r for r in records if r.student_id == s.id]
        total_days = len(student_records)
        present = len([r for r in student_records if r.status == 'Present'])
        absent = total_days - present
        percentage = round((present / total_days * 100), 1) if total_days > 0 else 0
        
        analytics_data.append({
            'student': s,
            'total_days': total_days,
            'present': present,
            'absent': absent,
            'percentage': percentage
        })
        
    # Optional CSV / Excel export hook
    export_format = request.args.get('export', 'none')
    if export_format in ['csv', 'excel']:
        data_rows = []
        for ad in analytics_data:
            data_rows.append({
                "Roll Number": ad['student'].roll_number,
                "Name": ad['student'].name,
                f"Total Days ({start_date} to {end_date})": ad['total_days'],
                "Present": ad['present'],
                "Absent": ad['absent'],
                "Attendance %": f"{ad['percentage']}%"
            })
            
        df = pd.DataFrame(data_rows)
        
        if export_format == 'csv':
            path = '/tmp/admin_date_analytics.csv'
            df.to_csv(path, index=False)
            return send_file(path, as_attachment=True, download_name=f'attendance_{start_date}_to_{end_date}.csv')
            
        elif export_format == 'excel':
            path = '/tmp/admin_date_analytics.xlsx'
            df.to_excel(path, index=False)
            return send_file(path, as_attachment=True, download_name=f'attendance_{start_date}_to_{end_date}.xlsx')
        
    return render_template('admin_analytics.html', 
                            analytics_data=analytics_data, 
                            start_date=start_date_str, 
                            end_date=end_date_str)

@admin.route('/training')
@login_required
@admin_required
def training_dashboard():
    students = Student.query.all()
    return render_template('admin_training.html', students=students)

@admin.route('/training/upload/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def training_upload(student_id):
    student = Student.query.get_or_404(student_id)
    files = request.files.getlist('file')
    
    if not files:
        return {"error": "No files uploaded"}, 400
        
    folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'training_cache', student.roll_number)
    os.makedirs(folder_path, exist_ok=True)
    
    saved_count = 0
    for file in files:
        if file.filename and student.training_image_count < 20:
            filename = secure_filename(file.filename)
            save_path = os.path.join(folder_path, filename)
            file.save(save_path)
            student.training_image_count += 1
            saved_count += 1
            
    db.session.commit()
    return {"success": True, "count": student.training_image_count, "saved_this_request": saved_count}

@admin.route('/training/process/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def training_process(student_id):
    student = Student.query.get_or_404(student_id)
    folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'training_cache', student.roll_number)
    
    if not os.path.exists(folder_path) or student.training_image_count == 0:
        flash("No images to train for this student.", "warning")
        return redirect(url_for('admin.training_dashboard'))
        
    # We will compute average encoding
    from app.services.vision import generate_average_encoding
    
    avg_encoding = generate_average_encoding(folder_path)
    if avg_encoding is not None:
        student.set_encoding(avg_encoding)
        db.session.commit()
        flash(f"Successfully trained model for {student.name} using multiple images!", "success")
    else:
        flash(f"Failed to find clear faces in the uploaded images for {student.name}.", "danger")
        
    return redirect(url_for('admin.training_dashboard'))

@admin.route('/teachers')
@login_required
@admin_required
def manage_teachers():
    # Fetch all teachers
    teachers = User.query.filter_by(role='teacher').all()
    
    # Calculate stats per teacher
    teacher_data = []
    for t in teachers:
        # All attendance markings done by this teacher
        records = Attendance.query.filter_by(marked_by_id=t.id).all()
        total_marked = len(records)
        present = len([r for r in records if r.status == 'Present'])
        absent = total_marked - present
        
        teacher_data.append({
            'user': t,
            'total_marked': total_marked,
            'present': present,
            'absent': absent
        })
        
    return render_template('admin_teachers.html', teacher_data=teacher_data)

@admin.route('/delete_teacher/<int:teacher_id>')
@login_required
@admin_required
def delete_teacher(teacher_id):
    t = User.query.get_or_404(teacher_id)
    if t.role == 'admin':
        flash("Cannot delete an administrator.", "danger")
        return redirect(url_for('admin.manage_teachers'))
        
    # Unlink any attendance records marked by this teacher to avoid foreign key constraints
    Attendance.query.filter_by(marked_by_id=t.id).update({'marked_by_id': None})
    
    db.session.delete(t)
    db.session.commit()
    flash(f"Teacher {t.username} has been permanently removed.", "success")
    return redirect(url_for('admin.manage_teachers'))
