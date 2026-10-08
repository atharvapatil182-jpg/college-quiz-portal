from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField, IntegerField, TextAreaField, RadioField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, NumberRange,Email

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Link')
class SignupForm(FlaskForm):
    full_name = StringField('Full Name', validators=[
        DataRequired(), Length(min=2, max=100)
    ])
    email = StringField('Email', validators=[
        DataRequired()
    ])
    branch = SelectField('Branch', coerce=int, validators=[
        DataRequired()
    ])
    password = PasswordField('Password', validators=[
        DataRequired(), Length(min=6)
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password')
    ])
    submit = SubmitField('Create Account')

    def validate_email(self, email):
        from app.models import User
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please login.')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired()
    ])
    password = PasswordField('Password', validators=[
        DataRequired()
    ])
    submit = SubmitField('Login')


class QuizForm(FlaskForm):
    title = StringField('Quiz Title', validators=[
        DataRequired(), Length(min=3, max=200)
    ])
    description = TextAreaField('Description')
    duration_minutes = IntegerField('Duration (Minutes)', validators=[
        DataRequired(), NumberRange(min=1, max=180)
    ])
    branch = SelectField('Branch', coerce=int, validators=[
        DataRequired()
    ])
    submit = SubmitField('Create Quiz')


class QuestionForm(FlaskForm):
    question_text = TextAreaField('Question', validators=[
        DataRequired(), Length(min=5)
    ])
    option_a = StringField('Option A', validators=[DataRequired()])
    option_b = StringField('Option B', validators=[DataRequired()])
    option_c = StringField('Option C', validators=[DataRequired()])
    option_d = StringField('Option D', validators=[DataRequired()])
    correct_option = RadioField('Correct Answer', validators=[DataRequired()],
                                choices=[('A','Option A'),('B','Option B'),
                                         ('C','Option C'),('D','Option D')])
    marks = IntegerField('Marks', validators=[
        DataRequired(), NumberRange(min=1, max=10)
    ], default=1)
    submit = SubmitField('Add Question')


class AddAdminForm(FlaskForm):
    full_name = StringField('Full Name', validators=[
        DataRequired(), Length(min=2, max=100)
    ])
    email = StringField('Email', validators=[
        DataRequired()
    ])
    password = PasswordField('Password', validators=[
        DataRequired(), Length(min=6)
    ])
    submit = SubmitField('Create Admin')

    def validate_email(self, email):
        from app.models import User
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered.')


class AIGenerateForm(FlaskForm):
    """Top-level fields for the "Generate Quiz with AI" flow. The topics
    list (topic name + question count per topic) is rendered and added to
    dynamically in the template with plain JS, and is parsed separately
    in app/ai_routes.py from topic_name[]/topic_count[] - it isn't a
    WTForms field because the teacher can add/remove rows freely."""
    chapter = StringField('Chapter / Unit Name', validators=[
        DataRequired(), Length(min=2, max=200)
    ])
    title = StringField('Quiz Title', validators=[
        DataRequired(), Length(min=3, max=200)
    ])
    description = TextAreaField('Description')
    branch = SelectField('Branch', coerce=int, validators=[
        DataRequired()
    ])
    duration_minutes = IntegerField('Time Limit (Minutes)', validators=[
        DataRequired(), NumberRange(min=1, max=180)
    ])
    submit = SubmitField('Generate Questions')
