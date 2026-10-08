from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, generate_csrf
from config import Config

db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please login to access this page.'
login_manager.login_message_category = 'warning'

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf)

    from app.auth_routes import auth
    app.register_blueprint(auth)
    from app.admin_routes import admin
    app.register_blueprint(admin)
    from app.student_routes import student
    app.register_blueprint(student)
    from app.ai_routes import ai
    app.register_blueprint(ai)

    with app.app_context():
        from app import models
        db.create_all()
        _run_migrations()
        seed_database()

    return app


def _run_migrations():
    """Safe column additions for existing DBs."""
    import sqlalchemy as sa
    engine = db.engine
    with engine.connect() as conn:
        inspector = sa.inspect(engine)
        cols = [c['name'] for c in inspector.get_columns('question')]
        if 'explanation' not in cols:
            conn.execute(sa.text(
                "ALTER TABLE question ADD COLUMN explanation TEXT"
            ))
            conn.commit()


def seed_database():
    from app.models import Branch, User
    from werkzeug.security import generate_password_hash

    branches = [
        {'name': 'Computer Engineering', 'code': 'CO'},
        {'name': 'Information Technology', 'code': 'IT'},
        {'name': 'Mechanical Engineering', 'code': 'ME'},
        {'name': 'Civil Engineering', 'code': 'CE'},
        {'name': 'Electrical Engineering', 'code': 'EE'},
        {'name': 'AI & Machine Learning', 'code': 'AI'},
        {'name': 'Chemical Engineering', 'code': 'CH'},
    ]
    for branch_data in branches:
        existing = Branch.query.filter_by(code=branch_data['code']).first()
        if not existing:
            branch = Branch(name=branch_data['name'], code=branch_data['code'])
            db.session.add(branch)

    admin_user = User.query.filter_by(email='admin@quiz.com').first()
    if not admin_user:
        admin = User(
            full_name='Super Admin',
            email='admin@quiz.com',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            branch_id=None,
            is_super_admin=True
        )
        db.session.add(admin)
    db.session.commit()
