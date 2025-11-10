import argparse
from daemon.weaprous import WeApRous
import threading

PORT = 8000

app = WeApRous()

active_peers = []
peers_lock = threading.Lock()

@app.route('/login', methods=['GET'])
def login_page(header, body):
    pass

@app.route('/login', methods=['POST'])
def login(header, body):
    try:
        if body.get('username') == 'admin' and body.get('password') == 'password':
            return True
        else:
            return False
    except Exception:
        return False
    
@app.route('/submit-info', methods=['POST'])
def submit_info(header, body):
    try:
        auth_cookie = header.get('cookie', '')
        if "auth=true" not in auth_cookie:
            return False
        peer_ip = body.get('ip')
        peer_port = body.get('port')
        if not peer_ip or not peer_port:
            return False
        peer_info = (peer_ip, int(peer_port))
        with peers_lock:
            if peer_info not in active_peers:
                active_peers.append(peer_info)
        return True
    except Exception:
        return False

@app.route('/get-list', methods=['GET'])
def get_list(header, body):
    try:
        auth_cookie = header.get('cookie', '')
        if "auth=true" not in auth_cookie:
            return False
        with peers_lock:
            # Create a copy instead of referencing
            data_to_send = list(active_peers)
        return data_to_send
    except Exception:
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='Backend', description='', epilog='Backend daemon')
    parser.add_argument('--server-ip', default='0.0.0.0')
    parser.add_argument('--server-port', type=int, default=PORT)
    args = parser.parse_args()
    ip = args.server_ip
    port = args.server_port
    app.prepare_address(ip, port)
    app.run()