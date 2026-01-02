from flask import Blueprint, current_app, jsonify, request, session
import json

from career_counselor_chat.service import career_service
from service import model_service, game_service
from service.constants import (
    BEST_STEP1_SESSION_KEY,
    BEST_REFLEX_SESSION_KEY,
    CHAT_HISTORY_SESSION_KEY,
    CAREER_SUMMARY_SESSION_KEY,
    CHARACTERISTIC_READY_SESSION_KEY,
    CHAT_DONE_SESSION_KEY,
    TEST_USER_ID,
)


def create_api_blueprint(socketio):
    api = Blueprint('api', __name__)

    @api.route('/predict', methods=['POST'])
    def predict():
        model_service.ensure_model()
        try:
            data = request.json or {}
            time_val = float(data['time'])
            errors_val = int(data['errors'])
            score_val = int(data.get('score', 0))

            model = model_service.ensure_model()
            prediction = model.predict([[time_val, errors_val, score_val]])[0]
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
        except Exception as exc:
            return jsonify({'error': str(exc)}), 400

    @api.route('/api/final_report', methods=['POST'])
    def generate_final_report():
        payload = request.json or {}
        current_app.logger.info("Final report payload: %s", payload)
        student_profile = payload.get('student_info') or session.get('student_info')
        if not student_profile:
            return jsonify({'error': 'Chưa có thông tin học sinh.'}), 400

        chat_history = session.get(CHAT_HISTORY_SESSION_KEY, [])
        if not chat_history:
            return jsonify({
                'error': 'Chưa có lịch sử trò chuyện. Hãy trò chuyện với AI trước khi tạo báo cáo.'
            }), 400
        best_step1 = payload.get('best_step1') or session.get(BEST_STEP1_SESSION_KEY)
        best_reflex = payload.get('best_reflex') or session.get(BEST_REFLEX_SESSION_KEY)
        if not best_step1 or not best_reflex:
            return jsonify({
                'error': (
                    'Thiếu kết quả bài test. Hãy hoàn thành Wire Loop và Reflex Test trước khi tạo báo cáo.'
                )
            }), 400

        try:
            career_service.update_test_metrics(
                user_id=TEST_USER_ID,
                ingenuous={'time': best_step1.get('time'), 'mistake': best_step1.get('errors')},
                reflex={'time': best_reflex.get('time'), 'quantity': best_reflex.get('quantity')},
            )
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
        except Exception:
            current_app.logger.exception("Failed to generate final report")
            return jsonify({'error': 'Không thể tạo báo cáo cuối.'}), 500

    @api.route('/api/university_recommendations', methods=['POST'])
    def university_recommendations():
        payload = request.json or {}
        student_profile = payload.get('student_info') or session.get('student_info')
        if not student_profile:
            return jsonify({'error': 'Chưa có thông tin học sinh.'}), 400
        fit_jobs = (payload.get('fit_jobs') or '').strip()
        if fit_jobs:
            career_summary = f"Ngành nghề phù hợp: {fit_jobs}"
        else:
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
                except Exception:
                    current_app.logger.exception("Failed to generate career summary for university search")
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
        except Exception:
            current_app.logger.exception("Failed to generate university recommendations")
            return jsonify({'error': 'Không thể tìm đại học phù hợp.'}), 500

    @api.route('/chat', methods=['POST'])
    def chat_with_ai():
        payload = request.json or {}
        message = (payload.get('message') or '').strip()
        student_profile = payload.get('student_info') or session.get('student_info')
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
        except Exception:
            current_app.logger.exception("Career agent failed, returning fallback response")
            normalized = message.lower()
            if 'accuracy' in normalized or 'độ chính xác' in normalized:
                acc_val = round(model_service.get_accuracy() * 100, 2) if model_service.get_accuracy() else 0
                response = f"Độ chính xác hiện tại của mô hình là khoảng {acc_val}% dựa trên dữ liệu huấn luyện."
            elif 'bước' in normalized or 'quy trình' in normalized:
                response = (
                    "Bạn hoàn thành 2 bước: (1) Nhập kết quả Wire Loop hoặc nhận từ thiết bị ESP32; "
                    "(2) Chơi đập chuột 10 giây. Sau đó nhấn Phân Tích để xem gợi ý nghề."
                )
            elif 'nhóm' in normalized or 'group' in normalized:
                response = (
                    "Nhóm A thiên về phản xạ nhanh, Nhóm B chú trọng sự khéo léo, "
                    "còn Nhóm C phù hợp tư duy phân tích với ít thao tác tay."
                )
            else:
                response = (
                    "Xin chào! Tính năng tư vấn nghề thông minh đang có lỗi tạm thời, "
                    "bạn có thể hỏi về quy trình kiểm tra, kết quả hoặc cách hệ thống tư vấn nghề."
                )
            return jsonify({'reply': response, 'fallback': True}), 200

    @api.route('/api/student_info', methods=['POST'])
    def save_student_info():
        data = request.json or {}
        full_name = (data.get('full_name') or '').strip()
        grade = (data.get('grade') or '').strip()
        class_name = (data.get('class_name') or '').strip()

        if not all([full_name, grade, class_name]):
            return jsonify({'error': 'Thiếu thông tin học sinh.'}), 400

        student_info = {
            'full_name': full_name,
            'grade': grade,
            'class_name': class_name,
        }
        return jsonify({'message': 'Đã lưu thông tin học sinh.', 'student_info': student_info}), 200

    @api.route('/api/game_event', methods=['POST'])
    def game_event_http():
        try:
            data = request.json or {}
            current_app.logger.info("RAW DATA FROM ESP32 (HTTP): %s", data)
            event = data.get('event')
            response_payload = {"status": "ok"}

            if event == 'start':
                game_service.mark_game_start()
                current_app.logger.info(">>> GAME STARTED")
            elif event == 'update':
                game_service.update_game_state(
                    float(data.get('time', 0)),
                    int(data.get('errors', 0)),
                )
            elif event == 'finish':
                time_val = float(data.get('time') or 0)
                errors_val = int(data.get('errors') or 0)
                _, best_value, improved = game_service.mark_game_finish(time_val, errors_val)
                response_payload.update({
                    "best": best_value,
                    "improved": improved,
                })

            socket_payload = dict(game_service.get_current_game_state())
            if event == 'finish':
                socket_payload.update({
                    "best": response_payload.get("best"),
                    "improved": response_payload.get("improved"),
                })
            socketio.emit('game_update', socket_payload)
            return jsonify(response_payload)
        except Exception as exc:
            current_app.logger.exception("Error processing ESP32 data")
            return jsonify({"error": str(exc)}), 400

    @api.route('/api/reflex_result', methods=['POST'])
    def reflex_result():
        try:
            data = request.json or {}
            current_app.logger.info("Reflex result payload: %s", data)
            reflex_time = float(data.get('time') or 0.0)
            quantity = int(data.get('quantity') or 0)
            best_value, improved = game_service.record_reflex_result(quantity, reflex_time)
            return jsonify({
                "status": "ok",
                "best": best_value,
                "improved": improved,
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @api.route('/health')
    def health_check():
        status = {
            "status": "ok",
            "model_loaded": model_service.is_model_loaded(),
            "game_state": game_service.get_current_game_state().get('status'),
        }
        return jsonify(status), 200

    return api
