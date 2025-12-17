from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import threading
from urllib.parse import urlparse, parse_qs

from common.utils import get_abs_path
import managers as Managers

REST_PORT_DEFAULT = 9000
PORT_FOWARD_SCRIPT = get_abs_path("scripts/portForward.sh")
SSH_FOWARD_BBB_SCRIPT = get_abs_path("scripts/sshForwardBBB.sh")

class RestHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/network/port-forwarding":
            query = parse_qs(parsed.query)
            ip = query.get("ip", [None])[0]
            port = query.get("port", [None])[0]

            if ip and port:
                print(f"Setting port forwarding to {ip}:{port}")
                subprocess.run([f"{PORT_FOWARD_SCRIPT}", ip, port])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing ip or port parameter")
        elif parsed.path == "/network/ssh-forwarding/safety":
            query = parse_qs(parsed.query)
            port = query.get("port", [None])[0]

            command = [f"{SSH_FOWARD_BBB_SCRIPT}"]
            if port:
                command.append(port)
            print(f"Setting ssh forwarding to Safety Board")
            subprocess.run(command)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        pass

    def do_DELETE(self):
        parsed = urlparse(self.path)
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/browser-test"):
            self.path = self.path.replace("/browser-test","")
            parsed = urlparse(self.path)
            if parsed.path.startswith("/post"):
                self.path = self.path.replace("/post","")
                self.do_POST()
            if parsed.path.startswith("/put"):
                self.path = self.path.replace("/put","")
                self.do_PUT()
            if parsed.path.startswith("/delete"):
                self.path = self.path.replace("/delete","")
                self.do_DELETE()

REST_SERVICE_THREAD = None
def startRestService(host="0.0.0.0", port=REST_PORT_DEFAULT) -> bool:
    global REST_SERVICE_THREAD
    if REST_SERVICE_THREAD is not None:
        Managers.LogManager().error(content='REST Server Already Started', source='RestService')
        return
    Managers.LogManager().info(content='Start REST Server...', source='RestService')
    REST_SERVICE_THREAD = threading.Thread(target=HTTPServer((host, port), RestHandler).serve_forever, daemon=True)
    REST_SERVICE_THREAD.start()
