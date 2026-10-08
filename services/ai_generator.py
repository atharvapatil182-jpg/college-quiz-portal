"""
AI Question Generator - Groq API integration for the "Generate Quiz with AI"
admin flow.

This module knows nothing about Flask, sessions, or the database. It takes
plain Python data in and returns plain Python data out, so it can be unit
tested on its own. The two things it's responsible for:

1. Talking to the Groq API (llama-3.1-8b-instant) to turn
   "chapter + topic + how many questions" into a list of validated MCQ
   dicts (with a retry-once policy).
2. Holding the in-progress "draft" quiz (generated but not yet saved to
   the database) in memory between the generate -> preview -> edit ->
   regenerate -> confirm steps, via the DraftStore class.

Nothing in here ever touches the database. The draft only becomes real
Quiz/Question rows when app/ai_routes.py's confirm() view saves it.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid

try:
    from groq import Groq
except ImportError:
    Groq = None


# --------------------------------------------------------------------------
# Config / constants
# --------------------------------------------------------------------------

MAX_QUESTIONS_PER_TOPIC = 25
MAX_TOTAL_QUESTIONS = 100

# Default model: llama-3.1-8b-instant on Groq free tier - fast and capable
# for structured MCQ generation. Override with GROQ_MODEL env variable.
DEFAULT_MODEL = "openai/gpt-oss-20b"

_RETRY_DELAY_SECONDS = 1.5

_OPTION_KEYS = ("option_a", "option_b", "option_c", "option_d")
_OPTION_PREFIX_RE = re.compile(r"^\s*[A-Da-d]\s*[\.\):]\s*")


class AIGenerationError(Exception):
    """Raised whenever we can't produce a usable set of questions.

    The message is written to be shown to the teacher as-is (via flash()),
    so keep it short and free of stack-trace-y detail.
    """


# --------------------------------------------------------------------------
# System prompt
# --------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an experienced polytechnic-level instructor in India writing "
    "exam-quality multiple choice questions for diploma engineering students. "
    "Questions must be clear, technically accurate, unambiguous, and pitched "
    "at a level appropriate for polytechnic students - not trivial, and not "
    "research-level. Every question needs exactly 4 options with exactly one "
    "clearly correct answer. Never use 'all of the above' or 'none of the "
    "above' style options. Do not letter-prefix the option text yourself "
    "(no 'A) ', 'B. ', etc. - just the option text).\n\n"
    "IMPORTANT: You MUST respond with ONLY a valid JSON object. "
    "No markdown, no explanation, no extra text. "
    "The JSON must have a top-level key 'questions' containing an array. "
    "Each question object must have exactly these keys:\n"
    "  - question_text (string)\n"
    "  - option_a (string)\n"
    "  - option_b (string)\n"
    "  - option_c (string)\n"
    "  - option_d (string)\n"
    "  - correct_option (string, exactly one of: A, B, C, D)\n"
    "  - explanation (string, 1-2 sentences explaining why the correct answer is right)\n"
)


# --------------------------------------------------------------------------
# Prompt builder
# --------------------------------------------------------------------------

def _build_prompt(chapter: str, topic_name: str, count: int, avoid_questions=None) -> str:
    prompt = (
        f"Chapter/Unit: {chapter}\n"
        f"Topic: {topic_name}\n"
        f"Number of questions required: {count}\n"
    )
    if avoid_questions:
        joined = "\n".join(f"- {q}" for q in avoid_questions if q)
        if joined:
            prompt += (
                "\nThese questions already exist for this topic. Do not repeat "
                f"them or write close rephrasings of them:\n{joined}\n"
            )
    prompt += (
        f"\nGenerate exactly {count} multiple-choice question(s) on this topic, "
        "grounded in this chapter, suitable for a polytechnic diploma exam. "
        f"Return a JSON object with a 'questions' array containing exactly {count} items."
    )
    return prompt


# --------------------------------------------------------------------------
# Question validation / cleanup
# --------------------------------------------------------------------------

def _clean_question(raw: dict) -> dict:
    """Validate + tidy up one question dict returned by the model."""
    text = (raw.get("question_text") or "").strip()
    correct = (raw.get("correct_option") or "").strip().upper()

    # Accept "A." or "a)" style prefixes from the model and strip them
    if len(correct) > 1:
        correct = correct[0]

    options = {}
    for key in _OPTION_KEYS:
        value = (raw.get(key) or "").strip()
        value = _OPTION_PREFIX_RE.sub("", value).strip()
        options[key] = value

    if not text:
        raise AIGenerationError("The AI returned a question with no text.")
    if correct not in ("A", "B", "C", "D"):
        raise AIGenerationError(
            f"The AI returned a question with an invalid correct answer: '{correct}'."
        )
    if any(not value for value in options.values()):
        raise AIGenerationError("The AI returned a question with a blank option.")

    explanation = (raw.get("explanation") or "").strip()

    return {
        "question_text": text,
        "option_a": options["option_a"],
        "option_b": options["option_b"],
        "option_c": options["option_c"],
        "option_d": options["option_d"],
        "correct_option": correct,
        "explanation": explanation,
        "marks": 1,
    }


# --------------------------------------------------------------------------
# Groq API calls
# --------------------------------------------------------------------------

def _request_questions(client, model, chapter, topic_name, count, avoid_questions=None):
    """One attempt at asking Groq for `count` MCQs on a topic."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(chapter, topic_name, count, avoid_questions)},
        ],
        response_format={"type": "json_object"},
        max_tokens=min(8000, 700 + count * 350),
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise AIGenerationError(f'Groq returned an empty response for "{topic_name}".')

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIGenerationError(
            f'Groq returned invalid JSON for "{topic_name}": {exc}'
        )

    # Accept either {"questions": [...]} or a bare list at top level
    if isinstance(data, list):
        raw_questions = data
    else:
        raw_questions = data.get("questions") or []

    if not raw_questions:
        raise AIGenerationError(f'Groq did not return any questions for "{topic_name}".')

    return [_clean_question(q) for q in raw_questions]


