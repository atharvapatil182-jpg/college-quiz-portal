from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app import db
from app.models import User, Branch, Quiz, Question, Result, Answer
from datetime import datetime

student = Blueprint('student', __name__, url_prefix='/student')

def student_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role == 'admin':
            flash('This page is for students only!', 'warning')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@student.route('/home')
@login_required
@student_required
def home():
    branch = Branch.query.get(current_user.branch_id)
    quizzes = Quiz.query.filter_by(branch_id=current_user.branch_id, is_active=True).order_by(Quiz.created_at.desc()).all()
    attempted_quiz_ids = [r.quiz_id for r in Result.query.filter_by(user_id=current_user.id).all()]
    return render_template('student/home.html', branch=branch, quizzes=quizzes, attempted_quiz_ids=attempted_quiz_ids)

@student.route('/quiz/<int:quiz_id>/start')
@login_required
@student_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if not quiz.is_active:
        flash('This quiz is not available.', 'warning')
        return redirect(url_for('student.home'))
    existing = Result.query.filter_by(user_id=current_user.id, quiz_id=quiz_id).first()
    if existing:
        flash('You already attempted this quiz!', 'warning')
        return redirect(url_for('student.home'))
    if quiz.branch_id != current_user.branch_id:
        flash('This quiz is not for your branch!', 'danger')
        return redirect(url_for('student.home'))
    session[f'quiz_start_{quiz_id}'] = datetime.utcnow().isoformat()
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    if not questions:
        flash('This quiz has no questions yet!', 'warning')
        return redirect(url_for('student.home'))
    return render_template('student/quiz.html', quiz=quiz, questions=questions)

@student.route('/quiz/<int:quiz_id>/submit', methods=['POST'])
@login_required
@student_required
def submit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    existing = Result.query.filter_by(user_id=current_user.id, quiz_id=quiz_id).first()
    if existing:
        flash('Already submitted!', 'warning')
        return redirect(url_for('student.result', result_id=existing.id))
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    score = 0
    total_marks = 0
    result = Result(user_id=current_user.id, quiz_id=quiz_id, score=0, total_marks=0, percentage=0.0)
    db.session.add(result)
    db.session.flush()
    for question in questions:
        total_marks += question.marks
        selected = request.form.get(f'question_{question.id}')
        is_correct = False
        if selected and selected.upper() == question.correct_option.upper():
            is_correct = True
            score += question.marks
        answer = Answer(result_id=result.id, question_id=question.id, selected_option=selected, is_correct=is_correct)
        db.session.add(answer)
    result.score = score
    result.total_marks = total_marks
    result.percentage = (score / total_marks * 100) if total_marks > 0 else 0
    db.session.commit()
    session.pop(f'quiz_start_{quiz_id}', None)
    flash('Quiz submitted!', 'success')
    return redirect(url_for('student.result', result_id=result.id))

@student.route('/result/<int:result_id>')
@login_required
@student_required
def result(result_id):
    result = Result.query.get_or_404(result_id)
    if result.user_id != current_user.id:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('student.home'))
    answers = Answer.query.filter_by(result_id=result_id).all()
    questions = {q.id: q for q in Question.query.filter_by(quiz_id=result.quiz_id).all()}
    return render_template('student/result.html', result=result, answers=answers, questions=questions)

