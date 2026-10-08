from flask import (Blueprint, render_template, redirect,
                   url_for, flash, request)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, mail
from app.models import User, Branch
from app.forms import SignupForm, LoginForm
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

auth = Blueprint('auth', __name__)

def get_serializer():
    from flask import current_app
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

@auth.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('student.home'))
    return render_template('index.html')

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))
    form = SignupForm()
    branches = Branch.query.all()
    form.branch.choices = [(b.id, b.name) for b in branches]
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            full_name=form.full_name.data,
            email=form.email.data,
            password_hash=hashed_password,
            role='student',
            branch_id=form.branch.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/signup.html', form=form)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash(f'Welcome back, {user.full_name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('student.home'))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()

        if user:
            s = get_serializer()
            token = s.dumps(email, salt='password-reset-salt')
            reset_url = url_for('auth.reset_password',
                                token=token, _external=True)
            try:
                msg = Message(
                    subject='K.K. Wagh Quiz Portal - Password Reset',
                    recipients=[email]
                )
                msg.html = f'''
                <div style="font-family:Arial,sans-serif;
                            max-width:600px;margin:0 auto;">
                    <div style="background:linear-gradient(135deg,#29b6f6,#0288d1);
                                padding:30px;text-align:center;
                                border-radius:10px 10px 0 0;">
                        <h2 style="color:white;margin:0;">
                            K.K. Wagh Polytechnic
                        </h2>
                        <p style="color:rgba(255,255,255,0.9);margin:5px 0 0;">
                            Quiz Portal
                        </p>
                    </div>
                    <div style="background:#f8fbff;padding:30px;
                                border:1px solid #b3e5fc;
                                border-radius:0 0 10px 10px;">
                        <h3 style="color:#0d47a1;">
                            Hello, {user.full_name}!
                        </h3>
                        <p style="color:#1565c0;">
                            We received a request to reset your password.
                            Click the button below to reset it:
                        </p>
                        <div style="text-align:center;margin:30px 0;">
                            <a href="{reset_url}"
                               style="background:linear-gradient(135deg,#29b6f6,#0288d1);
                                      color:white;padding:14px 35px;
                                      border-radius:10px;text-decoration:none;
                                      font-weight:bold;font-size:1rem;">
                                Reset My Password
                            </a>
                        </div>
                        <p style="color:#5c9bd6;font-size:0.85rem;">
                            This link expires in
                            <strong>30 minutes</strong>.
                            If you didn't request this,
                            ignore this email.
                        </p>
                        <hr style="border-color:#b3e5fc;">
                        <p style="color:#90caf9;font-size:0.8rem;
                                  text-align:center;">
                            K.K. Wagh Polytechnic Quiz Portal
                        </p>
                    </div>
                </div>
                '''
                mail.send(msg)
                flash('Password reset link sent to your email! '
                      'Please check your inbox.', 'success')
            except Exception as e:
                flash(f'Error sending email: {str(e)}', 'danger')
        else:
            flash('No account found with this email address. '
                  'Please check and try again.', 'danger')

        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    try:
        s = get_serializer()
        email = s.loads(token,
                        salt='password-reset-salt',
                        max_age=1800)
    except SignatureExpired:
        flash('Reset link has expired! '
              'Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid reset link! '
              'Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found!', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters!', 'danger')
        elif new_password != confirm_password:
            flash('Passwords do not match!', 'danger')
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password reset successful! '
                  'Please login with your new password.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)