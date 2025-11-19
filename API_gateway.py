import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from queue import Empty
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class API(BaseHTTPRequestHandler):    
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        peer_instance = self.server.peer_instance
        ui_queue = self.server.ui_queue

        try:
            if self.path == '/messages':
                message_text = ui_queue.get(timeout=2)
                
                sender = "Anonymous"
                text = message_text
                channel = "#general"
                
                if '|[' in message_text and ']: ' in message_text:
                    channel_part, rest = message_text.split('|[', 1)
                    channel = channel_part
                    if ']: ' in rest:
                        sender_part, content_part = rest.split(']: ', 1)
                        sender = sender_part
                        text = content_part
                response = {
                    'type': 'message',
                    'text': text,
                    'sender': sender,
                    'channel': channel,
                    'raw': message_text
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
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
                # Get peer status information
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                status = {
                    'logged_in': False, 'username': '', 'peer_count': 0, 'channels': []
                }
                
                if peer_instance:
                    with peer_instance.connections_lock:
                        active_peers = list(peer_instance.peers.keys())
                        total_peer_count = len(peer_instance.peers)
                    
                    formatted_peers = [{"ip": p[0], "port": p[1]} for p in active_peers]
                    status.update({
                        'logged_in': peer_instance.logged_in,
                        'username': peer_instance.username,
                        'peer_count': total_peer_count,
                        'current_channel': peer_instance.current_channel,
                        'connected_peers': formatted_peers
                    })
                self.wfile.write(json.dumps(status).encode('utf-8'))
            elif self.path == '/' or '/chat.html' in self.path:
                self.serve_chat_html()
            elif self.path.endswith('.css'):
                self.serve_chat_css()
            elif self.path.endswith('.js'):
                self.serve_chat_js()
            else:
                self.send_error(404)
        except Exception:
            self.send_error(500)
    
    def do_POST(self):
        peer_instance = self.server.peer_instance

        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_len) if content_len > 0 else b'{}'
            
            try:
                data = json.loads(post_body.decode('utf-8'))
            except json.JSONDecodeError:
                data = {}
            
            if self.path == '/send' or self.path == '/broadcast-peer':
                channel = data.get('channel', '#general')
                message = data.get('message', '')
                
                if not message.strip():
                    self.send_error(400, "Empty message")
                    return
                
                if peer_instance:
                    peer_instance.broadcast_message(message, channel)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))    
            elif self.path == '/join-channel':
                channel = data.get('channel')
                
                if peer_instance and channel:
                    peer_instance.current_channel = channel
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
                
            else:
                self.send_error(404)
        except Exception:
            self.send_error(500)
    
    def serve_chat_html(self):
        try:
            peer = self.server.peer_instance
            api_port = self.server.server_port
            username = peer.username if peer else "Anonymous"

            config_data = {
                "API_PORT": api_port,
                "USERNAME": username
            }
                    
            html_file = os.path.join(BASE_DIR, 'www', 'chat.html')
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            html_content = html_content.replace('__APP_CONFIG_JSON__', json.dumps(config_data))
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
        except Exception:
            self.send_error(404, "File Not Found")

    def serve_chat_css(self):
        try:
            css_file = os.path.join(BASE_DIR, 'static', 'css', 'chat.css')
            with open(css_file, 'r', encoding='utf-8') as f:
                css_content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/css; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(css_content.encode('utf-8'))
        except Exception:
            self.send_error(404, "File Not Found")
            
    def serve_chat_js(self):
        try:
            js_file = os.path.join(BASE_DIR, 'static', 'js', 'chat.js')
            with open(js_file, 'r', encoding='utf-8') as f:
                js_content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'application/javascript; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(js_content.encode('utf-8'))
        except Exception:
            self.send_error(404, "File Not Found")

class PeerHttpServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, peer_instance, ui_queue):
        self.peer_instance = peer_instance
        self.ui_queue = ui_queue
        super().__init__(server_address, RequestHandlerClass)

def run_api_server(port, peer_instance, ui_queue):
    try:
        server_address = ('0.0.0.0', port)
        httpd = PeerHttpServer(server_address, API, peer_instance, ui_queue)
        httpd.timeout = 1
        print("Listening on port {}".format(port))
        httpd.serve_forever()
    except OSError as e:
        if e.errno == 48:
            print("Error: Port {} is already in use.".format(port))
    except Exception:
        print("Unexpected error")