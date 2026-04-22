# YOLO Attendance System

This is a Flask-based automated attendance system that leverages YOLO (You Only Look Once) for image-based tracking and includes an Admin portal and Teacher records dashboard.

## Setup Instructions

### 1. Prerequisites
Ensure you have **Python 3** installed on your Mac.

### 2. Activate the Virtual Environment
To keep dependencies isolated, it is recommended to use the provided virtual environment. Open your terminal in the project directory and run:

```bash
source venv/bin/activate
```

### 3. Install Dependencies
If you haven't already installed the required packages, you can install them by running:

```bash
pip install -r requirements.txt
```

### 4. Initialize Default Admin (First-time setup)
If you are running the application for the first time and need an admin account, you can create a default one by running:

```bash
flask --app run.py init-admin
```
*This will create an admin user with username `admin` and password `admin123`.*

### 5. Run the Application
Start the Flask development server by running:

```bash
python run.py
```

The application will be accessible in your web browser at:
**http://127.0.0.1:8000**
