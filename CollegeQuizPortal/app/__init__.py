from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from flask_mail import Mail

db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please login to access this page.'
login_manager.login_message_category = 'warning'

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)

    from app.auth_routes import auth
    app.register_blueprint(auth)
    from app.admin_routes import admin
    app.register_blueprint(admin)
    from app.student_routes import student
    app.register_blueprint(student)

    with app.app_context():
        from app import models
        db.create_all()
        seed_database()
    return app

def seed_database():
    from app.models import Branch, User
    from werkzeug.security import generate_password_hash

    branches = [
        {'name': 'Computer Engineering', 'code': 'CO'},
        {'name': 'Information Technology', 'code': 'IT'},
        {'name': 'Mechanical Engineering', 'code': 'ME'},
        {'name': 'Civil Engineering', 'code': 'CE'},
        {'name': 'Electrical Engineering', 'code': 'EE'},
    ]
    for branch_data in branches:
        existing = Branch.query.filter_by(code=branch_data['code']).first()
        if not existing:
            branch = Branch(name=branch_data['name'], code=branch_data['code'])
            db.session.add(branch)

    admin_user = User.query.filter_by(email='admin@quiz.com').first()
    if not admin_user:
        admin = User(
            full_name='Admin',
            email='admin@quiz.com',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            branch_id=None
        )
        db.session.add(admin)
    db.session.commit()