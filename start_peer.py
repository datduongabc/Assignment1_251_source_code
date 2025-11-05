import socket
import threading
import json
import time
import argparse
import sys
from queue import Queue, Empty
from http.server import HTTPServer, BaseHTTPRequestHandler

class Peer:
    def __init__(self, tracker_url, my_host, my_port, username, ui_queue):
        self.tracker_url = tracker_url
        self.my_host = my_host
        self.my_port = int(my_port)
        self.username = username
        # Hàng đợi để gửi tin nhắn đến UI
        self.ui_queue = ui_queue
        # Hardcode các kênh có sẵn
        self.subscribed_channels = ['#general', '#mmt', '#cnpm']
        self.running = True
        # Danh sách chứa các socket đến các peer khác
        self.connections = []
        # Dùng set để lưu (ip, port) tránh kết nối trùng lặp
        self.connected_peers_info = set()
        # Lock để bảo vệ danh sách connections khi nhiều luồng truy cập
        self.connections_lock = threading.Lock()
        self.auth_cookie = None
        # Tạo socket server để lắng nghe kết nối từ các peer khác
        self.peer_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.peer_server_socket.bind((self.my_host, self.my_port))
        
    def start(self):
        server_thread = threading.Thread(target=self.run_server_thread, daemon=True)
        server_thread.start()
        
        connect_thread = threading.Thread(target=self.run_connect_thread, daemon=True)
        connect_thread.start()
        
    def run_server_thread(self):
        self.peer_server_socket.listen(5)
        while True:
            try:
                conn, addr = self.peer_server_socket.accept()
                self.add_connection(conn, addr)
                
                listener = threading.Thread(target=self.handle_peer_messages, args=(conn, addr), daemon=True)
                listener.start()
            except Exception:
                time.sleep(1)
                
    def run_connect_thread(self):
        if not self.login_to_tracker('admin', 'password'):
            return
        if not self.submit_info_to_tracker():
            return

        while self.running:
            peer_list = self.get_peer_list()
            if not peer_list:
                time.sleep(15)
                continue
            my_connectable_ip = 'localhost' if self.my_host == '0.0.0.0' else self.my_host
            my_info = (my_connectable_ip, self.my_port)
            
            for peer_addr in peer_list:
                if not self.running:
                    break
                if peer_addr == my_info:
                    continue
                is_connected = False
                with self.connections_lock:
                    if peer_addr in self.connected_peers_info:
                        is_connected = True
                if not is_connected:
                    try:
                        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        peer_socket.connect(peer_addr)
                        self.add_connection(peer_socket, peer_addr)
                        listener = threading.Thread(target=self.handle_peer_messages, args=(peer_socket, peer_addr), daemon=True)
                        listener.start()
                    except Exception:
                        pass
            time.sleep(15)

    def handle_peer_messages(self, conn, addr):
        conn.settimeout(None)
        while self.running:
            try:
                data = conn.recv(1024)
                if not data:
                    break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
            try:
                message = json.loads(data.decode('utf-8'))
                if message.get('type') == 'message':
                    channel_id = message.get('channels')
                    
                    if channel_id in self.subscribed_channels:
                        formatted_msg = f"{channel_id}|[{message.get('username')}]: {message.get('content')}"
                        self.ui_queue.put(formatted_msg)
            except json.JSONDecodeError:
                pass
        self.remove_connection(conn, addr)

    # Send message to all connected peers.
    def broadcast_message(self, message_content, channel_id='#general'):
        message_packet = {
            "type": "message",
            "channels": channel_id,
            "username": self.username,
            "content": message_content
        }
        bytes_packet = json.dumps(message_packet).encode('utf-8')
        
        # Debug info
        with self.connections_lock:
            for conn in self.connections:
                try:
                    conn.sendall(bytes_packet)
                except Exception:
                    pass

    def add_connection(self, conn, addr):
        with self.connections_lock:
            if addr not in self.connected_peers_info:
                self.connections.append(conn)
                self.connected_peers_info.add(addr)
            else:
                conn.close()
                
    def remove_connection(self, conn, addr):
        with self.connections_lock:
            if conn in self.connections:
                self.connections.remove(conn)
            if addr and addr in self.connected_peers_info:
                self.connected_peers_info.remove(addr)
            conn.close()
            
    def send_http_request_manually(self, method, path, body_data=None):
        # 1. Tách host và port từ self.tracker_url
        host = "localhost"
        port = 8000
        
        # 2. Tạo socket và kết nối
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, port))
        
        # 3. Chuẩn bị body và headers
        body_str = ""
        if body_data:
            # Chuyển dict {'user':'a', 'pass':'b'} thành 'user=a&pass=b'
            body_str = "&".join(f"{k}={v}" for k, v in body_data.items())
        
        # 4. Build chuỗi HTTP Request "thô"
        request_lines = [
            f"{method} {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Connection: close",
            f"Cookie: {self.auth_cookie}" if self.auth_cookie else "", # Đã sửa
            f"Content-Type: application/x-www-form-urlencoded" if body_data else "",
            f"Content-Length: {len(body_str)}" if body_data else "",
            "",
            body_str
        ]
        
        request_raw = "\r\n".join(line for line in request_lines if line).encode('utf-8')
        client_socket.sendall(request_raw)
        
        response_raw = b""
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            response_raw += chunk
        
        client_socket.close()

        headers_raw, body_content = response_raw.split(b'\r\n\r\n', 1)
        status_line = headers_raw.split(b'\r\n', 1)[0]
        status_code = int(status_line.split(b' ')[1])
        
        # Cập nhật cookie cho lần gọi sau
        # (Logic này cần làm kỹ hơn: tìm header 'Set-Cookie')
        return status_code, headers_raw.decode('utf-8'), body_content

    # BƯỚC 2 (MỚI): Đăng nhập và LƯU COOKIE
    def login_to_tracker(self, username, password):
        payload = {"username": username, "password": password}
        
        status_code, headers_str, body = self.send_http_request_manually("POST", "/login", body_data=payload)

        if status_code == 200:
            # Tìm header 'Set-Cookie' trong đống header trả về
            for line in headers_str.split('\r\n'):
                if line.lower().startswith('set-cookie:'):
                    # Lấy giá trị cookie, ví dụ: "auth=true"
                    self.auth_cookie = line.split(':', 1)[1].strip().split(';', 1)[0]
                    print(f"[Peer] Login success, got cookie: {self.auth_cookie}")
                    return True
        print("[Peer] Login failed")
        return False

    # BƯỚC 3 (MỚI): Đăng ký (dùng cookie đã lưu)
    def submit_info_to_tracker(self):
        submit_ip = 'localhost' if self.my_host == '0.0.0.0' else self.my_host
        payload = {
            "ip": submit_ip,
            "port": self.my_port
        }
        
        status_code, headers, body = self.send_http_request_manually("POST", "/submit-info", body_data=payload)
        
        if status_code == 200:
            print("[Peer] Submitted info to tracker.")
            return True
        print("[Peer] Failed to submit info.")
        return False
        
    # BƯỚC 4 (MỚI): Lấy danh sách (dùng cookie đã lưu)
    def get_peer_list(self):
        status_code, headers, body = self.send_http_request_manually("GET", "/get-list")
        
        if status_code == 200:
            try:
                peers = json.loads(body.decode('utf-8'))
                peer_tuple_list = [tuple(peer) for peer in peers]
                return peer_tuple_list
            except json.JSONDecodeError:
                print("[Peer] Failed to parse peer list JSON.")
                return None
        return None

    def shutdown(self):
        self.running = False
        with self.connections_lock:
            for conn in self.connections:
                conn.close()
        self.peer_server_socket.close()
      
