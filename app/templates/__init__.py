"""
app/__init__.py - Initializes our Flask application.
"""

from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    # Import models so SQLAlchemy knows about them
    from app import models

    # Register Blueprints
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    # Home route — redirects to login page
    @app.route('/')
    def home():
        return redirect(url_for('auth.login'))

    # Create database tables and seed initial data
    with app.app_context():
        db.create_all()
        seed_initial_data()

    return app


def seed_initial_data():
    """
    Creates default branches and a default admin account on first run.
    This runs only if the data doesn't already exist.
    """
    from app.models import Branch, Admin

    # Add default branches if none exist
    if Branch.query.count() == 0:
        default_branches = ['Computer', 'IT', 'Mechanical', 'Civil', 'Electrical']
        for branch_name in default_branches:
            db.session.add(Branch(name=branch_name))
        db.session.commit()
        print('✅ Default branches added: Computer, IT, Mechanical, Civil, Electrical')

    # Create default admin if no admin exists
    if Admin.query.count() == 0:
        default_admin = Admin(username='admin')
        default_admin.set_password('admin123')  # ⚠️ Change this later!
        db.session.add(default_admin)
        db.session.commit()
        print('✅ Default admin created → username: admin | password: admin123')