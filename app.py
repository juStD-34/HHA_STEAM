from flask import Flask, render_template, request, jsonify
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os
from flask_socketio import SocketIO, emit
import json
import sys

from agents.service import career_service

# HYBRID ARCHITECTURE: HTTP (ESP32) -> Server -> SocketIO (Web)
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# Standard threading mode for Windows compatibility
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
def index():
    global model_accuracy
    if model is None:
        train_model()
    acc_val = round(model_accuracy * 100, 2) if model_accuracy else 0
    return render_template('index.html', accuracy=acc_val)

@app.route('/predict', methods=['POST'])
def predict():
    global model
    if model is None:
        train_model()
        
    try:
        data = request.json
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

@app.route('/chat', methods=['POST'])
def chat_with_ai():
    """Simple chatbot endpoint used by the UI modal."""
    global model_accuracy
    payload = request.json or {}
    message = (payload.get('message') or '').strip()

    if not message:
        return jsonify({'error': 'Missing message'}), 400

    try:
        agent_reply = career_service.ask(message, user_id="web_chat_user").text
        return jsonify({'reply': agent_reply})
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
        data = request.json
        print(f"RAW DATA FROM ESP32 (HTTP): {data}") # DEBUG
        
        event = data.get('event')
        import time as t
        current_time = t.time()
        
        if event == 'start':
            current_game_state['status'] = 'playing'
            current_game_state['time'] = 0.0
            current_game_state['errors'] = 0
            current_game_state['timestamp'] = current_time
            print(">>> GAME STARTED")
            
        elif event == 'update':
            current_game_state['status'] = 'playing'
            current_game_state['time'] = float(data.get('time', 0))
            current_game_state['errors'] = int(data.get('errors', 0))
            current_game_state['timestamp'] = current_time
            
        elif event == 'finish':
            time_val = float(data.get('time', 0))
            errors_val = int(data.get('errors', 0))
            current_game_state['status'] = 'finished'
            current_game_state['time'] = time_val
            current_game_state['errors'] = errors_val
            current_game_state['timestamp'] = current_time
            print(f">>> GAME FINISHED: T={time_val}, E={errors_val}")

        # Broadcast to Web immediately
        socketio.emit('game_update', current_game_state)
        return jsonify({"status": "ok"})
        
    except Exception as e:
        print(f"Error processing ESP32 data: {e}")
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    train_model()
    # Use standard app.run() which works perfectly with threading mode
    app.run(host='0.0.0.0', port=5000, debug=True)

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
def index():
    global model_accuracy
    if model is None:
        train_model()
    acc_val = round(model_accuracy * 100, 2) if model_accuracy else 0
    return render_template('index.html', accuracy=acc_val)

@app.route('/predict', methods=['POST'])
def predict():
    global model
    if model is None:
        train_model()
        
    try:
        data = request.json
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

@app.route('/chat', methods=['POST'])
def chat_with_ai():
    """Simple chatbot endpoint used by the UI modal."""
    global model_accuracy
    payload = request.json or {}
    message = (payload.get('message') or '').strip()

    if not message:
        return jsonify({'error': 'Missing message'}), 400

    normalized = message.lower()
    if 'accuracy' in normalized or 'độ chính xác' in normalized:
        acc_val = round(model_accuracy * 100, 2) if model_accuracy else 0
        response = f"Độ chính xác hiện tại của mô hình là khoảng {acc_val}% dựa trên dữ liệu huấn luyện."
    elif 'bước' in normalized or 'quy trình' in normalized:
        response = "Bạn hoàn thành 2 bước: (1) Nhập kết quả Wire Loop hoặc nhận từ thiết bị ESP32; (2) Chơi đập chuột 10 giây. Sau đó nhấn Phân Tích để xem gợi ý nghề."
    elif 'nhóm' in normalized or 'group' in normalized:
        response = "Nhóm A thiên về phản xạ nhanh, Nhóm B chú trọng sự khéo léo, còn Nhóm C phù hợp tư duy phân tích với ít thao tác tay."
    else:
        response = "Xin chào! Bạn có thể hỏi tôi về quy trình kiểm tra, kết quả hoặc cách hệ thống tư vấn nghề."

    return jsonify({'reply': response})

# ===== SOCKET.IO (For Web Frontend) =====
@socketio.on('connect')
def handle_connect():
    print('Web Client connected')
    emit('game_update', current_game_state)

@socketio.on('disconnect')
def handle_disconnect():
    print('Web Client disconnected')

# ===== RAW WEBSOCKET (For ESP32) =====
@sock.route('/ws')
def esp32_comm(ws):
    global current_game_state
    print(">>> ESP32 HANDSHAKE SUCCESSFUL (Raw WS)")
    try:
        while True:
            data = ws.receive()
            if data:
                print(f"RAW DATA FROM ESP32: {data}") # DEBUG PRINT
                # Process JSON from ESP32
                try:
                    data_dict = json.loads(data)
                    event = data_dict.get('event')
                    
                    # Logic to update state and Broadcast to Web
                    import time as t
                    current_time = t.time()
                    
                    if event == 'start':
                        current_game_state['status'] = 'playing'
                        current_game_state['time'] = 0.0
                        current_game_state['errors'] = 0
                        current_game_state['timestamp'] = current_time
                        print(">>> GAME STARTED (ESP32)")
                        
                    elif event == 'update':
                        current_game_state['status'] = 'playing'
                        current_game_state['time'] = float(data_dict.get('time', 0))
                        current_game_state['errors'] = int(data_dict.get('errors', 0))
                        current_game_state['timestamp'] = current_time
                        
                    elif event == 'finish':
                        time_val = float(data_dict.get('time', 0))
                        errors_val = int(data_dict.get('errors', 0))
                        current_game_state['status'] = 'finished'
                        current_game_state['time'] = time_val
                        current_game_state['errors'] = errors_val
                        current_game_state['timestamp'] = current_time
                        print(f">>> GAME FINISHED: Time={time_val}, Errors={errors_val}")

                    # Broadcast to Update Web UI
                    print(">>> BROADCASTING TO WEB...") # DEBUG PRINT
                    socketio.emit('game_update', current_game_state)
                    
                except json.JSONDecodeError:
                    print(f"Invalid JSON from ESP32: {data}")
    except Exception as e:
        print(f"ESP32 Disconnected or Error: {e}")

if __name__ == '__main__':
    train_model()
    # socketio.run handles the server. flask_sock hooks into the app.
    # standard app.run might be better for flask-sock in threading mode
    app.run(host='0.0.0.0', port=5000, debug=True)
