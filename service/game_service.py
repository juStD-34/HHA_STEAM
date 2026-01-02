import time as t
from flask import session

from career_counselor_chat.service import career_service
from .constants import (
    BEST_STEP1_SESSION_KEY,
    BEST_REFLEX_SESSION_KEY,
    CHAT_DONE_SESSION_KEY,
    CHARACTERISTIC_READY_SESSION_KEY,
    TEST_USER_ID,
)

_current_game_state = {
    'status': 'idle',
    'time': 0.0,
    'errors': 0,
    'group': None,
    'careers': [],
    'timestamp': 0.0,
}


def get_current_game_state():
    return _current_game_state


def mark_game_start():
    now = t.time()
    _current_game_state['status'] = 'playing'
    _current_game_state['time'] = 0.0
    _current_game_state['errors'] = 0
    _current_game_state['timestamp'] = now
    return now


def update_game_state(time_val: float, errors_val: int):
    now = t.time()
    _current_game_state['status'] = 'playing'
    _current_game_state['time'] = float(time_val)
    _current_game_state['errors'] = int(errors_val)
    _current_game_state['timestamp'] = now
    return now


def mark_game_finish(time_val: float, errors_val: int):
    now = t.time()
    _current_game_state['status'] = 'finished'
    _current_game_state['time'] = float(time_val)
    _current_game_state['errors'] = int(errors_val)
    _current_game_state['timestamp'] = now
    best_value, improved = record_step1_result(time_val, errors_val)
    all_done = (
        session.get(BEST_STEP1_SESSION_KEY)
        and session.get(BEST_REFLEX_SESSION_KEY)
        and (
            session.get(CHAT_DONE_SESSION_KEY)
            or session.get(CHARACTERISTIC_READY_SESSION_KEY)
        )
    )
    if all_done:
        session['tests_in_progress'] = False
        session['tests_completed'] = True
    return now, best_value, improved


def record_step1_result(time_val: float, errors_val: int):
    best = session.get(BEST_STEP1_SESSION_KEY)
    improved = False
    candidate = {'time': float(time_val), 'errors': int(errors_val)}
    if (
        not best
        or candidate['errors'] < best.get('errors', 0)
        or (
            candidate['errors'] == best.get('errors', 0)
            and candidate['time'] < best.get('time', float('inf'))
        )
    ):
        session[BEST_STEP1_SESSION_KEY] = candidate
        career_service.update_test_metrics(
            user_id=TEST_USER_ID,
            ingenuous={'time': candidate['time'], 'mistake': candidate['errors']},
        )
        best = candidate
        improved = True
    elif not best:
        best = candidate
    return best, improved


def record_reflex_result(quantity: int, time_val: float):
    best = session.get(BEST_REFLEX_SESSION_KEY)
    improved = False
    candidate = {'quantity': int(quantity), 'time': float(time_val)}
    if not best or candidate['quantity'] > best.get('quantity', 0):
        session[BEST_REFLEX_SESSION_KEY] = candidate
        career_service.update_test_metrics(
            user_id=TEST_USER_ID,
            reflex={'time': candidate['time'], 'quantity': candidate['quantity']},
        )
        best = candidate
        improved = True
    elif not best:
        best = candidate
    return best, improved
