from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    u = User.query.filter_by(email='admin@quiz.com').first()
    if u:
        u.password_hash = generate_password_hash('admin123')
        db.session.commit()
        print("Done! Login: admin@quiz.com / admin123")
    else:
        print("User not found")