def _generate_with_retry(client, model, chapter, topic_name, count, avoid_questions=None):
    """Ask for `count` questions, retrying once on any failure."""
    last_error = None
    for attempt in (1, 2):
        try:
            questions = _request_questions(
                client, model, chapter, topic_name, count, avoid_questions
            )
        except AIGenerationError as exc:
            last_error = exc
        except Exception as exc:
            last_error = AIGenerationError(
                f'The AI service reported an error while writing questions for '
                f'"{topic_name}": {exc}'
            )
        else:
            if len(questions) < count:
                last_error = AIGenerationError(
                    f'Groq returned only {len(questions)} of the {count} requested '
                    f'question(s) for "{topic_name}".'
                )
            else:
                return questions[:count]

        if attempt == 1:
            time.sleep(_RETRY_DELAY_SECONDS)

    raise AIGenerationError(
        f'Could not generate questions for "{topic_name}" after two attempts. '
        f'{last_error}'
    )


def _build_client(api_key):
    if Groq is None:
        raise AIGenerationError(
            "The 'groq' Python package is not installed. "
            "Run: pip install groq"
        )
    if not api_key:
        raise AIGenerationError(
            "No Groq API key is configured. Set the GROQ_API_KEY "
            "environment variable in your .env file and restart the server. "
            "Get a free key at https://console.groq.com"
        )
    return Groq(api_key=api_key)


# --------------------------------------------------------------------------
# Public generation API used by app/ai_routes.py
# --------------------------------------------------------------------------

def generate_quiz_draft(chapter, topics, api_key, model=None):
    """Generate a full multi-topic draft.

    `topics` is a list of {"topic_name": str, "requested_count": int}.
    Returns a list of topic dicts ready to hand to DraftStore.create().
    Raises AIGenerationError without writing anything to the database.
    """
    client = _build_client(api_key)
    model = model or DEFAULT_MODEL
    draft_topics = []

    for t_idx, topic in enumerate(topics, start=1):
        topic_key = f"t{t_idx}"
        questions = _generate_with_retry(
            client, model, chapter, topic["topic_name"], topic["requested_count"]
        )
        draft_topics.append({
            "key": topic_key,
            "topic_name": topic["topic_name"],
            "requested_count": topic["requested_count"],
            "questions": [
                {"key": f"{topic_key}_q{q_idx}", **question}
                for q_idx, question in enumerate(questions, start=1)
            ],
        })

    return draft_topics


def regenerate_topic_questions(chapter, topic_name, count, api_key, model=None):
    """Regenerate every question for a single topic."""
    client = _build_client(api_key)
    model = model or DEFAULT_MODEL
    return _generate_with_retry(client, model, chapter, topic_name, count)


def regenerate_single_question(chapter, topic_name, api_key, model=None, avoid_questions=None):
    """Regenerate exactly one question for a topic."""
    client = _build_client(api_key)
    model = model or DEFAULT_MODEL
    questions = _generate_with_retry(
        client, model, chapter, topic_name, 1, avoid_questions=avoid_questions
    )
    return questions[0]


# --------------------------------------------------------------------------
# DraftStore - holds generated-but-not-yet-saved quizzes in memory
# --------------------------------------------------------------------------

class DraftStore:
    """A small in-memory store for AI-generated quiz drafts awaiting teacher
    review before anything is saved to the database.

    Drafts are kept in a plain process-wide dict, keyed by a random id
    stashed in the teacher's Flask session, and scoped to the admin who
    created them. Two admins generating quizzes simultaneously never see
    each other's drafts.

    Caveat: drafts do not survive an app restart and are not shared across
    multiple worker processes. Fine for a single `flask run` process; swap
    out for Redis if you ever deploy with multiple gunicorn workers.
    """

    _lock = threading.Lock()
    _drafts: dict = {}
    _MAX_AGE_SECONDS = 2 * 60 * 60  # drop abandoned drafts after 2 hours

    @classmethod
    def create(cls, owner_id, data) -> str:
        cls._purge_expired()
        draft_id = uuid.uuid4().hex
        with cls._lock:
            cls._drafts[draft_id] = {
                "owner_id": owner_id,
                "data": data,
                "touched": time.time(),
            }
        return draft_id

    @classmethod
    def get(cls, draft_id, owner_id):
        if not draft_id:
            return None
        with cls._lock:
            entry = cls._drafts.get(draft_id)
            if not entry or entry["owner_id"] != owner_id:
                return None
            entry["touched"] = time.time()
            return entry["data"]

    @classmethod
    def save(cls, draft_id, owner_id, data) -> bool:
        with cls._lock:
            entry = cls._drafts.get(draft_id)
            if not entry or entry["owner_id"] != owner_id:
                return False
            entry["data"] = data
            entry["touched"] = time.time()
            return True

    @classmethod
    def discard(cls, draft_id, owner_id):
        with cls._lock:
            entry = cls._drafts.get(draft_id)
            if entry and entry["owner_id"] == owner_id:
                cls._drafts.pop(draft_id, None)

    @classmethod
    def _purge_expired(cls):
        cutoff = time.time() - cls._MAX_AGE_SECONDS
        with cls._lock:
            expired = [k for k, v in cls._drafts.items() if v["touched"] < cutoff]
            for k in expired:
                cls._drafts.pop(k, None)
