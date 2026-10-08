import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load a .env file sitting next to this config.py, if one exists, into the
# environment BEFORE Config reads from os.environ below. Copy .env.example
# to .env and fill in your real keys - it is git-ignored on purpose.
load_dotenv(os.path.join(BASE_DIR, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'quizportal-secret-key-2024'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'quiz_portal.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_PERMANENT = False

    # ===== EMAIL SETTINGS =====
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'your-email@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = ('KK Wagh Quiz Portal', os.environ.get('MAIL_USERNAME', 'your-email@gmail.com'))
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    # ===== AI QUESTION GENERATOR (Groq API) =====
    # Copy .env.example to .env in the project root and fill in your real
    # key there (GROQ_API_KEY=gsk_...). Get a free key at console.groq.com
    # Never commit a real key into this file or into .env - .env is git-ignored.
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    # Optional override - defaults to llama-3.1-8b-instant in services/ai_generator.py
    GROQ_MODEL = os.environ.get('GROQ_MODEL')
