import threading
import time
import datetime
from collections import deque
import webbrowser
from flask import Flask, render_template, request, jsonify
from vision_client import VisionClient  # 기존에 작성한 클래스 임포트
from robot_controller import RobotController # 로봇 컨트롤러 임포트

app = Flask(__name__, template_folder='template')

# 전역 변수로 클라이언트 객체 관리 (단일 연결 가정)
vision_client = None
robot_controller = RobotController(robot_ip='192.168.2.20')
recv_thread = None
is_running = False
received_logs = deque(maxlen=200)  # 최근 200개의 수신 데이터 저장
current_target = {"target_x": 0.0, "target_y": 0.0, "target_theta": 0.0}  # 최신 타겟 정보 저장

def receive_thread_func():
    """백그라운드 데이터 수신 스레드"""
    global vision_client, is_running, current_target
    print("Receive thread started.")
    while is_running and vision_client:
        data = vision_client.receive_data()
        if data:
            print(f"[Received] {data}")
            # UI 표시를 위해 로그 저장
            log_entry = {
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "data": f"R) {data}"
            }
            
            # 데이터 파싱: SCENE_RESULT에서 rx, ry, theta 추출
            if data.get("type") == "SCENE_RESULT" and data.get("specimens"):
                try:
                    # 첫 번째 객체의 위치 정보 사용
                    loc = data["specimens"][0].get("location", {})
                    current_target["target_x"] = loc.get("rx", 0.0) * 1000
                    current_target["target_y"] = loc.get("ry", 0.0) * 1000
                    current_target["target_theta"] = loc.get("theta", 0.0)
                except Exception as e:
                    print(f"Parsing Error: {e}")

            received_logs.append(log_entry)
        else:
            time.sleep(0.01)

@app.route('/')
def index():
    """메인 페이지 렌더링"""
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
def connect():
    """비전 시스템 연결"""
    global vision_client, is_running, recv_thread
    data = request.json
    ip = data.get('ip')
    port = int(data.get('port', 5003))

    if not ip:
        return jsonify({"success": False, "message": "IP address is required"}), 400

    # 기존 연결이 있다면 종료
    if vision_client:
        is_running = False
        vision_client.disconnect()
        if recv_thread:
            recv_thread.join()

    vision_client = VisionClient(ip=ip, port=port)
    success = vision_client.connect()
    
    if success:
        # 수신 스레드 시작
        is_running = True
        recv_thread = threading.Thread(target=receive_thread_func)
        recv_thread.daemon = True
        recv_thread.start()
        
        return jsonify({"success": True, "message": f"Connected to {ip}:{port}"})
    else:
        return jsonify({"success": False, "message": "Failed to connect to Vision System"})

@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    """연결 종료"""
    global vision_client, is_running, recv_thread
    if vision_client:
        is_running = False
        vision_client.disconnect()
        if recv_thread:
            recv_thread.join()
            
        vision_client = None
        return jsonify({"success": True, "message": "Disconnected"})
    return jsonify({"success": False, "message": "No active connection"})

@app.route('/api/command/<cmd_type>', methods=['POST'])
def execute_command(cmd_type):
    """비전 명령 실행 (HELLO, CHECK_SCENE, CHECK_GRASP 등)"""
    global vision_client
    if not vision_client:
        return jsonify({"success": False, "message": "Not connected to Vision System"}), 400

    try:
        if cmd_type == 'handshake':
            received_logs.append({"timestamp": datetime.datetime.now().strftime("%H:%M:%S"), "data": "S) HELLO"})
            result = vision_client.handshake()
            return jsonify({"success": True, "data": {"handshake_ok": result}})
        
        elif cmd_type == 'check_scene':
            mode = request.json.get('mode', 'SINGLE')
            received_logs.append({"timestamp": datetime.datetime.now().strftime("%H:%M:%S"), "data": f"S) CHECK_SCENE (mode={mode})"})
            result = vision_client.check_scene(mode=mode)
            return jsonify({"success": True, "data": result})
        
        elif cmd_type == 'stop_scene':
            received_logs.append({"timestamp": datetime.datetime.now().strftime("%H:%M:%S"), "data": "S) STOP_SCENE"})
            result = vision_client.stop_scene()
            return jsonify({"success": True, "data": result})
        
        elif cmd_type == 'check_grasp':
            received_logs.append({"timestamp": datetime.datetime.now().strftime("%H:%M:%S"), "data": "S) CHECK_GRASP"})
            result = vision_client.check_grasp()
            return jsonify({"success": True, "data": result})
        
        else:
            return jsonify({"success": False, "message": "Unknown command"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/robot/connect', methods=['POST'])
def connect_robot():
    """로봇 연결"""
    global robot_controller
    data = request.json
    ip = data.get('ip', '192.168.0.100') # 기본값 예시
    
    if robot_controller:
        robot_controller.disconnect()
    
    robot_controller = RobotController(robot_ip=ip)
    if robot_controller.connect():
        return jsonify({"success": True, "message": f"Connected to Robot at {ip}"})
    else:
        return jsonify({"success": False, "message": "Failed to connect to Robot"})

@app.route('/api/robot/disconnect', methods=['POST'])
def disconnect_robot():
    """로봇 연결 해제"""
    global robot_controller
    if robot_controller:
        robot_controller.disconnect()
        robot_controller = None
        return jsonify({"success": True, "message": "Robot Disconnected"})
    return jsonify({"success": False, "message": "No robot connection"})

@app.route('/api/robot/move_target', methods=['POST'])
def move_robot_target():
    """비전 타겟 좌표로 로봇 이동 (Task Move)"""
    global robot_controller, current_target
    
    if not robot_controller or not robot_controller.is_connected:
        return jsonify({"success": False, "message": "Robot not connected"}), 400

    try:
        # 현재 타겟 좌표 가져오기 (mm 단위)
        tx = current_target.get("target_x", 0.0)
        ty = current_target.get("target_y", 0.0)
        t_theta = current_target.get("target_theta", 0.0)
        
        # robot_controller.py에 정의된 move_to_target 사용
        robot_controller.move_to_target(tx, ty, t_theta)
        
        return jsonify({"success": True, "message": f"Moved to target: x={tx:.2f}, y={ty:.2f}, theta={t_theta:.2f}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """수신된 데이터 로그 반환 (UI 갱신용)"""
    return jsonify({"logs": list(received_logs), "current_target": current_target})

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """로그 초기화"""
    received_logs.clear()
    return jsonify({"success": True, "message": "Logs cleared"})

if __name__ == '__main__':
    # 로봇 자동 연결 시도
    print("Attempting to connect to robot...")
    if robot_controller.connect():
        print("Robot connected automatically.")
        initial_data = robot_controller.get_status()
        print(f"Initial Robot Data: {initial_data}")
    else:
        print("Failed to connect to robot.")

    # 서버 시작 시 웹 브라우저 자동 실행 (1.5초 대기 후 실행)
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()

    # Flask 서버 실행
    app.run(host='0.0.0.0', port=5000, debug=True)