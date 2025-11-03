"""
daemon.proxy

This module implements a simple proxy server using Python's socket and threading libraries.
It routes incoming HTTP requests to backend services based on hostname mappings and returns the corresponding responses to clients.

Requirement:
-----------------
- socket: provides socket networking interface.
- threading: enables concurrent client handling via threads.
- response: customized :class: `Response <Response>` utilities.
- httpadapter: :class: `HttpAdapter <HttpAdapter >` adapter for HTTP request processing.
- dictionary: :class: `CaseInsensitiveDict <CaseInsensitiveDict>` for managing headers and cookies.
"""

import socket
import threading
HOST_COUNTERS = {}
COUNTERS_LOCK = threading.Lock()

def forward_request(host, port, request):
    """
    Forwards an HTTP request to a backend server and retrieves the response.

    :params host (str): IP address of the backend server.
    :params port (int): port number of the backend server.
    :params request (str): incoming HTTP request.

    :rtype bytes: Raw HTTP response from the backend server. If the connection fails, returns a 404 Not Found response.
    """

    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        backend.connect((host, port))
        backend.sendall(request.encode())
        response = b""
        while True:
            chunk = backend.recv(4096)
            if not chunk:
                break
            response += chunk
        return response
    except socket.error as e:
      print("Socket error: {}".format(e))
      return (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 13\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode('utf-8')


def resolve_routing_policy(hostname, routes):
    """
    Handles an routing policy to return the matching proxy_pass.
    It determines the target backend to forward the request to.

    :params host (str): IP address of the request target server.
    :params port (int): port number of the request target server.
    :params routes (dict): dictionary mapping hostnames and location.
    """

    proxy_map, policy = routes.get(hostname,([], 'round-robin'))
    proxy_host = None
    proxy_port = None
    
    if isinstance(proxy_map, list):
        if len(proxy_map) == 0:
            print("[Proxy] No backend found for host {}".format(hostname))
            return None, None
        elif len(proxy_map) == 1:
            print("[Proxy] {} points to a single backend".format(hostname))
            proxy_host, proxy_port = proxy_map[0].split(":", 2)
        else:
            if policy == 'round-robin':
                with COUNTERS_LOCK:
                    # 1. Get the current index
                    current_index = HOST_COUNTERS.get(hostname, 0)
                    # 2. Get the backend at index
                    selected_backend = proxy_map[current_index]
                    proxy_host, proxy_port = selected_backend.split(":", 2)
                    # Update index for next time
                    new_index = (current_index + 1) % len(proxy_map)
                    HOST_COUNTERS[hostname] = new_index
                    print(f"[Proxy] RoundRobin: {hostname} -> index {current_index} ({selected_backend})")
            else:
                print("[Proxy] Unknown policy {}, defaulting to first backend".format(policy))
                proxy_host, proxy_port = proxy_map[0].split(":", 2)
        return proxy_host, proxy_port

    else:
        print("[Proxy] resolve route of hostname {} is a singular to".format(hostname))
        proxy_host, proxy_port = proxy_map.split(":", 2)

    return proxy_host, proxy_port

def handle_client(ip, port, conn, addr, routes):
    """
    Handles an individual client connection by parsing the request, determining the target backend,
    and forwarding the request.

    The handler extracts the Host header from the request to matches the hostname against known routes.
    In the matching condition, it forwards the request to the appropriate backend.

    The handler sends the backend response back to the client or returns 404
    if the hostname is unreachable or is not recognized.

    :params ip (str): IP address of the proxy server.
    :params port (int): port number of the proxy server.
    :params conn (socket.socket): client connection socket.
    :params addr (tuple): client address (IP, port).
    :params routes (dict): dictionary mapping hostnames and location.
    """

    header_data = b""
    try:
        # 1. Đọc Header
        while b"\r\n\r\n" not in header_data:
            chunk = conn.recv(1024)
            if not chunk:
                break
            header_data += chunk
        
        header_text = header_data.decode('latin-1')
        body_data = b""

        if "\r\n\r\n" in header_text:
            header_part, body_part_initial = header_text.split("\r\n\r\n", 1)
            body_data = body_part_initial.encode('latin-1')
        else:
            header_part = header_text
        
        # 2. Lấy Content-Length
        temp_headers = {}
        hostname = "unknown"
        for line in header_part.split('\r\n')[1:]:
            if ': ' in line:
                key, val = line.split(': ', 1)
                temp_headers[key.lower()] = val
                if key.lower() == 'host':
                    hostname = val.strip()
        content_length = int(temp_headers.get('content-length', 0))
        
        # 3. Đọc Body
        while len(body_data) < content_length:
            chunk = conn.recv(1024)
            if not chunk:
                break
            body_data += chunk
        
        # 4. Ghép lại request (string)
        request_string = header_part + "\r\n\r\n" + body_data.decode('utf-8')
    except Exception as e:
        print(f"[Proxy] Lỗi khi đọc request: {e}")
        conn.close()
        return

    print("[Proxy] {} at Host: {}".format(addr, hostname))

    # Resolve the matching destination in routes and need convert port to integer value
    resolved_host, resolved_port = resolve_routing_policy(hostname, routes)
    try:
        resolved_port = int(resolved_port)
    except ValueError:
        print("Not a valid integer")
        resolved_host = None

    if resolved_host:
        print("[Proxy] Host name {} is forwarded to {}:{}".format(hostname,resolved_host, resolved_port))
        response = forward_request(resolved_host, resolved_port, request_string)        
    else:
        response = (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 13\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode('utf-8')
    conn.sendall(response)
    conn.close()

def run_proxy(ip, port, routes):
    """
    Starts the proxy server and listens for incoming connections. 

    The process binds the proxy server to the specified IP and port. In each incoming connection,
    it accepts the connections and spawns a new thread for each client using `handle_client`.

    :params ip (str): IP address to bind the proxy server.
    :params port (int): port number to listen on.
    :params routes (dict): dictionary mapping hostnames and location.
    """

    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        proxy.bind((ip, port))
        proxy.listen(50)
        print("[Proxy] Listening on IP {} port {}".format(ip,port))
        while True:
            conn, addr = proxy.accept()
            client_thread = threading.Thread(target=handle_client, args=(ip, port, conn, addr, routes))
            client_thread.start()
    except socket.error as e:
      print("Socket error: {}".format(e))

def create_proxy(ip, port, routes):
    """
    Entry point for launching the proxy server.

    :params ip (str): IP address to bind the proxy server.
    :params port (int): port number to listen on.
    :params routes (dict): dictionary mapping hostnames and location.
    """
    run_proxy(ip, port, routes)