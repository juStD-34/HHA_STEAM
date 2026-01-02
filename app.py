from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import os
import tempfile
from flask_socketio import SocketIO, emit
import logging
from dotenv import load_dotenv
import hmac

# Load env before importing services that rely on it
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
logging.basicConfig(level=logging.DEBUG)

from handler.api import create_api_blueprint
from service import model_service, session_service, game_service
from service.constants import (
    PROTECTED_PREFIXES,
    DEVICE_UNRESTRICTED_ENDPOINTS,
    UNRESTRICTED_ENDPOINTS,
    BEST_STEP1_SESSION_KEY,
    BEST_REFLEX_SESSION_KEY,
    CHARACTERISTIC_READY_SESSION_KEY,
    CHAT_DONE_SESSION_KEY,
)


def _bootstrap_google_credentials() -> None:
    """Render stores service-account JSON in an env var; materialize it if needed."""
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    creds_blob = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_blob:
        return
    try:
        fd, path = tempfile.mkstemp(prefix="gcp-key-", suffix=".json")
        with os.fdopen(fd, "w") as handle:
            handle.write(creds_blob)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        logging.info("Loaded Google credentials from env blob", extra={"component": "bootstrap"})
    except Exception:
        logging.exception("Failed to write GOOGLE_APPLICATION_CREDENTIALS_JSON")


_bootstrap_google_credentials()

# HYBRID ARCHITECTURE: HTTP (ESP32) -> Server -> SocketIO (Web)
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['ACCESS_KEY'] = os.environ.get('APP_ACCESS_KEY', 'enter-demo-key')  # change in production
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

app.register_blueprint(create_api_blueprint(socketio))

def has_access():
    return session.get('access_granted') is True

@app.before_request
def enforce_access():
    if not app.config.get('ACCESS_KEY'):
        return
    if request.endpoint in UNRESTRICTED_ENDPOINTS:
        return
    if request.path in DEVICE_UNRESTRICTED_ENDPOINTS:
        return
    if has_access():
        return
    for prefix in PROTECTED_PREFIXES:
        if request.path.startswith(prefix):
            return jsonify({'error': 'Unauthorized'}), 401
    return redirect(url_for('access_gate', next=request.url))

@app.before_request
def block_home_during_tests():
    if request.endpoint in UNRESTRICTED_ENDPOINTS or request.endpoint is None:
        return
    if session.get('tests_in_progress') and not session.get('tests_completed'):
        if request.endpoint == 'home':
            if request.args.get('abandon') == '1':
                session_service.reset_session_state()
                return
            return redirect(url_for('test_page'))

@app.route('/access', methods=['GET', 'POST'])
def access_gate():
    error = None
    next_url = request.args.get('next') or request.form.get('next') or url_for('home')
    if request.method == 'POST':
        provided = (request.form.get('access_key') or '').strip()
        if provided and hmac.compare_digest(provided, app.config['ACCESS_KEY']):
            session['access_granted'] = True
            return redirect(next_url)
        error = "Mã truy cập không chính xác."
    return render_template('access.html', error=error, next_url=next_url)

@app.route('/')
@app.route('/home')
def home():
    session_service.reset_session_state()
    model_service.ensure_model()
    acc_val = round(model_service.get_accuracy() * 100, 2) if model_service.get_accuracy() else 0
    return render_template('index.html', accuracy=acc_val)

@app.route('/test')
def test_page():
    model_service.ensure_model()
    acc_val = round(model_service.get_accuracy() * 100, 2) if model_service.get_accuracy() else 0
    session['tests_in_progress'] = True
    session['tests_completed'] = False
    student_info = session.get('student_info')
    return render_template(
        'tests.html',
        accuracy=acc_val,
        student_info=student_info,
        tests_completed=session.get('tests_completed', False),
        best_step1=session.get(BEST_STEP1_SESSION_KEY),
        best_reflex=session.get(BEST_REFLEX_SESSION_KEY),
        characteristic_ready=session.get(CHARACTERISTIC_READY_SESSION_KEY, False),
        chat_done=session.get(CHAT_DONE_SESSION_KEY, False),
    )

@app.route('/result')
def result_page():
    model_service.ensure_model()
    acc_val = round(model_service.get_accuracy() * 100, 2) if model_service.get_accuracy() else 0
    student_info = session.get('student_info')
    return render_template(
        'result.html',
        accuracy=acc_val,
        student_info=student_info,
    )

# ===== SOCKET.IO EVENTS (Web Client) =====
@socketio.on('connect')
def handle_connect():
    print('Web Client connected')
    emit('game_update', game_service.get_current_game_state())

@socketio.on('disconnect')
def handle_disconnect():
    print('Web Client disconnected')

if __name__ == '__main__':
    model_service.train_model()
    port = int(os.environ.get('PORT', '5000'))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
