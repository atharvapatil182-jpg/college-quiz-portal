"""
Admin-only "Generate Quiz with AI" flow.

This is a separate flow from admin.create_quiz / admin.add_questions (the
manual quiz-building pages), which are untouched. The steps here are:

  1. GET/POST /admin/ai/generate  - teacher describes the quiz (chapter,
     topics + how many questions each, title/branch/duration).
  2. On submit, we call Claude once per topic (services/ai_generator.py)
     and stash the result as an in-memory "draft" (nothing is saved to
     the database yet).
  3. GET /admin/ai/preview - shows the draft, grouped by topic, with
     inline-editable fields plus "regenerate this question" /
     "regenerate this topic" buttons.
  4. POST /admin/ai/confirm - only now do we create the Quiz + Question
     rows via the normal SQLAlchemy models.

The whole preview page is one HTML form. Every button on it (Save,
Regenerate question, Regenerate topic, Confirm & Create Quiz) submits the
same set of question fields, so whichever button the teacher clicks, any
edits they've made anywhere else on the page are captured first and
folded into the draft before that button's specific action runs.
"""

from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, session, current_app,
)
from flask_login import login_required, current_user

from app import db
from app.admin_routes import admin_required
from app.forms import AIGenerateForm
from app.models import Branch, Quiz, Question
from services import ai_generator

ai = Blueprint('ai', __name__, url_prefix='/admin/ai')


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _parse_topics(topic_names, topic_counts):
    """Turn the raw topic_name[]/topic_count[] form lists into a clean
    list of {"topic_name", "requested_count"} dicts, plus a list of
    human-readable error strings for anything that didn't parse."""
    topics = []
    errors = []

    for idx, (name, count_raw) in enumerate(zip(topic_names, topic_counts), start=1):
        name = (name or '').strip()
        count_raw = (count_raw or '').strip()

        if not name and not count_raw:
            continue  # a blank trailing row - just ignore it

        if not name:
            errors.append(f'Topic #{idx}: please enter a topic name.')
            continue

        try:
            count = int(count_raw)
        except ValueError:
            errors.append(f'"{name}": number of questions must be a whole number.')
            continue

        if count < 1 or count > ai_generator.MAX_QUESTIONS_PER_TOPIC:
            errors.append(
                f'"{name}": number of questions must be between 1 and '
                f'{ai_generator.MAX_QUESTIONS_PER_TOPIC}.'
            )
            continue

        topics.append({'topic_name': name, 'requested_count': count})

    if not errors and not topics:
        errors.append('Add at least one topic with a question count.')

    total = sum(t['requested_count'] for t in topics)
    if total > ai_generator.MAX_TOTAL_QUESTIONS:
        errors.append(
            f'Total questions requested ({total}) is too high - please keep '
            f'the total under {ai_generator.MAX_TOTAL_QUESTIONS} per generation.'
        )

    return topics, errors


def _field_name(topic_key, question_key, field):
    return f'q__{topic_key}__{question_key}__{field}'


def _apply_edits(draft, form):
    """Fold any inline edits from the preview form back into the draft.
    Called before every save / regenerate / confirm action so nothing the
    teacher typed is lost, no matter which button they clicked."""
    for topic in draft['topics']:
        for question in topic['questions']:
            prefix = f"q__{topic['key']}__{question['key']}__"

            text = form.get(prefix + 'question_text')
            if text is not None:
                question['question_text'] = text.strip()

            for opt in ('option_a', 'option_b', 'option_c', 'option_d'):
                value = form.get(prefix + opt)
                if value is not None:
                    question[opt] = value.strip()

            correct = form.get(prefix + 'correct_option')
            if correct:
                correct = correct.strip().upper()
                if correct in ('A', 'B', 'C', 'D'):
                    question['correct_option'] = correct
    return draft


def _validate_draft_ready(draft):
    """Final safety check before writing anything to the database."""
    problems = []
    for topic in draft['topics']:
        for idx, question in enumerate(topic['questions'], start=1):
            label = f'{topic["topic_name"]} Q{idx}'
            if not question['question_text'].strip():
                problems.append(f'{label}: question text is empty.')
            for opt in ('option_a', 'option_b', 'option_c', 'option_d'):
                if not question[opt].strip():
                    problems.append(f'{label}: option {opt[-1].upper()} is empty.')
            if question['correct_option'] not in ('A', 'B', 'C', 'D'):
                problems.append(f'{label}: no correct answer selected.')
    return problems


