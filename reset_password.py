"""Run this once to reset a student password:
   python reset_password.py
"""
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    u = User.query.filter_by(email='bhanosesanika@gmail.com').first()
    if u:
        u.password_hash = generate_password_hash('student123')
        db.session.commit()
        print("Done! Login with: bhanosesanika@gmail.com / student123")
    else:
        print("User not found")
