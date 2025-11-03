import socket
import threading
import time
import requests
import json
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
import queue
import datetime

class ChatUI:
    def __init__(self, root, peer_logic, ui_queue):
        self.root = root
        self.peer = peer_logic
        self.ui_queue = ui_queue
        self.root.title(f"Chat P2P - {self.peer.username} ({self.peer.my_host}:{self.peer.my_port})")
        self.root.geometry("1280x720")
        
        # 1. Khung channel
        self.left_frame = tk.Frame(root, width=150)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        self.channel_label = tk.Label(self.left_frame, text="Các Kênh:")
        self.channel_label.pack()
        
        self.channel_list = tk.Listbox(self.left_frame, height=15)
        self.channel_list.pack(fill=tk.BOTH, expand=True)
        self.channel_list.bind('<<ListboxSelect>>', self.on_channel_select)
        
        # 2. Khung chat
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 3. Khung tin nhắn
        self.message_frame = tk.Frame(self.right_frame)
        self.msg_list = scrolledtext.ScrolledText(self.message_frame, wrap=tk.WORD, state='disabled')
        self.msg_list.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.message_frame.pack(fill=tk.BOTH, expand=True)
        
        self.msg_list.tag_config('me', foreground='blue', justify='right')
        self.msg_list.tag_config('peer', foreground='green')
        self.msg_list.tag_config('system', foreground='#777', font=('Arial', 9, 'italic'))
        self.msg_list.tag_config('error', foreground='red', font=('Arial', 9, 'bold'))

        # 4. Khung Input
        self.input_frame = tk.Frame(self.right_frame)
        self.input_entry = tk.Entry(self.input_frame, width=40, font=("Arial", 11))

        self.input_entry.bind("<Return>", self.on_send_message) 
        self.send_button = tk.Button(self.input_frame, text="Gửi", command=self.on_send_message)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=10)
        self.send_button.pack(side=tk.RIGHT, padx=10, pady=10)
        self.input_frame.pack(fill=tk.X)
        
        # 5. Logic khởi động
        self.active_channel = '#general'
        self.update_channel_list()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_queue()
        self.input_entry.focus_set()
    
    def on_send_message(self):
        """
        Called when the 'Send' button is pressed or "Enter" is pressed.
        """
        message = self.input_entry.get().strip()
        if message:
            try:
                self.peer.broadcast_message(message, self.active_channel)
                self.show_message(f"You: {message}", 'me')
                self.input_entry.delete(0, tk.END)
                self.input_entry.focus_set()  # Keep focus on input
            except Exception:
                self.show_message(f"Error sending message", 'error')
        else:
            self.input_entry.focus_set()
        return "break"
            
    def show_message(self, message, tag='peer'):
        """
        Display message on UI.
        """
        self.msg_list.config(state='normal')
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        self.msg_list.insert(tk.END, formatted_message, (tag,))
        
        if tag == 'me':
            self.msg_list.tag_config('me', foreground='blue')
        elif tag == 'peer':
            self.msg_list.tag_config('peer', foreground='green')
        elif tag == 'error':
            self.msg_list.tag_config('error', foreground='red')

        self.msg_list.config(state='disabled')
        # Auto scroll to bottom
        self.msg_list.yview(tk.END)
        
    def check_queue(self):
        """
        Check the queue to see if there are new messages (from the P2P stream).
        """
        try:
            message = self.ui_queue.get_nowait()
            # Check if the message belongs to the selected channel
            if '|' in message:
                channel, content = message.split('|', 1)
                if channel == self.active_channel:
                    self.show_message(content, 'peer')
            else:
                # Tin nhắn hệ thống hoặc lỗi
                self.show_message(message, 'peer')
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)
        
    def on_closing(self):
        """
        Handle when user clicks close window button.
        """
        if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
            self.peer.shutdown()
            self.root.destroy()
            
    def update_channel_list(self):
        """
        Update the channel list.
        """
        self.channel_list.delete(0, tk.END)
        for channel in self.peer.subscribed_channels:
            self.channel_list.insert(tk.END, channel)
            if channel == self.active_channel:
                self.channel_list.selection_set(tk.END)

    def on_channel_select(self):
        """
        Called when a user clicks on a channel.
        """
        try:
            selected_index = self.channel_list.curselection()[0]
            self.active_channel = self.channel_list.get(selected_index)
            self.root.title(f"Chat P2P - {self.peer.username} ({self.active_channel})")
            self.ui_queue.put(f"[System] Switched to channel {self.active_channel}")
        except IndexError:
            pass
    
class Peer:
    def __init__(self, tracker_url, my_host, my_port, username, ui_queue):
        self.tracker_url = tracker_url
        self.my_host = my_host
        self.my_port = int(my_port)
        self.username = username
        # Hàng đợi để gửi tin nhắn đến UI
        self.ui_queue = ui_queue
        # Hardcode các kênh có sẵn
        self.subscribed_channels = ['#general', '#mmt', '#cnpm', '#random']
        self.running = True
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
        time.sleep(2)
        peer_list = self.get_peer_list()
        if not peer_list:
            return
        
        my_connectable_ip = '127.0.0.1' if self.my_host == '0.0.0.0' else self.my_host
        my_info = (my_connectable_ip, self.my_port)
        
        for peer_addr in peer_list:
            if not self.running:
                break
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
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect(peer_addr)
                self.add_connection(peer_socket, peer_addr)
                listener = threading.Thread(target=self.handle_peer_messages, args=(peer_socket, peer_addr), daemon=True)
                listener.start()
            except Exception:
                pass
    
    #  One thread will run for each peer connection.
    def handle_peer_messages(self, conn, addr):
        # Đảm bảo socket không bị timeout
        conn.settimeout(None)
        try:
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
                        else:
                            pass
                except json.JSONDecodeError:
                    pass
        except Exception:
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
        dead_connections = []
        
        # Debug info
        with self.connections_lock:
            for conn in self.connections:
                try:
                    conn.sendall(bytes_packet)
                except Exception:
                    dead_connections.append(conn)
        # Cleanup dead connections
        for conn in dead_connections:
            self.remove_connection(conn, None)
                    
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
            try:
                conn.close()
            except:
                pass

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
                return True
            else:
                return False
        except requests.exceptions.ConnectionError:
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
                return True
            else:
                return False
        except requests.exceptions.ConnectionError:
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
                return None
        except requests.exceptions.ConnectionError:
            return None

    def shutdown(self):
        self.running = False
        with self.connections_lock:
            for conn in self.connections:
                conn.close()
        self.peer_server_socket.close()

if __name__ == "__main__":
    TRACKER = "http://127.0.0.1:8080"
    MY_HOST = "0.0.0.0"
    temp_root = tk.Tk()
    temp_root.withdraw()
    MY_PORT = simpledialog.askstring("Port", "Port:", parent=temp_root)
    MY_USERNAME = simpledialog.askstring("Name", "Name:", parent=temp_root)
    temp_root.destroy()
    
    if not MY_PORT or not MY_USERNAME:
        print("Port and name are required.")
    else:
        ui_message_queue = queue.Queue()
        peer = Peer(TRACKER, MY_HOST, MY_PORT, MY_USERNAME, ui_message_queue)
        peer.start()
        root = tk.Tk()
        app_ui = ChatUI(root, peer, ui_message_queue)
        # Ensure the input entry gets focus after window is fully loaded
        root.after(100, lambda: app_ui.input_entry.focus_set())
        root.mainloop()