def _get_draft_or_none():
    draft_id = session.get('ai_draft_id')
    draft = ai_generator.DraftStore.get(draft_id, current_user.id)
    return draft_id, draft


# --------------------------------------------------------------------------
# Step 1: describe the quiz
# --------------------------------------------------------------------------

@ai.route('/generate', methods=['GET', 'POST'])
@login_required
@admin_required
def generate():
    form = AIGenerateForm()
    branches = Branch.query.all()
    form.branch.choices = [(b.id, b.name) for b in branches]

    if request.method == 'POST':
        topic_names = request.form.getlist('topic_name[]')
        topic_counts = request.form.getlist('topic_count[]')
        submitted_rows = [
            {'topic_name': n, 'requested_count': c}
            for n, c in zip(topic_names, topic_counts)
            if n.strip() or c.strip()
        ] or [{'topic_name': '', 'requested_count': ''}]

        topics, topic_errors = _parse_topics(topic_names, topic_counts)
        form_ok = form.validate_on_submit()

        if form_ok and not topic_errors:
            try:
                draft_topics = ai_generator.generate_quiz_draft(
                    chapter=form.chapter.data.strip(),
                    topics=topics,
                    api_key=current_app.config.get('GROQ_API_KEY'),
                    model=current_app.config.get('GROQ_MODEL'),
                )
            except ai_generator.AIGenerationError as exc:
                flash(str(exc), 'danger')
            else:
                branch_lookup = dict(form.branch.choices)
                draft = {
                    'quiz_meta': {
                        'title': form.title.data.strip(),
                        'description': (form.description.data or '').strip(),
                        'branch_id': form.branch.data,
                        'branch_name': branch_lookup.get(form.branch.data, ''),
                        'duration_minutes': form.duration_minutes.data,
                        'chapter': form.chapter.data.strip(),
                    },
                    'topics': draft_topics,
                }
                draft_id = ai_generator.DraftStore.create(current_user.id, draft)
                session['ai_draft_id'] = draft_id
                flash('Questions generated! Review them below before saving.', 'success')
                return redirect(url_for('ai.preview'))
        else:
            for err in topic_errors:
                flash(err, 'danger')

        return render_template(
            'admin/ai_generate.html', form=form, topic_rows=submitted_rows,
            max_per_topic=ai_generator.MAX_QUESTIONS_PER_TOPIC,
            max_total=ai_generator.MAX_TOTAL_QUESTIONS,
        )

    return render_template(
        'admin/ai_generate.html', form=form,
        topic_rows=[{'topic_name': '', 'requested_count': 5}],
        max_per_topic=ai_generator.MAX_QUESTIONS_PER_TOPIC,
        max_total=ai_generator.MAX_TOTAL_QUESTIONS,
    )


# --------------------------------------------------------------------------
# Step 2: preview / edit / regenerate / confirm
# --------------------------------------------------------------------------

@ai.route('/preview')
@login_required
@admin_required
def preview():
    draft_id, draft = _get_draft_or_none()
    if not draft:
        flash('No draft to preview yet - generate a quiz first.', 'info')
        return redirect(url_for('ai.generate'))

    total_questions = sum(len(t['questions']) for t in draft['topics'])
    return render_template(
        'admin/ai_preview.html', draft=draft, total_questions=total_questions
    )


@ai.route('/preview/save', methods=['POST'])
@login_required
@admin_required
def save_edits():
    draft_id, draft = _get_draft_or_none()
    if not draft:
        flash('Your draft has expired - please generate again.', 'warning')
        return redirect(url_for('ai.generate'))

    _apply_edits(draft, request.form)
    ai_generator.DraftStore.save(draft_id, current_user.id, draft)
    flash('Changes saved.', 'success')
    return redirect(url_for('ai.preview'))


