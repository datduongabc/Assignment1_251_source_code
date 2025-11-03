"""
start_sampleapp
~~~~~~~~~~~~~~~~~

This module provides a sample RESTful web application using the WeApRous framework.

It defines basic route handlers and launches a TCP-based backend server to serve HTTP requests.
The application includes a login endpoint and a greeting endpoint, and can be configured via command-line arguments.
"""

import argparse
from daemon.weaprous import WeApRous
import threading

PORT = 8000  # Default port

app = WeApRous()

active_peers = []
peers_lock = threading.Lock()

@app.route('/login', methods=['POST'])
def login(headers, body):
    """
    Handle user login via POST request.

    This route simulates a login process and prints the provided headers and body
    to the console.

    :param headers (str): The request headers or user identifier.
    :param body (str): The request body or login payload.
    """
    print ("[SampleApp] Logging in {} to {}".format(headers, body))
    
    if body.get('username') == 'admin' and body.get('password') == 'password':
        print("[SampleApp] Login successful")
        return True
    else:
        print("[SampleApp] Login failed: Unauthorized")
        return False
    
@app.route('/submit-info', methods=['POST'])
def submit_info(headers, body):
    """
    Handle peer registration via POST request.
    Peers send their IP and Port to be added to the active list.
    """
    peer_ip = body.get('ip')
    peer_port = body.get('port')
    
    # Nếu body thiếu ip hoặc port thì trả về false
    if not peer_ip or not peer_port:
        print("[Task 2] Peer registration failed: Missing IP or Port")
        return False

    try:
        peer_info = (peer_ip, int(peer_port))
        with peers_lock:
            if peer_info not in active_peers:
                active_peers.append(peer_info)
                print("[Task 2] New peer registered:", peer_info)
            else:
                print("[Task 2] Peer already registered:", peer_info)
        print("[Task 2] Current active peers:", active_peers)
        return {"status": "success", "message": "Peer registered successfully"}
    except ValueError:
        print("[Task 2] Peer registration failed: Invalid Port")
        # Return false để httpadapter biết đó là 401
        return False
    except Exception as e:
        print("[Task 2] Error processing peer:", e)
        return {"status": "error", "message": str(e)}

@app.route('/get-list', methods=['GET'])
def get_list(headers, body):
    """
    Handle retrieval of the active peer list via GET request.
    """
    auth_cookie = headers.get('cookie', '')
    if "auth=true" not in auth_cookie:
        return False  # Return false để httpadapter biết đó là 401
    
    with peers_lock:
        data_to_send = list(active_peers)
    
    print("[Task 2] Sending active peer list:", data_to_send)
    return data_to_send

if __name__ == "__main__":
    # Parse command-line arguments to configure server IP and port
    parser = argparse.ArgumentParser(prog='Backend', description='', epilog='Beckend daemon')
    parser.add_argument('--server-ip', default='0.0.0.0')
    parser.add_argument('--server-port', type=int, default=PORT)
 
    args = parser.parse_args()
    ip = args.server_ip
    port = args.server_port

    # Prepare and launch the RESTful application
    app.prepare_address(ip, port)
    app.run()