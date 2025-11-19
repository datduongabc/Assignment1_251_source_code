import socket
import threading
import json
import time
import argparse
from queue import Queue
from daemon.dictionary import CaseInsensitiveDict
from daemon.utils import send_http_request
from API_gateway import run_api_server

class Peer:
    def __init__(self, tracker, host, port, username, ui_queue):
        self.tracker = tracker
        self.host = host
        self.port = int(port)
        self.username = username
        
        self.auth_cookie = None
        self.logged_in = False
        self.peers = {}
        self.connections_lock = threading.Lock()
        
        self.ui_queue = ui_queue
        self.current_channel = '#general'
        self.subscribed_channels = ['#general', '#mmt', '#cnpm']
                
        self.running = True
        self.peer_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.peer_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.peer_server_socket.bind((self.host, self.port))
        
        self.port = self.peer_server_socket.getsockname()[1]
        
    def start(self):
        server_thread = threading.Thread(target=self.run_server_thread, daemon=True)
        server_thread.start()
        connect_thread = threading.Thread(target=self.run_connect_thread, daemon=True)
        connect_thread.start()
        
    def run_server_thread(self):
        self.peer_server_socket.listen(5)
        while self.running:
            try:
                conn, addr = self.peer_server_socket.accept()
                listener = threading.Thread(target=self.handle_peer_connections, args=(conn, addr), daemon=True)
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
                time.sleep(10)
                continue
            
            for peer_addr in peer_list:
                if not self.running:
                    break
                
                peer_addr_tuple = (peer_addr[0], int(peer_addr[1]))
                
                host = 'localhost' if self.host == '0.0.0.0' else self.host
                info = (host, self.port)
                if peer_addr_tuple == info:
                    continue
                    
                is_connected = False
                with self.connections_lock:
                    if peer_addr_tuple in self.peers:
                        is_connected = True
                        
                if not is_connected:
                    try:
                        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        peer_socket.settimeout(5)
                        peer_socket.connect(peer_addr_tuple)
                        self.add_connection(peer_socket, peer_addr_tuple)
                        listener = threading.Thread(target=self.handle_peer_connections, args=(peer_socket, peer_addr_tuple), daemon=True)
                        listener.start()
                    except Exception:
                        pass
            time.sleep(10)

    def handle_peer_connections(self, conn, addr):
        conn.settimeout(None)
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
                
            try:
                messages = data.decode('utf-8').strip().split('\n')
                
                for msg_str in messages:
                    if not msg_str.strip():
                        continue
                    
                    try:
                        message = json.loads(msg_str)
                        if message.get('type') == 'message':
                            channel_id = message.get('channels', '#general')
                            username = message.get('username', 'Anonymous')
                            content = message.get('content', '')
                            
                            if channel_id in self.subscribed_channels:
                                formatted_msg = "{}|[{}]: {}".format(channel_id, username, content)
                                self.ui_queue.put(formatted_msg)
                    except json.JSONDecodeError:
                        print("Decoded message to JSON unsuccessfully")
            except Exception:
                print("Handling peer message unsuccessfully")
                
        self.remove_connection(conn, addr)

    def add_connection(self, conn, addr):
        with self.connections_lock:
            if addr not in self.peers:
                self.peers[addr] = conn
                print("Added connection {}. Total connections: {}".format(addr, len(self.peers)))
            else:
                conn.close()
                
    def remove_connection(self, conn, addr):
        with self.connections_lock:
            if addr in self.peers:
                del self.peers[addr]
                print("Removed connection {}. Total connections: {}".format(addr, len(self.peers)))
            try:
                conn.close()
            except:
                pass

    def login_to_tracker(self, username, password):
        payload = {"username": username, "password": password}
        
        try:
            status_code, headers, body = send_http_request(self.tracker, "POST", "/login", body_data=payload, auth_cookie=None)

            if status_code == 200:
                response_headers = CaseInsensitiveDict()
                if headers:
                    for line in headers.split('\r\n')[1:]:
                        if ': ' in line:
                            key, val = line.split(': ', 1)
                            response_headers[key] = val
                    
                    set_cookie = response_headers.get('Set-Cookie')
                    if set_cookie and 'auth=true' in set_cookie:
                        self.auth_cookie = set_cookie.split(';')[0].strip()
                        self.logged_in = True
                        print("Login successfully, session cookie: {}".format(self.auth_cookie))
                        return True
                    else:
                        print("Login unsuccessfully")
                        self.logged_in = False
                        return False
            else:
                print("Login unsuccessfully: status code {}".format(status_code))
        except Exception as e:
            print("Login to tracker unsuccessfully: {}".format(e))

        self.logged_in = False
        return False

    def submit_info_to_tracker(self):
        if not self.logged_in:
            return False
            
        payload = {
            "ip": 'localhost' if self.host == '0.0.0.0' else self.host,
            "port": self.port,
            "username": self.username
        }
        
        try:
            status_code, headers, body = send_http_request(self.tracker, "POST", "/submit-info", body_data=payload, auth_cookie=self.auth_cookie)
            if status_code == 200:
                print("Successfully registered to tracker")
                return True
            else:
                print("Unsuccessfully registered to tracker: status code {}".format(status_code))
                return False
        except Exception:
            print("Unsuccessfully registered to tracker")
            return False

    def get_peer_list(self):
        if not self.logged_in:
            return None

        try:
            status_code, headers, body = send_http_request(self.tracker, "GET", "/get-list", body_data=None, auth_cookie=self.auth_cookie)
            
            if status_code == 200:
                try:
                    body_str = body.decode('utf-8')
                    peers_data = json.loads(body_str)
                    
                    if isinstance(peers_data, list):
                        peer_tuple_list = []
                        for peer in peers_data:
                            if isinstance(peer, (list, tuple)) and len(peer) >= 2:
                                peer_tuple_list.append((peer[0], int(peer[1])))
                        return peer_tuple_list
                except json.JSONDecodeError as e:
                    print("Failed to decode peer list JSON: {}".format(e))
                    return None
            else:
                print("Failed to get peer list: status code {}".format(status_code))
                return None
        except Exception:
            print("Failed to get peer list")
            return None
        
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
            target_conn = self.peers.get(target_peer)
            
            if target_conn:
                try:
                    target_conn.sendall(bytes_packet)
                    return True
                except Exception:
                    return False
        return False
    
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
        
        with self.connections_lock:
            active_items = list(self.peers.items())
        
        for addr, conn in active_items:
            try:
                conn.sendall(bytes_packet)
            except Exception:
                self.remove_connection(conn, addr)
    
    def shutdown(self):
        self.running = False
        
        with self.connections_lock:
            for conn in self.peers.values():
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
                except:
                    pass
            self.peers.clear()

        try:
            dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dummy_socket.connect(('localhost' if self.host == '0.0.0.0' else self.host, self.port))
            dummy_socket.close()
        except:
            pass
        
        try:
            self.peer_server_socket.close()
        except:
            pass
      
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--username', required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--api-port', type=int, default=0)
    parser.add_argument('--tracker', default="http://localhost:8080")
    
    args = parser.parse_args()
    
    # Random port
    if args.api_port == 0:
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_sock.bind(('0.0.0.0', 0))
        args.api_port = temp_sock.getsockname()[1]
        temp_sock.close()
    
    ui_queue = Queue()      
    api_thread = None

    peer_instance = Peer(tracker=args.tracker, host='0.0.0.0', port=args.port, username=args.username, ui_queue=ui_queue)    
    
    try:
        peer_instance.start()
        print("Name:     {}".format(args.username))
        print("P2P Port: {}".format(peer_instance.port))
        print("UI URL:   http://localhost:{}/chat.html".format(args.api_port))
        
        api_thread = threading.Thread(target=run_api_server, args=(args.api_port, peer_instance, ui_queue), daemon=True)
        api_thread.start()
        
        while True:
            time.sleep(1)
            if not api_thread.is_alive():
                break
            
    except KeyboardInterrupt:
        print("Shutting down")
    except Exception:
        print("Error occurred")
    finally:
        if peer_instance:
            peer_instance.shutdown()