@ai.route('/preview/question/<topic_key>/<question_key>/regenerate', methods=['POST'])
@login_required
@admin_required
def regenerate_question(topic_key, question_key):
    draft_id, draft = _get_draft_or_none()
    if not draft:
        flash('Your draft has expired - please generate again.', 'warning')
        return redirect(url_for('ai.generate'))

    _apply_edits(draft, request.form)

    topic = next((t for t in draft['topics'] if t['key'] == topic_key), None)
    if not topic:
        ai_generator.DraftStore.save(draft_id, current_user.id, draft)
        flash('That topic no longer exists in this draft.', 'danger')
        return redirect(url_for('ai.preview'))

    sibling_texts = [q['question_text'] for q in topic['questions'] if q['key'] != question_key]

    try:
        new_question = ai_generator.regenerate_single_question(
            chapter=draft['quiz_meta']['chapter'],
            topic_name=topic['topic_name'],
            api_key=current_app.config.get('GROQ_API_KEY'),
            model=current_app.config.get('GROQ_MODEL'),
            avoid_questions=sibling_texts,
        )
    except ai_generator.AIGenerationError as exc:
        ai_generator.DraftStore.save(draft_id, current_user.id, draft)
        flash(str(exc), 'danger')
        return redirect(url_for('ai.preview'))

    for idx, q in enumerate(topic['questions']):
        if q['key'] == question_key:
            new_question['key'] = question_key
            topic['questions'][idx] = new_question
            break

    ai_generator.DraftStore.save(draft_id, current_user.id, draft)
    flash('Question regenerated.', 'success')
    return redirect(url_for('ai.preview'))


@ai.route('/preview/topic/<topic_key>/regenerate', methods=['POST'])
@login_required
@admin_required
def regenerate_topic(topic_key):
    draft_id, draft = _get_draft_or_none()
    if not draft:
        flash('Your draft has expired - please generate again.', 'warning')
        return redirect(url_for('ai.generate'))

    _apply_edits(draft, request.form)

    topic = next((t for t in draft['topics'] if t['key'] == topic_key), None)
    if not topic:
        ai_generator.DraftStore.save(draft_id, current_user.id, draft)
        flash('That topic no longer exists in this draft.', 'danger')
        return redirect(url_for('ai.preview'))

    try:
        new_questions = ai_generator.regenerate_topic_questions(
            chapter=draft['quiz_meta']['chapter'],
            topic_name=topic['topic_name'],
            count=topic['requested_count'],
            api_key=current_app.config.get('GROQ_API_KEY'),
            model=current_app.config.get('GROQ_MODEL'),
        )
    except ai_generator.AIGenerationError as exc:
        ai_generator.DraftStore.save(draft_id, current_user.id, draft)
        flash(str(exc), 'danger')
        return redirect(url_for('ai.preview'))

    topic['questions'] = [
        {'key': f'{topic_key}_q{idx}', **q}
        for idx, q in enumerate(new_questions, start=1)
    ]

    ai_generator.DraftStore.save(draft_id, current_user.id, draft)
    flash(f'Regenerated all questions for "{topic["topic_name"]}".', 'success')
    return redirect(url_for('ai.preview'))


@ai.route('/confirm', methods=['POST'])
@login_required
@admin_required
def confirm():
    draft_id, draft = _get_draft_or_none()
    if not draft:
        flash('Your draft has expired - please generate again.', 'warning')
        return redirect(url_for('ai.generate'))

    _apply_edits(draft, request.form)
    ai_generator.DraftStore.save(draft_id, current_user.id, draft)

    problems = _validate_draft_ready(draft)
    if problems:
        for problem in problems[:5]:
            flash(problem, 'danger')
        if len(problems) > 5:
            flash(f'...and {len(problems) - 5} more issue(s).', 'danger')
        return redirect(url_for('ai.preview'))

    meta = draft['quiz_meta']
    quiz = Quiz(
        title=meta['title'],
        description=meta.get('description') or None,
        duration_minutes=meta['duration_minutes'],
        branch_id=meta['branch_id'],
        created_by=current_user.id,
    )
    db.session.add(quiz)
    db.session.flush()  # assigns quiz.id without ending the transaction

    question_count = 0
    for topic in draft['topics']:
        for q in topic['questions']:
            db.session.add(Question(
                question_text=q['question_text'],
                option_a=q['option_a'],
                option_b=q['option_b'],
                option_c=q['option_c'],
                option_d=q['option_d'],
                correct_option=q['correct_option'],
                explanation=q.get('explanation', ''),
                marks=q.get('marks', 1),
                quiz_id=quiz.id,
            ))
            question_count += 1

    db.session.commit()

    ai_generator.DraftStore.discard(draft_id, current_user.id)
    session.pop('ai_draft_id', None)

    flash(
        f'Quiz "{quiz.title}" created with {question_count} AI-generated question(s)!',
        'success',
    )
    return redirect(url_for('admin.add_questions', quiz_id=quiz.id))


@ai.route('/discard', methods=['POST'])
@login_required
@admin_required
def discard():
    draft_id = session.pop('ai_draft_id', None)
    if draft_id:
        ai_generator.DraftStore.discard(draft_id, current_user.id)
    flash('Draft discarded.', 'info')
    return redirect(url_for('ai.generate'))
