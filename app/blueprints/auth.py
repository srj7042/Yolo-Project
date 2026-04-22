from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_user, logout_user, current_user, login_required
from app import db, bcrypt
from app.models import User

auth = Blueprint('auth', __name__)

@auth.route('/')
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('teacher.dashboard'))
            
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'teacher')
        
        user = User.query.filter_by(username=username, role=role).first()
        if user and bcrypt.check_password_hash(user.password, password):
            if role == 'teacher' and not user.is_approved:
                flash("Your account is pending admin approval.", "warning")
                return redirect(url_for('auth.login'))
                
            login_user(user)
            if role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('teacher.dashboard'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('login.html')

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Check if username exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return redirect(url_for('auth.signup'))
            
        # Register as teacher (requires approval)
        new_user = User(username=username, password=hashed_password, role='teacher', is_approved=False)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. Please wait for admin approval.", "success")
        return redirect(url_for('auth.login'))
        
    return render_template('signup.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
