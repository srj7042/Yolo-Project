from datetime import datetime
from json import dumps, loads
from app import db, login_manager
from flask_login import UserMixin

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='teacher') # 'admin' or 'teacher'
    is_approved = db.Column(db.Boolean, default=False) # Admins approve teachers
    
    # Optional Teacher Metadata fields matching the UI 
    name = db.Column(db.String(100), nullable=True)
    subject = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    visible_password = db.Column(db.String(60), nullable=True) # For admin viewing
    
    # Relationships
    attendances_marked = db.relationship('Attendance', backref='marker', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(100), nullable=True, default='Class CS')
    image_filename = db.Column(db.String(200), nullable=True) # Profile thumbnail image
    training_image_count = db.Column(db.Integer, default=0) # Number of images uploaded in training portal out of 20
    face_encoding = db.Column(db.Text, nullable=True) # JSON serialized float array from facenet
    
    # Relationships
    attendances = db.relationship('Attendance', backref='student', lazy=True)
    
    def set_encoding(self, encoding_array):
        # Convert numpy array to list then string
        if encoding_array is not None:
            self.face_encoding = dumps(encoding_array.tolist())
            
    def get_encoding(self):
        import numpy as np
        if self.face_encoding:
            return np.array(loads(self.face_encoding))
        return None

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='Present') # Present, Absent
    method = db.Column(db.String(20), nullable=False, default='yolo') # yolo, manual
    marked_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Which teacher marked this
