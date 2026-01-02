from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os
import tempfile
from flask_socketio import SocketIO, emit
import json
import sys
import logging
from dotenv import load_dotenv
import hmac

# Load env before importing services that rely on it
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
logging.basicConfig(level=logging.DEBUG)

from career_counselor_chat.service import career_service


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

# Global variables to store model and data
model = None
model_accuracy = 0.0
current_game_state = {
    'status': 'idle',
    'time': 0.0,
    'errors': 0,
    'group': None,
    'careers': [],
    'timestamp': 0.0
}
data_file = 'career_data.csv'
PROTECTED_PREFIXES = ('/api/', '/predict', '/chat')
DEVICE_UNRESTRICTED_ENDPOINTS = ('/api/game_event',)
UNRESTRICTED_ENDPOINTS = ('static', 'access_gate', 'health_check')
TEST_USER_ID = "web_chat_user"
BEST_STEP1_SESSION_KEY = "best_step1"
BEST_REFLEX_SESSION_KEY = "best_reflex"
CHAT_HISTORY_SESSION_KEY = "chat_history"
CAREER_SUMMARY_SESSION_KEY = "career_summary"
CHARACTERISTIC_READY_SESSION_KEY = "characteristic_ready"
CHAT_DONE_SESSION_KEY = "chat_done"

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
                _reset_session_state()
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

def train_model():
    global model, model_accuracy
    if not os.path.exists(data_file):
        return "Data file not found."
    
    df = pd.read_csv(data_file)
    X = df[['Time', 'Errors', 'Score']]
    y = df['Group']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    clf = DecisionTreeClassifier()
    clf.fit(X_train, y_train)
    
    y_pred = clf.predict(X_test)
    model_accuracy = accuracy_score(y_test, y_pred)
    
    model = clf
    return "Model trained successfully."

@app.route('/')
@app.route('/home')
def home():
    global model_accuracy
    _reset_session_state()
    if model is None:
        train_model()
    acc_val = round(model_accuracy * 100, 2) if model_accuracy else 0
    return render_template('index.html', accuracy=acc_val)

@app.route('/test')
def test_page():
    global model_accuracy
    if model is None:
        train_model()
    acc_val = round(model_accuracy * 100, 2) if model_accuracy else 0
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

