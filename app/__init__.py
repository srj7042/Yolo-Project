from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # Register Blueprints
    from app.blueprints.auth import auth as auth_blueprint
    from app.blueprints.admin import admin as admin_blueprint
    from app.blueprints.teacher import teacher as teacher_blueprint
    
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(teacher_blueprint)
    
    # Create DB tables
    with app.app_context():
        db.create_all()

    return app
