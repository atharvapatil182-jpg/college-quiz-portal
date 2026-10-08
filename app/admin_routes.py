from flask import (Blueprint, render_template, redirect,
                   url_for, flash, request, make_response)
from flask_login import login_required, current_user
from app import db
from app.models import User, Branch, Quiz, Question, Result, Answer
from app.forms import QuizForm, QuestionForm, AddAdminForm
import csv, io

admin = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required!', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
def super_admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin' or not current_user.is_super_admin:
            flash('Super Admin access required!', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_students = User.query.filter_by(role='student').count()
    total_quizzes = Quiz.query.count()
    total_attempts = Result.query.count()
    branches = Branch.query.all()
    recent_results = Result.query\
        .order_by(Result.submitted_at.desc())\
        .limit(5).all()
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
    return render_template('admin/dashboard.html',
                           total_students=total_students,
                           total_quizzes=total_quizzes,
                           total_attempts=total_attempts,
                           branches=branches,
                           recent_results=recent_results,
                           quizzes=quizzes)


@admin.route('/create-quiz', methods=['GET', 'POST'])
@login_required
@admin_required
def create_quiz():
    form = QuizForm()
    branches = Branch.query.all()
    form.branch.choices = [(b.id, b.name) for b in branches]
    if form.validate_on_submit():
        quiz = Quiz(
            title=form.title.data,
            description=form.description.data,
            duration_minutes=form.duration_minutes.data,
            branch_id=form.branch.data,
            created_by=current_user.id
        )
        db.session.add(quiz)
        db.session.commit()
        flash(f'Quiz "{quiz.title}" created!', 'success')
        return redirect(url_for('admin.add_questions', quiz_id=quiz.id))
    return render_template('admin/create_quiz.html', form=form)


@admin.route('/quiz/<int:quiz_id>/add-questions', methods=['GET', 'POST'])
@login_required
@admin_required
def add_questions(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    form = QuestionForm()
    if form.validate_on_submit():
        question = Question(
            question_text=form.question_text.data,
            option_a=form.option_a.data,
            option_b=form.option_b.data,
            option_c=form.option_c.data,
            option_d=form.option_d.data,
            correct_option=form.correct_option.data,
            marks=form.marks.data,
            quiz_id=quiz.id
        )
        db.session.add(question)
        db.session.commit()
        flash('Question added!', 'success')
        return redirect(url_for('admin.add_questions', quiz_id=quiz.id))
    questions = Question.query.filter_by(quiz_id=quiz.id).all()
    return render_template('admin/add_questions.html',
                           form=form,
                           quiz=quiz,
                           questions=questions)


@admin.route('/question/<int:question_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    quiz_id = question.quiz_id
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted.', 'info')
    return redirect(url_for('admin.add_questions', quiz_id=quiz_id))


@admin.route('/quiz/<int:quiz_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    quiz.is_active = not quiz.is_active
    db.session.commit()
    status = 'activated' if quiz.is_active else 'deactivated'
    flash(f'Quiz "{quiz.title}" {status}.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    db.session.delete(quiz)
    db.session.commit()
    flash('Quiz deleted.', 'info')
    return redirect(url_for('admin.dashboard'))


@admin.route('/results')
@login_required
@admin_required
def view_results():
    branch_id = request.args.get('branch_id', type=int)
    if branch_id:
        results = Result.query\
            .join(User, Result.user_id == User.id)\
            .filter(User.branch_id == branch_id)\
            .order_by(Result.submitted_at.desc()).all()
    else:
        results = Result.query\
            .order_by(Result.submitted_at.desc()).all()
    branches = Branch.query.all()
    return render_template('admin/view_results.html',
                           results=results,
                           branches=branches,
                           selected_branch=branch_id)


@admin.route('/results/export')
@login_required
@admin_required
def export_csv():
    results = Result.query\
        .order_by(Result.submitted_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Student Name', 'Email', 'Branch',
        'Quiz Title', 'Score', 'Total Marks',
        'Percentage', 'Submitted At'
    ])
    for r in results:
        writer.writerow([
            r.student.full_name,
            r.student.email,
            r.student.branch.name if r.student.branch else 'N/A',
            r.quiz.title,
            r.score,
            r.total_marks,
            f'{r.percentage:.1f}%',
            r.submitted_at.strftime('%Y-%m-%d %H:%M')
        ])
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = \
        'attachment; filename=quiz_results.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


@admin.route('/analytics')
@login_required
@admin_required
def analytics():
    branches = Branch.query.all()
    analytics_data = []
    for branch in branches:
        results = Result.query\
            .join(User, Result.user_id == User.id)\
            .filter(User.branch_id == branch.id).all()
        if results:
            avg_score = sum(r.percentage for r in results) / len(results)
            total = len(results)
            highest = max(r.percentage for r in results)
        else:
            avg_score = 0
            total = 0
            highest = 0
        analytics_data.append({
            'branch': branch.name,
            'total': total,
            'avg_score': round(avg_score, 1),
            'highest': round(highest, 1)
        })
    return render_template('admin/analytics.html',
                           analytics_data=analytics_data)
@admin.route('/students')
@login_required
@admin_required
def students():
    students = User.query\
        .filter_by(role='student')\
        .order_by(User.created_at.desc()).all()

    branches = Branch.query.all()
    branch_id = request.args.get('branch_id', type=int)

    if branch_id:
        students = User.query\
            .filter_by(role='student', branch_id=branch_id)\
            .order_by(User.created_at.desc()).all()

    return render_template('admin/students.html',
                           students=students,
                           branches=branches,
                           selected_branch=branch_id)
@admin.route('/manage-admins')
@login_required
@super_admin_required
def manage_admins():
    admins = User.query.filter_by(role='admin').order_by(User.created_at.desc()).all()
    return render_template('admin/manage_admins.html', admins=admins)


@admin.route('/add-admin', methods=['GET', 'POST'])
@login_required
@super_admin_required
def add_admin():
    from werkzeug.security import generate_password_hash
    form = AddAdminForm()

    if form.validate_on_submit():
        new_admin = User(
            full_name=form.full_name.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            role='admin',
            branch_id=None,
            is_super_admin=False
        )
        db.session.add(new_admin)
        db.session.commit()
        flash(f'Admin "{new_admin.full_name}" created successfully!', 'success')
        return redirect(url_for('admin.manage_admins'))

    return render_template('admin/add_admin.html', form=form)


@admin.route('/admin/<int:admin_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_admin(admin_id):
    admin_user = User.query.get_or_404(admin_id)

    if admin_user.is_super_admin:
        flash('Cannot delete Super Admin!', 'danger')
        return redirect(url_for('admin.manage_admins'))

    if admin_user.id == current_user.id:
        flash('You cannot delete your own account!', 'danger')
        return redirect(url_for('admin.manage_admins'))

    db.session.delete(admin_user)
    db.session.commit()
    flash(f'Admin "{admin_user.full_name}" deleted.', 'info')
    return redirect(url_for('admin.manage_admins'))
