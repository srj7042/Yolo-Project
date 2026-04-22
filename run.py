from app import create_app, db, bcrypt
from app.models import User

app = create_app()

@app.cli.command("init-admin")
def init_admin():
    """Create a default admin user if none exists."""
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            pw_hash = bcrypt.generate_password_hash("admin123").decode('utf-8')
            new_admin = User(username='admin', password=pw_hash, role='admin', is_approved=True)
            db.session.add(new_admin)
            db.session.commit()
            print("Default admin created (username: admin, password: admin123)")
        else:
            print("Admin already exists.")

if __name__ == '__main__':
    app.run(debug=True, port=8000)
