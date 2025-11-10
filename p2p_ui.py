import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from queue import Empty
import os

# Lớp Handler này xử lý tất cả các request HTTP đến từ giao diện web (chat.html)
class PeerAPIHandler(BaseHTTPRequestHandler):
    
    # Lấy peer_instance và ui_queue từ server thay vì dùng global
    def get_peer_instance(self):
        return self.server.peer_instance

    def get_ui_queue(self):
        return self.server.ui_queue

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests"""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Handle GET requests for various endpoints"""
        peer_instance = self.get_peer_instance()
        ui_queue = self.get_ui_queue()

        try:
            if self.path == '/messages':
                # Long polling for new messages - Notification system
                try:
                    message_text = ui_queue.get(timeout=2)
                    
                    if message_text.startswith("CHANNEL_PEER_UPDATE|"):
                        parts = message_text.split("|")
                        response = {
                            'type': 'channel_peer_update',
                            'channel': parts[1],
                            'peer_count': int(parts[2]),
                            'text': '{}: {} peers'.format(parts[1], parts[2]),
                            'sender': 'System'
                        }
                    else:
                        sender = "Unknown"
                        text = message_text
                        
                        if '|[' in message_text and ']: ' in message_text:
                            parts = message_text.split('|[', 1)
                            if len(parts) == 2:
                                rest = parts[1]
                                if ']: ' in rest:
                                    sender_part, content_part = rest.split(']: ', 1)
                                    sender = sender_part
                                    text = content_part
                        
                        response = {
                            'type': 'message',
                            'text': text,
                            'sender': sender,
                            'raw': message_text
                        }
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                except Empty:
                    # No message after timeout
                    self.send_response(204)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
            elif self.path == '/channels':
                # Channel listing
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                channels = peer_instance.subscribed_channels if peer_instance else []
                response = {'channels': channels}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            elif self.path == '/peers':
                # Get list of connected peers
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                peers = []
                if peer_instance:
                    with peer_instance.connections_lock:
                        peers = list(peer_instance.connected_peers_info)
                        
                response = {'connected_peers': [{"ip": peer[0], "port": peer[1]} for peer in peers]}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            elif self.path == '/status':
                # Get peer status information
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                status = {
                    'logged_in': False, 'username': '', 'peer_count': 0, 'channels': []
                }
                
                if peer_instance:
                    total_peer_count = len(peer_instance.connected_peers_info)
                    status.update({
                        'logged_in': peer_instance.logged_in,
                        'username': peer_instance.username,
                        'peer_count': total_peer_count,
                        'current_channel': peer_instance.current_channel,
                        'channels': peer_instance.subscribed_channels
                    })
                    
                self.wfile.write(json.dumps(status).encode('utf-8'))
                
            elif self.path == '/' or self.path == '/chat.html' or self.path == '/www/chat.html':
                self.serve_chat_html()
            elif self.path == '/chat.css' or self.path == '/static/css/chat.css':
                self.serve_chat_css()
            elif self.path == '/chat.js' or self.path == '/static/js/chat.js':
                self.serve_chat_js()
            else:
                self.send_error(404)
        except Exception:
            self.send_error(500)

    def do_POST(self):
        """Handle POST requests for various endpoints"""
        peer_instance = self.get_peer_instance()

        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_len) if content_len > 0 else b'{}'
            
            try:
                body_str = post_body.decode('utf-8')
                data = json.loads(body_str)
            except json.JSONDecodeError:
                data = {}
            
            if self.path == '/send' or self.path == '/broadcast-peer':
                channel = data.get('channel', '#general')
                message = data.get('message', '')
                
                if not message.strip():
                    self.send_error(400, "Message cannot be empty")
                    return
                
                if peer_instance:
                    peer_instance.broadcast_message(message, channel)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response_data = {"status": "ok"}
                self.wfile.write(json.dumps(response_data).encode('utf-8'))
                
            elif self.path == '/send-peer':
                target_ip = data.get('target_ip')
                target_port = data.get('target_port')
                message = data.get('message', '')
                channel = data.get('channel', '#general')
                
                if not all([target_ip, target_port, message.strip()]):
                    self.send_error(400, "Missing required fields")
                    return
                
                success = False
                if peer_instance:
                    target_peer = (target_ip, int(target_port))
                    success = peer_instance.send_to_peer(target_peer, message, channel)
                
                self.send_response(200 if success else 404)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {"status": "ok" if success else "peer not found"}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            elif self.path == '/connect-peer':
                target_ip = data.get('target_ip')
                target_port = data.get('target_port')
                
                if not all([target_ip, target_port]):
                    self.send_error(400, "Missing required fields")
                    return
                
                success = False
                if peer_instance:
                    success = peer_instance.connect_peer_via_tracker(target_ip, int(target_port))
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {"status": "ok" if success else "failed"}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            elif self.path == '/join-channel':
                channel = data.get('channel')
                
                if not channel or not channel.startswith('#'):
                    self.send_error(400, "Invalid channel name")
                    return
                
                if peer_instance:
                    peer_instance.current_channel = channel
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                total_peer_count = len(peer_instance.connections) + 1 if peer_instance else 1
                self.wfile.write(json.dumps({
                    "status": "ok", 
                    "channel": channel,
                    "peer_count": total_peer_count
                }).encode('utf-8'))
                
            else:
                self.send_error(404)
                
        except Exception:
            print("Error in POST", file=sys.stderr)
            self.send_error(500)
    
    def serve_chat_html(self):
        """Serve the chat HTML page with dynamic API port configuration"""
        try:
            # Lấy thông tin từ peer_instance
            peer = self.get_peer_instance()
            api_port = self.server.server_port
            username = peer.username

            # Tạo JSON config
            config_data = {
                "API_PORT": api_port,
                "USERNAME": username
            }
            config_json = json.dumps(config_data)

            html_file = os.path.join(os.path.dirname(__file__), 'www', 'chat.html')
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            html_content = html_content.replace(
                '__APP_CONFIG_JSON__',
                config_json
            )
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))

        except Exception:
            print("Error serving HTML", file=sys.stderr)
            self.send_error(500)

    def serve_chat_css(self):
        """Serve the chat CSS file"""
        try:
            css_file = os.path.join(os.path.dirname(__file__), 'static', 'css', 'chat.css')
            with open(css_file, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/css; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(css_content.encode('utf-8'))
            
        except Exception:
            print("Error serving CSS", file=sys.stderr)
            self.send_error(500)
            
    def serve_chat_js(self):
        """Serve the chat JavaScript file"""
        try:
            js_file = os.path.join(os.path.dirname(__file__), 'static', 'js', 'chat.js')
            with open(js_file, 'r', encoding='utf-8') as f:
                js_content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/javascript; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(js_content.encode('utf-8'))
            
        except Exception:
            print("Error serving JS", file=sys.stderr)
            self.send_error(500, "Internal Server Error")

# Lớp Server tùy chỉnh để giữ tham chiếu đến peer_instance và ui_queue
class PeerHttpServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, peer_instance, ui_queue):
        self.peer_instance = peer_instance
        self.ui_queue = ui_queue
        super().__init__(server_address, RequestHandlerClass)

def run_api_server(port, peer_instance, ui_queue):
    """
    Run HTTP API server for peer operations
    """
    try:
        server_address = ('', port)
        # Sử dụng PeerHttpServer tùy chỉnh
        httpd = PeerHttpServer(server_address, PeerAPIHandler, peer_instance, ui_queue)
        httpd.timeout = 1
        print("Listening on port {}".format(port))
        httpd.serve_forever()
    except OSError as e:
        if e.errno == 48:
            print("Error: Port {} is already in use.".format(port), file=sys.stderr)
        else:
            print("Network error", file=sys.stderr)
    except Exception:
        print("Unexpected error", file=sys.stderr)