@app.route('/predict', methods=['POST'])
def predict():
    global model
    if model is None:
        train_model()
        
    try:
        data = request.json or {}
        time = float(data['time'])
        errors = int(data['errors'])
        score = int(data.get('score', 0))
        
        prediction = model.predict([[time, errors, score]])[0]
        group = prediction
        
        careers_map = {
            'A': ['Phi công', 'Game thủ', 'Lái xe', 'An ninh mạng'],
            'B': ['Bác sĩ', 'Thủ công mỹ nghệ', 'Kỹ thuật nha khoa'],
            'C': ['Kinh tế', 'Sư phạm', 'Luật', 'Ngành ít thao tác tay']
        }
        
        suggested_careers = careers_map.get(group, [])
        return jsonify({
            'group': group,
            'careers': suggested_careers
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/final_report', methods=['POST'])
def generate_final_report():
    student_profile = session.get('student_info')
    if not student_profile:
        return jsonify({'error': 'Chưa có thông tin học sinh.'}), 400

    chat_history = session.get(CHAT_HISTORY_SESSION_KEY, [])
    if not chat_history:
        return jsonify({
            'error': 'Chưa có lịch sử trò chuyện. Hãy trò chuyện với AI trước khi tạo báo cáo.'
        }), 400
    if not session.get(BEST_STEP1_SESSION_KEY) or not session.get(BEST_REFLEX_SESSION_KEY):
        return jsonify({
            'error': (
                'Thiếu kết quả bài test. Hãy hoàn thành Wire Loop và Reflex Test trước khi tạo báo cáo.'
            )
        }), 400

    try:
        report = career_service.generate_final_report(
            student_profile=student_profile,
            chat_history=chat_history,
            user_id=TEST_USER_ID,
        )
        session['tests_in_progress'] = False
        session['tests_completed'] = True
        return jsonify(report)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Failed to generate final report")
        return jsonify({'error': 'Không thể tạo báo cáo cuối.'}), 500

@app.route('/api/university_recommendations', methods=['POST'])
def university_recommendations():
    student_profile = session.get('student_info')
    if not student_profile:
        return jsonify({'error': 'Chưa có thông tin học sinh.'}), 400
    chat_history = session.get(CHAT_HISTORY_SESSION_KEY, [])
    if not chat_history:
        return jsonify({'error': 'Chưa có lịch sử trò chuyện.'}), 400

    career_summary = session.get(CAREER_SUMMARY_SESSION_KEY)
    if not career_summary:
        try:
            career_summary = career_service.generate_career_summary(
                student_profile=student_profile,
                chat_history=chat_history,
                user_id=TEST_USER_ID,
            )
            session[CAREER_SUMMARY_SESSION_KEY] = career_summary
        except Exception as exc:
            app.logger.exception("Failed to generate career summary for university search")
            return jsonify({'error': 'Không thể tạo tóm tắt nghề nghiệp.'}), 500

    try:
        recommendations = career_service.generate_university_recommendations(
            career_summary=career_summary,
            student_profile=student_profile,
            user_id=TEST_USER_ID,
        )
        return jsonify({'recommendations': recommendations})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Failed to generate university recommendations")
        return jsonify({'error': 'Không thể tìm đại học phù hợp.'}), 500

@app.route('/chat', methods=['POST'])
def chat_with_ai():
    """Simple chatbot endpoint used by the UI modal."""
    global model_accuracy
    payload = request.json or {}
    message = (payload.get('message') or '').strip()
    student_profile = session.get('student_info')
    if session.get(CHAT_DONE_SESSION_KEY):
        return jsonify({
            'reply': 'Phần trò chuyện đã hoàn tất. Bạn có thể xem báo cáo hoặc gợi ý đại học nhé.',
            'chat_done': True,
            'characteristic_ready': session.get(CHARACTERISTIC_READY_SESSION_KEY, False),
        })

    if not message:
        return jsonify({'error': 'Missing message'}), 400

    try:
        enriched_message = message
        if student_profile:
            info_str = (
                f"Học sinh: {student_profile.get('full_name')} | "
                f"Giới tính: {student_profile.get('gender')} | "
                f"Khối: {student_profile.get('grade')} | "
                f"Lớp: {student_profile.get('class_name')}\n"
                f"Nội dung: {message}"
            )
            enriched_message = info_str
        session.pop(CAREER_SUMMARY_SESSION_KEY, None)
        agent_reply = career_service.ask(enriched_message, user_id=TEST_USER_ID).text
        parsed_reply = agent_reply
        try:
            reply_data = json.loads(agent_reply)
            parsed_reply = (
                reply_data.get("response", {}).get("result")
                or reply_data.get("result")
                or agent_reply
            )
        except (TypeError, ValueError):
            pass
        characteristic_ready = career_service.is_characteristic_ready(parsed_reply)
        chat_done = career_service.is_chat_done(parsed_reply)
        if characteristic_ready:
            session[CHARACTERISTIC_READY_SESSION_KEY] = True
        chat_history = session.get(CHAT_HISTORY_SESSION_KEY, [])
        chat_history.append({"role": "user", "text": message})
        chat_history.append({"role": "assistant", "text": parsed_reply})
        session[CHAT_HISTORY_SESSION_KEY] = chat_history
        if not chat_done:
            for entry in chat_history:
                if entry.get("role") == "assistant" and career_service.is_chat_done(
                    entry.get("text", "")
                ):
                    chat_done = True
                    break
        if chat_done:
            session[CHAT_DONE_SESSION_KEY] = True
        return jsonify({
            'reply': agent_reply,
            'characteristic_ready': characteristic_ready,
            'chat_done': chat_done,
        })
    except Exception as exc:
        # Fallback to deterministic responses so the UI isn't blocked
        app.logger.exception("Career agent failed, returning fallback response")
        normalized = message.lower()
        if 'accuracy' in normalized or 'độ chính xác' in normalized:
            acc_val = round(model_accuracy * 100, 2) if model_accuracy else 0
            response = f"Độ chính xác hiện tại của mô hình là khoảng {acc_val}% dựa trên dữ liệu huấn luyện."
        elif 'bước' in normalized or 'quy trình' in normalized:
            response = "Bạn hoàn thành 2 bước: (1) Nhập kết quả Wire Loop hoặc nhận từ thiết bị ESP32; (2) Chơi đập chuột 10 giây. Sau đó nhấn Phân Tích để xem gợi ý nghề."
        elif 'nhóm' in normalized or 'group' in normalized:
            response = "Nhóm A thiên về phản xạ nhanh, Nhóm B chú trọng sự khéo léo, còn Nhóm C phù hợp tư duy phân tích với ít thao tác tay."
        else:
            response = (
                "Xin chào! Tính năng tư vấn nghề thông minh đang có lỗi tạm thời, "
                "bạn có thể hỏi về quy trình kiểm tra, kết quả hoặc cách hệ thống tư vấn nghề."
            )
        return jsonify({'reply': response, 'fallback': True}), 200

@app.route('/api/student_info', methods=['POST'])
def save_student_info():
    data = request.json or {}
    full_name = (data.get('full_name') or '').strip()
    gender = (data.get('gender') or '').strip()
    grade = (data.get('grade') or '').strip()
    class_name = (data.get('class_name') or '').strip()
    age = (data.get('age') or '').strip()

    if not all([full_name, gender, grade, class_name, age]):
        return jsonify({'error': 'Thiếu thông tin học sinh.'}), 400

    session['student_info'] = {
        'full_name': full_name,
        'gender': gender,
        'grade': grade,
        'class_name': class_name,
        'age': age
    }
    session.pop(CHAT_HISTORY_SESSION_KEY, None)
    session.pop(CAREER_SUMMARY_SESSION_KEY, None)
    session.pop(CHARACTERISTIC_READY_SESSION_KEY, None)
    session.pop(CHAT_DONE_SESSION_KEY, None)

    return jsonify({'message': 'Đã lưu thông tin học sinh.', 'student_info': session['student_info']}), 200

# ===== SOCKET.IO EVENTS (Web Client) =====
@socketio.on('connect')
def handle_connect():
    print('Web Client connected')
    emit('game_update', current_game_state)

@socketio.on('disconnect')
def handle_disconnect():
    print('Web Client disconnected')

# ===== HTTP API FOR ESP32 (Robust Bridge) =====
@app.route('/api/game_event', methods=['POST'])
def game_event_http():
    global current_game_state
    try:
        data = request.json or {}
        print(f"RAW DATA FROM ESP32 (HTTP): {data}") # DEBUG
        
        event = data.get('event')
        import time as t
        current_time = t.time()
        response_payload = {"status": "ok"}
        
        if event == 'start':
            current_game_state['status'] = 'playing'
            current_game_state['time'] = 0.0
            current_game_state['errors'] = 0
            current_game_state['timestamp'] = current_time
            app.logger.info(">>> GAME STARTED")
            
        elif event == 'update':
            current_game_state['status'] = 'playing'
            current_game_state['time'] = float(data.get('time', 0))
            current_game_state['errors'] = int(data.get('errors', 0))
            current_game_state['timestamp'] = current_time
            
        elif event == 'finish':
            time_val = float(data.get('time') or 0)
            errors_val = int(data.get('errors') or 0)
            current_game_state['status'] = 'finished'
            current_game_state['time'] = time_val
            current_game_state['errors'] = errors_val
            current_game_state['timestamp'] = current_time
            print(f">>> GAME FINISHED: T={time_val}, E={errors_val}")
            best_value, improved = _record_step1_result(time_val, errors_val)
            response_payload.update({
                "best": best_value,
                "improved": improved,
            })

        socket_payload = dict(current_game_state)
        if event == 'finish':
            socket_payload.update({
                "best": response_payload.get("best"),
                "improved": response_payload.get("improved"),
            })
        socketio.emit('game_update', socket_payload)
        return jsonify(response_payload)
        
    except Exception as e:
        print(f"Error processing ESP32 data: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/reflex_result', methods=['POST'])
def reflex_result():
    """Endpoint to record the ReflexTest metrics reported by the client/ESP32."""
    try:
        data = request.json or {}
        app.logger.info("Reflex result payload: %s", data)
        reflex_time = float(data.get('time') or 0.0)
        quantity = int(data.get('quantity') or 0)
        best_value, improved = _record_reflex_result(quantity, reflex_time)
        return jsonify({
            "status": "ok",
            "best": best_value,
            "improved": improved,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.route('/health')
def health_check():
    """Basic health check endpoint for load balancers."""
    status = {
        "status": "ok",
        "model_loaded": model is not None,
        "game_state": current_game_state.get('status'),
    }
    return jsonify(status), 200

if __name__ == '__main__':
    train_model()
    port = int(os.environ.get('PORT', '5000'))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)

def _reset_session_state():
    """Clear session flags and cached test metrics for a fresh attempt."""
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


def _record_step1_result(time_val: float, errors_val: int):
    """Persist the best Wire Loop result in session + agent state."""
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


def _record_reflex_result(quantity: int, time_val: float):
    """Persist the best Reflex game score in session + agent state."""
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
