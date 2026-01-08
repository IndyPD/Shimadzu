"""
Shimadzu Logic Launcher
간단한 GUI로 run.py 프로그램을 시작/정지합니다.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import os
import signal
import sys
from datetime import datetime


class ShimadzuLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("Shimadzu Logic Launcher")
        self.root.geometry("800x600")

        # 프로세스 관련 변수
        self.process = None
        self.is_running = False
        self.read_thread = None

        # UI 구성
        self.setup_ui()

        # 윈도우 닫기 이벤트
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # 상단 프레임 (버튼들)
        top_frame = tk.Frame(self.root, padx=10, pady=10)
        top_frame.pack(fill=tk.X)

        # 시작 버튼
        self.start_btn = tk.Button(
            top_frame,
            text="▶ 시작",
            command=self.start_program,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 12, "bold"),
            width=12,
            height=2
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # 정지 버튼
        self.stop_btn = tk.Button(
            top_frame,
            text="■ 정지",
            command=self.stop_program,
            bg="#f44336",
            fg="white",
            font=("Arial", 12, "bold"),
            width=12,
            height=2,
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 상태 표시
        self.status_label = tk.Label(
            top_frame,
            text="● 정지됨",
            font=("Arial", 14, "bold"),
            fg="#f44336"
        )
        self.status_label.pack(side=tk.LEFT, padx=20)

        # 구분선
        separator = ttk.Separator(self.root, orient='horizontal')
        separator.pack(fill=tk.X, padx=10, pady=5)

        # 로그 프레임
        log_frame = tk.Frame(self.root, padx=10, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_label = tk.Label(log_frame, text="로그:", font=("Arial", 10, "bold"))
        log_label.pack(anchor=tk.W)

        # 로그 텍스트 영역 (스크롤 가능)
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            width=90,
            height=25,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 하단 정보
        bottom_frame = tk.Frame(self.root, padx=10, pady=5)
        bottom_frame.pack(fill=tk.X)

        info_label = tk.Label(
            bottom_frame,
            text="Shimadzu Logic System | run.py 실행 관리",
            font=("Arial", 8),
            fg="#666"
        )
        info_label.pack(side=tk.LEFT)

    def log(self, message, level="INFO"):
        """로그 메시지 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 레벨별 색상
        colors = {
            "INFO": "#4CAF50",
            "WARN": "#FF9800",
            "ERROR": "#f44336",
            "SYSTEM": "#2196F3"
        }
        color = colors.get(level, "#d4d4d4")

        self.log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.log_text.insert(tk.END, f"[{level}] ", level)
        self.log_text.insert(tk.END, f"{message}\n", "message")

        # 태그 설정
        self.log_text.tag_config("timestamp", foreground="#888")
        self.log_text.tag_config(level, foreground=color, font=("Consolas", 9, "bold"))
        self.log_text.tag_config("message", foreground="#d4d4d4")

        # 자동 스크롤
        self.log_text.see(tk.END)

    def start_program(self):
        """run.py 시작"""
        if self.is_running:
            self.log("프로그램이 이미 실행 중입니다.", "WARN")
            return

        try:
            # run.py 경로 확인
            run_py_path = os.path.join(os.path.dirname(__file__), "run.py")
            if not os.path.exists(run_py_path):
                self.log(f"run.py 파일을 찾을 수 없습니다: {run_py_path}", "ERROR")
                return

            self.log("프로그램 시작 중...", "SYSTEM")
            self.log(f"실행 파일: {run_py_path}", "SYSTEM")

            # 서브프로세스로 run.py 실행
            self.process = subprocess.Popen(
                [sys.executable, run_py_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )

            self.is_running = True

            # 버튼 상태 변경
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_label.config(text="● 실행 중", fg="#4CAF50")

            self.log("프로그램이 시작되었습니다.", "SYSTEM")

            # 출력 읽기 스레드 시작
            self.read_thread = threading.Thread(target=self.read_output, daemon=True)
            self.read_thread.start()

        except Exception as e:
            self.log(f"시작 실패: {str(e)}", "ERROR")
            self.is_running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_label.config(text="● 정지됨", fg="#f44336")

    def stop_program(self):
        """run.py 강제 종료"""
        if not self.is_running or self.process is None:
            self.log("실행 중인 프로그램이 없습니다.", "WARN")
            return

        try:
            self.log("프로그램 정지 중...", "SYSTEM")

            # 플래그 먼저 False로 설정 (스레드 종료 유도)
            self.is_running = False

            # Windows에서 프로세스 그룹 종료
            if sys.platform == 'win32':
                # Ctrl+C 신호 전송 시도
                try:
                    self.process.send_signal(signal.CTRL_C_EVENT)
                    self.log("정지 신호 전송됨 (CTRL_C)", "SYSTEM")
                except:
                    pass

                # 2초 대기 후 강제 종료
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.log("프로세스가 응답하지 않습니다. 강제 종료합니다.", "WARN")
                    self.process.kill()
                    self.process.wait()  # 완전히 종료될 때까지 대기
            else:
                # Unix 계열
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.log("프로세스가 응답하지 않습니다. 강제 종료합니다.", "WARN")
                    self.process.kill()
                    self.process.wait()  # 완전히 종료될 때까지 대기

            # 프로세스 정리
            self.process = None

            # 버튼 상태 변경
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_label.config(text="● 정지됨", fg="#f44336")

            self.log("프로그램이 정지되었습니다.", "SYSTEM")

        except Exception as e:
            self.log(f"정지 실패: {str(e)}", "ERROR")
            # 에러 발생 시에도 상태 초기화
            self.is_running = False
            self.process = None
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_label.config(text="● 정지됨", fg="#f44336")

    def read_output(self):
        """서브프로세스의 출력을 읽어서 로그에 표시"""
        try:
            while self.is_running:
                # 프로세스 체크 (None이면 종료)
                if self.process is None:
                    break

                # stdout 읽기
                try:
                    if self.process.stdout:
                        line = self.process.stdout.readline()
                        if line:
                            # UI 업데이트는 메인 스레드에서
                            self.root.after(0, lambda l=line.strip(): self.log(l, "INFO"))
                except:
                    # 프로세스가 종료되어 읽기 실패
                    break

                # 프로세스 종료 확인
                try:
                    if self.process and self.process.poll() is not None:
                        self.root.after(0, lambda: self.log("프로그램이 종료되었습니다.", "SYSTEM"))
                        self.root.after(0, self.on_process_exit)
                        break
                except:
                    # 프로세스가 이미 None인 경우
                    break

        except Exception as e:
            # 스레드 종료 시 에러 로그 출력하지 않음
            if self.is_running:
                self.root.after(0, lambda: self.log(f"출력 읽기 오류: {str(e)}", "ERROR"))

    def on_process_exit(self):
        """프로세스 종료 시 호출"""
        self.is_running = False
        self.process = None
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="● 정지됨", fg="#f44336")

    def on_closing(self):
        """윈도우 닫기 이벤트"""
        if self.is_running:
            self.log("프로그램을 정지하고 종료합니다...", "SYSTEM")
            self.stop_program()

        self.root.destroy()


def main():
    root = tk.Tk()
    app = ShimadzuLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