GLOBAL_PEER_INSTANCE = None
GLOBAL_UI_QUEUE = Queue()      
  
class PeerAPIHandler(BaseHTTPRequestHandler):
    """
    Xử lý các request HTTP từ UI (chat.html).
    Chạy trên cổng 9001.
    """
    
    def do_OPTIONS(self):
        """Xử lý CORS pre-flight"""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Xử lý GET /messages (Long Polling)"""
        if self.path == '/messages':
            try:
                # Lấy tin nhắn từ hàng đợi (hàm .get() sẽ block cho đến khi có tin)
                message_text = GLOBAL_UI_QUEUE.get(timeout=30) # 30s timeout
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {'text': message_text}
                self.wfile.write(json.dumps(response).encode('utf-8'))
            except Empty:
                # Không có tin nhắn sau 30s, gửi response rỗng
                self.send_response(204) # 204 No Content
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self):
        """Xử lý POST /send"""
        if self.path == '/send':
            try:
                content_len = int(self.headers.get('Content-Length'))
                post_body = self.rfile.read(content_len)
                data = json.loads(post_body)
                
                # Lấy tin nhắn và gọi hàm broadcast P2P
                channel = data['channel']
                message = data['message']
                if GLOBAL_PEER_INSTANCE:
                    GLOBAL_PEER_INSTANCE.broadcast_message(message, channel)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404)

def run_api_server(port=9001):
    """Chạy API server trong một luồng riêng."""
    try:
        server_address = ('', port)
        httpd = HTTPServer(server_address, PeerAPIHandler)
        print(f"[API Server] Đang chạy trên http://localhost:{port}...")
        httpd.serve_forever()
    except Exception as e:
        print(f"[API Server] Lỗi: {e}")
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2P Chat Client")
    parser.add_argument('--username', required=True, help="Tên của bạn")
    parser.add_argument('--port', type=int, required=True, help="Port bạn muốn mở để P2P (ví dụ: 9002)")
    parser.add_argument('--api-port', type=int, default=9001, help="Port để UI (chat.html) gọi API (ví dụ: 9001)")
    parser.add_argument('--tracker', default="http://localhost:8080", help="URL của Proxy/Tracker (ví dụ: 8080)")
    args = parser.parse_args()
    GLOBAL_PEER_INSTANCE = Peer(
        tracker_url=args.tracker,
        my_host='0.0.0.0', 
        my_port=args.port,
        username=args.username,
        ui_queue=GLOBAL_UI_QUEUE
    )
    GLOBAL_PEER_INSTANCE.start()
    api_thread = threading.Thread(target=run_api_server, args=(args.api_port,), daemon=True)
    api_thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        GLOBAL_PEER_INSTANCE.shutdown()
        sys.exit(0)