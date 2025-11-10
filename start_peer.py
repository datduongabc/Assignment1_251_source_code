import socket
import threading
import json
import time
import argparse
from queue import Queue
from daemon.dictionary import CaseInsensitiveDict
from daemon.utils import send_http_request
from p2p_ui import run_api_server

class Peer:
    def __init__(self, tracker_url, my_host, my_port, username, ui_queue):
        self.tracker_url = tracker_url
        self.my_host = my_host
        self.my_port = int(my_port)
        self.username = username
        # Hàng đợi để gửi tin nhắn đến UI
        self.ui_queue = ui_queue
        self.subscribed_channels = ['#general', '#mmt', '#cnpm']
        self.current_channel = '#general'
        self.running = True
        # Danh sách chứa các socket đến các peer khác
        self.connections = []
        # Dùng set để lưu (ip, port) tránh kết nối trùng lặp
        self.connected_peers_info = set()
        # Lock để bảo vệ danh sách connections khi nhiều luồng truy cập
        self.connections_lock = threading.Lock()
        self.auth_cookie = None
        self.logged_in = False
        # Tạo socket server để lắng nghe kết nối từ các peer khác
        self.peer_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.peer_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.peer_server_socket.bind((self.my_host, self.my_port))
        
    def start(self):
        # Bắt đầu server socket để lắng nghe kết nối từ peer khác
        server_thread = threading.Thread(target=self.run_server_thread, daemon=True)
        server_thread.start()
        
        # Thread để kết nối với centralized server và các peer khác
        connect_thread = threading.Thread(target=self.run_connect_thread, daemon=True)
        connect_thread.start()
        
    def run_server_thread(self):
        self.peer_server_socket.listen(5)
        while self.running:
            try:
                conn, addr = self.peer_server_socket.accept()                
                listener = threading.Thread(target=self.handle_peer_messages, args=(conn, addr), daemon=True)
                listener.start()
            except Exception:
                if self.running:
                    time.sleep(1)
                else:
                    break
                
    def run_connect_thread(self):
        if not self.login_to_tracker('admin', 'password'):
            return
        if not self.submit_info_to_tracker():
            return

        while self.running:
            peer_list = self.get_peer_list()
            if peer_list is None:
                print("Failed to get peer list")
                time.sleep(15)
                continue
                
            my_connectable_ip = 'localhost' if self.my_host == '0.0.0.0' else self.my_host
            my_info = (my_connectable_ip, self.my_port)
            
            # Connection setup: initiate direct P2P connections
            for peer_addr in peer_list:
                if not self.running:
                    break
                # Đảm bảo peer_addr là tuple (ip, port)
                if not (isinstance(peer_addr, (list, tuple)) and len(peer_addr) == 2):
                    continue
                
                peer_addr_tuple = (peer_addr[0], int(peer_addr[1]))
                
                if peer_addr_tuple == my_info:
                    continue
                    
                is_connected = False
                with self.connections_lock:
                    if peer_addr_tuple in self.connected_peers_info:
                        is_connected = True
                        
                if not is_connected:
                    try:
                        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        peer_socket.settimeout(5)
                        peer_socket.connect(peer_addr_tuple)
                        self.add_connection(peer_socket, peer_addr_tuple)
                        listener = threading.Thread(target=self.handle_peer_messages, args=(peer_socket, peer_addr_tuple), daemon=True)
                        listener.start()
                    except Exception:
                        print("Login Error")
                        
            time.sleep(15)  # Check for new peers every 15 seconds

    def handle_peer_messages(self, conn, addr):
        conn.settimeout(None)
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
                
            try:
                data_str = data.decode('utf-8')
                messages = data_str.strip().split('\n')
                
                for msg_str in messages:
                    if not msg_str.strip():
                        continue
                    
                    try:
                        message = json.loads(msg_str)
                        
                        if message.get('type') == 'message':
                            channel_id = message.get('channels', '#general')
                            username = message.get('username', 'Unknown')
                            content = message.get('content', '')
                            
                            if channel_id in self.subscribed_channels:
                                formatted_msg = f"{channel_id}|[{username}]: {content}"
                                self.ui_queue.put(formatted_msg)
                    except json.JSONDecodeError:
                        continue
            except Exception:
                print("Error handling peer message")
                
        self.remove_connection(conn, addr)
        print("Stopped handling messages from {}".format(addr))

    def broadcast_message(self, message_content, channel_id='#general'):
        if not message_content.strip():
            return
            
        message_packet = {
            "type": "message",
            "channels": channel_id,
            "username": self.username,
            "content": message_content.strip(),
            "timestamp": time.time()
        }
        
        message_json = json.dumps(message_packet) + '\n'
        bytes_packet = message_json.encode('utf-8')
        
        sent_count = 0
        failed_count = 0
        
        with self.connections_lock:
            # Tạo bản sao để tránh lỗi "RuntimeError: dictionary changed size during iteration"
            connections_copy = list(self.connections)
            
        for conn in connections_copy:
            try:
                conn.sendall(bytes_packet)
                sent_count += 1
            except Exception:
                failed_count += 1
                # Xóa kết nối hỏng
                self.remove_connection(conn, conn.getpeername() if hasattr(conn, 'getpeername') else None)

        print("Broadcast complete: sent to {} peers, {} failed.".format(sent_count, failed_count))

    def add_connection(self, conn, addr):
        with self.connections_lock:
            if addr not in self.connected_peers_info:
                self.connections.append(conn)
                self.connected_peers_info.add(addr)
                print("Added connection from {}. Total connections: {}".format(addr, len(self.connections)))
            else:
                # Đã kết nối, đóng socket mới
                conn.close()
                
    def remove_connection(self, conn, addr):
        with self.connections_lock:
            if conn in self.connections:
                self.connections.remove(conn)
            if addr and addr in self.connected_peers_info:
                self.connected_peers_info.remove(addr)
                print("Removed connection {}. Total connections: {}".format(addr, len(self.connections)))
            try:
                conn.close()
            except:
                pass # Bỏ qua lỗi nếu socket đã đóng
            
    def send_to_peer(self, target_peer, message_content, channel_id='#general'):
        message_packet = {
            "type": "message",
            "channels": channel_id,
            "username": self.username,
            "content": message_content.strip(),
            "timestamp": time.time()
        }
        
        message_json = json.dumps(message_packet) + '\n'
        bytes_packet = message_json.encode('utf-8')
        
        with self.connections_lock:
            # Tìm socket tương ứng với target_peer
            target_conn = None
            for i, addr in enumerate(self.connected_peers_info):
                 if addr == target_peer and i < len(self.connections):
                    target_conn = self.connections[i]
                    break
            
            if target_conn:
                try:
                    target_conn.sendall(bytes_packet)
                    return True
                except Exception:
                    return False
        return False # Không tìm thấy peer

    def login_to_tracker(self, username, password):
        payload = {"username": username, "password": password}
        
        try:
            status_code, headers_str, body = send_http_request(self.tracker_url, "POST", "/login", body_data=payload, auth_cookie=None)

            if status_code == 200:
                response_headers = CaseInsensitiveDict()
                for line in headers_str.split('\r\n')[1:]:
                    if ': ' in line:
                        key, val = line.split(': ', 1)
                        response_headers[key] = val
                
                set_cookie = response_headers.get('Set-Cookie')
                if set_cookie:
                    self.auth_cookie = set_cookie.split(';')[0].strip()
                    self.logged_in = True
                    print("Login successful, session cookie: {}".format(self.auth_cookie))
                    return True
                
                self.logged_in = True
                return True
        except Exception:
            print("Login to tracker failed")

        self.logged_in = False
        return False

    def submit_info_to_tracker(self):
        if not self.logged_in:
            return False
            
        submit_ip = 'localhost' if self.my_host == '0.0.0.0' else self.my_host
        
        payload = {
            "ip": submit_ip,
            "port": self.my_port,
            "username": self.username
        }
        print("Submitting peer info to tracker: {}".format(payload))

        try:
            status_code, headers, body = send_http_request(self.tracker_url, "POST", "/submit-info", body_data=payload, auth_cookie=self.auth_cookie)
            
            if status_code == 200:
                print("Successfully registered to tracker")
                return True  
        except Exception:
            print("Failed to submit info to tracker")
            
        return False
        
    def get_peer_list(self):
        if not self.logged_in:
            return None
            
        try:
            status_code, headers, body = send_http_request(self.tracker_url, "GET", "/get-list", body_data=None, auth_cookie=self.auth_cookie)
            
            if status_code == 200:
                try:
                    body_str = body.decode('utf-8') if isinstance(body, bytes) else body
                    peers_data = json.loads(body_str)
                    
                    if isinstance(peers_data, list):
                        peer_tuple_list = []
                        for peer in peers_data:
                            if isinstance(peer, (list, tuple)) and len(peer) >= 2:
                                peer_tuple_list.append((peer[0], int(peer[1])))
                            elif isinstance(peer, dict):
                                ip = peer.get('ip')
                                port = peer.get('port')
                                if ip and port:
                                    peer_tuple_list.append((ip, int(port)))
                        return peer_tuple_list

                except json.JSONDecodeError:
                    print("Failed to decode peer list JSON")
        except Exception:
            print("Failed to get peer list")

        return None # Trả về None nếu có lỗi
        
    def connect_peer_via_tracker(self, target_ip, target_port):
        if not self.logged_in:
            return False
        payload = {
            "target_ip": target_ip, "target_port": target_port,
            "source_ip": self.my_host, "source_port": self.my_port
        }
        try:
            status_code, headers, body = send_http_request(self.tracker_url, "POST", "/connect-peer", body_data=payload, auth_cookie=self.auth_cookie)
            if status_code == 200:
                return True
        except Exception:
            print("Failed to request tracker to connect peer")
        return False
        
    def shutdown(self):
        self.running = False
        
        with self.connections_lock:
            for conn in self.connections:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
                except:
                    pass
            self.connections.clear()
            self.connected_peers_info.clear()
            
        try:
            # Tạo một kết nối giả đến server socket để nó thoát khỏi .accept()
            dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dummy_socket.connect(('localhost' if self.my_host == '0.0.0.0' else self.my_host, self.my_port))
            dummy_socket.close()
        except:
            pass
        
        try:
            self.peer_server_socket.close()
        except:
            pass
      
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="P2P Chat Peer - Distributed Chat Application",
    )
    
    parser.add_argument('--username', required=True, 
                       help="Your username for the chat")
    parser.add_argument('--port', type=int, required=True,
                       help="Port for P2P connections")
    parser.add_argument('--api-port', type=int, default=9001,
                       help="Port for HTTP API server")
    parser.add_argument('--tracker', default="http://localhost:8080",
                       help="URL of the centralized tracker server")
    
    args = parser.parse_args()
    
    # Hàng đợi (Queue) này là cầu nối giữa logic P2P và logic API
    ui_queue = Queue()      
    
    # Khởi tạo đối tượng Peer (logic)
    peer_instance = Peer(
        tracker_url=args.tracker,
        my_host='0.0.0.0',
        my_port=args.port,
        username=args.username,
        ui_queue=ui_queue
    )
    
    api_thread = None
    
    try:
        # 1. Bắt đầu logic P2P
        peer_instance.start()
        
        # 2. Bắt đầu server API (UI) trong một luồng riêng
        #    Truyền peer_instance và ui_queue vào
        api_thread = threading.Thread(
            target=run_api_server, 
            args=(args.api_port, peer_instance, ui_queue),
            daemon=True,
            name="APIServer"
        )
        api_thread.start()
        
        while True:
            time.sleep(1)
            if not api_thread.is_alive():
                break
            
    except KeyboardInterrupt:
        print("Shutting down")
    except Exception:
        print("Error occurred, shutting down")
    finally:
        if peer_instance:
            peer_instance.shutdown()