@student.route('/result/<int:result_id>/pdf')
@login_required
@student_required
def download_pdf(result_id):
    from io import BytesIO
    from flask import make_response
    result = Result.query.get_or_404(result_id)
    if result.user_id != current_user.id:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('student.home'))
    answers = Answer.query.filter_by(result_id=result_id).all()
    questions = {q.id: q for q in Question.query.filter_by(quiz_id=result.quiz_id).all()}
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.units import cm
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []
        # Title
        title_style = ParagraphStyle('title', parent=styles['Title'],
                                     fontSize=20, textColor=colors.HexColor('#0288d1'), spaceAfter=6)
        story.append(Paragraph("K.K. Wagh Polytechnic – Quiz Portal", title_style))
        story.append(Paragraph("Result Scorecard", styles['Heading2']))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0288d1')))
        story.append(Spacer(1, 0.3*cm))
        # Meta table
        pct = round(result.percentage, 1)
        status = "PASS" if result.percentage >= 35 else "FAIL"
        meta = [
            ["Student", result.student.full_name],
            ["Quiz", result.quiz.title],
            ["Score", f"{result.score} / {result.total_marks}"],
            ["Percentage", f"{pct}%"],
            ["Status", status],
            ["Date", result.submitted_at.strftime('%d %b %Y, %I:%M %p')],
        ]
        t = Table(meta, colWidths=[4*cm, 12*cm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 11),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#e3f2fd')),
            ('TEXTCOLOR', (1,4), (1,4), colors.green if status=='PASS' else colors.red),
            ('FONTNAME', (1,4), (1,4), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('BOX', (0,0), (-1,-1), 0.5, colors.grey),
            ('INNERGRID', (0,0), (-1,-1), 0.25, colors.lightgrey),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("Answer Review", styles['Heading3']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Spacer(1, 0.2*cm))
        opt_labels = {'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd'}
        for i, ans in enumerate(answers, 1):
            q = questions.get(ans.question_id)
            if not q:
                continue
            opts = {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d}
            sel = (ans.selected_option or '').upper()
            cor = (q.correct_option or '').upper()
            bg = colors.HexColor('#e8f5e9') if ans.is_correct else colors.HexColor('#ffebee')
            icon = '✓' if ans.is_correct else '✗'
            q_style = ParagraphStyle('qs', parent=styles['Normal'], fontSize=10,
                                     leading=14, spaceAfter=2)
            story.append(Paragraph(f"<b>Q{i}.</b> {q.question_text}", q_style))
            rows = []
            for letter in ['A','B','C','D']:
                mark = ''
                if letter == cor:
                    mark = ' ✓ (Correct)'
                elif letter == sel and not ans.is_correct:
                    mark = ' ✗ (Your answer)'
                rows.append([f"{letter}.", opts[letter] + mark])
            opt_table = Table(rows, colWidths=[1*cm, 15*cm])
            opt_table.setStyle(TableStyle([
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('PADDING', (0,0), (-1,-1), 3),
                ('TEXTCOLOR', (0, list('ABCD').index(cor)), (1, list('ABCD').index(cor)), colors.green),
            ]))
            story.append(opt_table)
            if q.explanation:
                exp_style = ParagraphStyle('exp', parent=styles['Normal'], fontSize=9,
                                           textColor=colors.HexColor('#555555'),
                                           leftIndent=10, spaceAfter=4)
                story.append(Paragraph(f"<i>Explanation: {q.explanation}</i>", exp_style))
            story.append(Spacer(1, 0.25*cm))
        doc.build(story)
        buf.seek(0)
        response = make_response(buf.read())
        response.headers['Content-Type'] = 'application/pdf'
        fname = f"result_{result_id}_{result.student.full_name.replace(' ','_')}.pdf"
        response.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response
    except ImportError:
        flash('PDF generation requires reportlab. Please install it on the server.', 'danger')
        return redirect(url_for('student.result', result_id=result_id))

@student.route('/leaderboard')
@login_required
def leaderboard():
    quizzes = Quiz.query.filter_by(is_active=True).all()
    quiz_id = request.args.get('quiz_id', type=int)
    if quiz_id:
        results = Result.query.filter_by(quiz_id=quiz_id).order_by(Result.percentage.desc(), Result.submitted_at.asc()).all()
        selected_quiz = Quiz.query.get(quiz_id)
    else:
        results = Result.query.order_by(Result.percentage.desc(), Result.submitted_at.asc()).limit(20).all()
        selected_quiz = None
    return render_template('student/leaderboard.html', results=results, quizzes=quizzes, selected_quiz=selected_quiz)


@student.route('/profile', methods=['GET', 'POST'])
@login_required
@student_required
def profile():
    from werkzeug.security import generate_password_hash, check_password_hash

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            new_name = request.form.get('full_name')
            if new_name and len(new_name.strip()) >= 2:
                current_user.full_name = new_name.strip()
                db.session.commit()
                flash('Profile updated successfully!', 'success')
            else:
                flash('Name must be at least 2 characters.', 'danger')

        elif action == 'change_password':
            current_pw = request.form.get('current_password')
            new_pw = request.form.get('new_password')
            confirm_pw = request.form.get('confirm_password')

            if not check_password_hash(current_user.password_hash, current_pw):
                flash('Current password is incorrect.', 'danger')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'danger')
            elif new_pw != confirm_pw:
                flash('New passwords do not match.', 'danger')
            else:
                current_user.password_hash = generate_password_hash(new_pw)
                db.session.commit()
                flash('Password changed successfully!', 'success')

        return redirect(url_for('student.profile'))

    results = Result.query.filter_by(user_id=current_user.id)\
        .order_by(Result.submitted_at.desc()).all()

    total_attempts = len(results)
    avg_score = round(sum(r.percentage for r in results) / total_attempts, 1) if total_attempts > 0 else 0
    best_score = round(max(r.percentage for r in results), 1) if total_attempts > 0 else 0
    total_marks_earned = sum(r.score for r in results)

    all_students = User.query.filter_by(role='student').all()
    student_avgs = []
    for s in all_students:
        s_results = Result.query.filter_by(user_id=s.id).all()
        if s_results:
            s_avg = sum(r.percentage for r in s_results) / len(s_results)
            student_avgs.append((s.id, s_avg))

    student_avgs.sort(key=lambda x: x[1], reverse=True)
    rank = next((i+1 for i, (sid, _) in enumerate(student_avgs) if sid == current_user.id), None)

    return render_template('student/profile.html',
                           results=results,
                           total_attempts=total_attempts,
                           avg_score=avg_score,
                           best_score=best_score,
                           total_marks_earned=total_marks_earned,
                           rank=rank,
                           total_students=len(student_avgs))