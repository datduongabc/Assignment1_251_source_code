import socket
import threading
import time
import requests
import json

class Peer:
    def __init__(self, tracker_url, my_host, my_port, username):
        self.tracker_url = tracker_url
        self.my_host = my_host
        self.my_port = int(my_port)
        self.username = username
        # Danh sách chứa các socket đến các peer khác
        self.connections = []
        # Dùng set để lưu (ip, port) tránh kết nối trùng lặp
        self.connected_peers_info = set()
        # Lock để bảo vệ danh sách connections khi nhiều luồng truy cập
        self.connections_lock = threading.Lock()
        # HTTP Session để nói chuyện với Tracker
        self.http_session = requests.Session()
        # Tạo socket server để lắng nghe kết nối từ các peer khác
        self.peer_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.peer_server_socket.bind((self.my_host, self.my_port))
        print(f"[Peer] Khởi tạo server P2P tại {self.my_host}:{self.my_port}")
        
    def run_server_thread(self):
        self.peer_server_socket.listen(5)

        while True:
            try:
                conn, addr = self.peer_server_socket.accept()
                print(f"[Peer] Chấp nhận kết nối từ: {addr}")
                self.add_connection(conn, addr)
                
                listener_thread = threading.Thread(target=self.handle_peer_messages, args=(conn, addr), daemon=True)
                listener_thread.start()
            except Exception as e:
                print(f"[Peer] Lỗi khi chấp nhận kết nối: {e}")
                time.sleep(1)
                
    def add_connection(self, conn, addr):
        with self.connections_lock:
            if addr not in self.connected_peers_info:
                self.connections.append(conn)
                self.connected_peers_info.add(addr)
                print(f"[Peer] Đã thêm kết nối. Tổng số kết nối: {len(self.connections)}")
            else:
                print(f"[Peer] Đã có kết nối với {addr}. Đóng kết nối trùng lặp.")
                conn.close()

    def start(self):
        server_thread = threading.Thread(target=self.run_server_thread, daemon=True)
        server_thread.start()
        
        # 2. TODO: Đăng nhập Tracker (Task 1)
        if not self.login_to_tracker('admin', 'password'):
            return
        # 3. TODO: Đăng ký Tracker (Task 2)
        if not self.submit_info_to_tracker():
            return
        # 4. TODO: Bắt đầu Luồng 2 (Client - kết nối ĐI)
        client_thread = threading.Thread(target=self.connect_to_peers_thread, daemon=True)
        client_thread.start()
        # 5. TODO: Bắt đầu Luồng 3 (Input - gõ chat)
    
    # BƯỚC 2: Đăng nhập vào Tracker
    def login_to_tracker(self, username, password):
        login_url = f"{self.tracker_url}/login"
        payload = {
            "username": username,
            "password": password
        }
        
        try:
            response = self.http_session.post(login_url, data=payload)
            if response.status_code == 200:
                print("[Peer] Đăng nhập thành công vào Tracker.")
                return True
            else:
                print(f"[Peer] Đăng nhập thất bại: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("[Tracker] Lỗi: Không thể kết nối đến Tracker.")
            return False
    
    # BƯỚC 3: Đăng ký với Tracker  
    def submit_info_to_tracker(self):
        submit_url = f"{self.tracker_url}/submit-info"
        submit_ip = '127.0.0.1' if self.my_host == '0.0.0.0' else self.my_host
        payload = {
            "ip": submit_ip,
            "port": self.my_port
        }
        
        try:
            response = self.http_session.post(submit_url, data=payload)
            if response.status_code == 200:
                print("[Peer] Đăng ký thông tin thành công với Tracker.")
                return True
            else:
                print(f"[Peer] Đăng ký thông tin thất bại: {response.text}")
                return False
        except requests.exceptions.ConnectionError:
            print("[Tracker] Lỗi: Không thể kết nối đến Tracker khi đăng ký.")
            return False
        
    # BƯỚC 4: Lấy danh sách peer từ Tracker
    def get_peer_list(self):
        list_url = f"{self.tracker_url}/get-list"
        try:
            response = self.http_session.get(list_url)
            if response.status_code == 200:
                peers = response.json()
                peer_tuple_list = [tuple(peer) for peer in peers]
                return peer_tuple_list
            else:
                print(f"[Peer] Lấy danh sách peer thất bại: {response.status_code}")
                return None
        except requests.exceptions.ConnectionError:
            print("[Tracker] Lỗi: Không thể kết nối đến Tracker khi lấy danh sách.")
            return None
    
    # CHỦ ĐỘNG KẾT NỐI ĐẾN PEER KHÁC.
    def connect_to_peers_thread(self):
        # Đợi 5 giây để các peer khác kịp đăng ký
        time.sleep(5)
        
        peer_list = self.get_peer_list()
        if not peer_list:
            print("[Peer] Không nhận được danh sách peer. Bỏ qua kết nối.")
            return
        
        my_connectable_ip = '127.0.0.1' if self.my_host == '0.0.0.0' else self.my_host
        my_info = (my_connectable_ip, self.my_port)
        
        for peer_addr in peer_list:
            # Bỏ qua ip và port của mình
            if peer_addr == my_info:
                continue
            
            is_connected = False
            with self.connections_lock:
                if peer_addr in self.connected_peers_info:
                    is_connected = True
            
            if is_connected:
                continue
            
            try:
                print(f"[Peer] Đang kết nối đến {peer_addr}...")
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect(peer_addr)
                print(f"[Peer] Kết nối thành công đến {peer_addr}.")

                self.add_connection(peer_socket, peer_addr)
                
                listener_thread = threading.Thread(target=self.handle_peer_messages, args=(peer_socket, peer_addr), daemon=True)
                listener_thread.start()
            except Exception as e:
                print(f"[Peer] Lỗi khi kết nối đến {peer_addr}: {e}")
                
    # CHỜ USER GÕ TIN NHẮN.            
    def run_input_thread(self):
        while True:
            try:
                message = input("Bạn: ")
                if message == "/quit":
                    print("[Peer] Đang thoát...")
                    break
                if message:
                    self.broadcast_message(message)
            # Bấm Ctrl+D
            except EOFError:
                break
            # Bấm Ctrl+C
            except KeyboardInterrupt:
                break
        print("[Peer] Đã thoát vòng lặp input.")
    
    # LẮNG NGHE TIN NHẮN ĐẾN.
    # Một luồng này sẽ chạy cho MỖI kết nối peer.
    def handle_peer_messages(self, conn, addr):
        print(f"[Peer] Bắt đầu lắng nghe từ {addr}")
        # Đảm bảo socket không bị timeout
        conn.settimeout(None)
        
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    print(f"[Peer] Peer {addr} đã ngắt kết nối.")
                    break
                try:
                    message = json.loads(data.decode('utf-8'))
                    if message.get('type') == 'message':
                        print(f"\r[{message.get('username')}]: {message.get('content')}\nBạn: ", end="")
                except json.JSONDecodeError:
                    print(f"\r[Peer] Nhận được data lỗi từ {addr}\nBạn: ", end="")
        except ConnectionResetError:
             print(f"[Peer] Peer {addr} đã reset kết nối.")
        except Exception as e:
            print(f"[Peer] Lỗi với {addr}: {e}")
            
        self.remove_connection(conn, addr)
    
    # Hàm để xóa kết nối (thread-safe).
    def remove_connection(self, conn, addr):
        with self.connections_lock:
            if conn in self.connected_peers_info:
                self.connections.remove(conn)
            if addr in self.connected_peers_info:
                self.connected_peers_info.remove(addr)
            conn.close()
            print(f"[Peer] Đã xóa kết nối với {addr}. Tổng kết nối: {len(self.connections)}")

    # Gửi tin nhắn đến TẤT CẢ các peer đã kết nối.
    def broadcast_message(self, message_content):
        message_packet = {
            "type": "message",
            "username": self.username,
            "content": message_content
        }
        bytes_packet = json.dumps(message_packet).encode('utf-8')
        dead_connections = []
        
        with self.connections_lock:
            for conn in self.connections:
                try:
                    conn.sendall(bytes_packet)
                except Exception as e:
                    dead_connections.append(conn)

if __name__ == "__main__":
    TRACKER = "http://127.0.0.1:8080"
    MY_HOST = "0.0.0.0" 
    MY_PORT = input("Nhập port bạn muốn chạy:")
    MY_USERNAME = input("Nhập tên của bạn: ")
    
    peer = Peer(TRACKER, MY_HOST, MY_PORT, MY_USERNAME)
    peer.start()
    
    peer.run_input_thread()
    print("[Peer] Chương trình kết thúc.")