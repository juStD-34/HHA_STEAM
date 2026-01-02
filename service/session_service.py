from flask import session

from career_counselor_chat.service import career_service
from .constants import (
    BEST_STEP1_SESSION_KEY,
    BEST_REFLEX_SESSION_KEY,
    CHAT_HISTORY_SESSION_KEY,
    CAREER_SUMMARY_SESSION_KEY,
    CHARACTERISTIC_READY_SESSION_KEY,
    CHAT_DONE_SESSION_KEY,
    TEST_USER_ID,
)


def reset_session_state():
    session.pop('student_info', None)
    session.pop('tests_in_progress', None)
    session.pop('tests_completed', None)
    session.pop(BEST_STEP1_SESSION_KEY, None)
    session.pop(BEST_REFLEX_SESSION_KEY, None)
    session.pop(CHAT_HISTORY_SESSION_KEY, None)
    session.pop(CAREER_SUMMARY_SESSION_KEY, None)
    session.pop(CHARACTERISTIC_READY_SESSION_KEY, None)
    session.pop(CHAT_DONE_SESSION_KEY, None)
    career_service.reset_test_metrics(user_id=TEST_USER_ID)
