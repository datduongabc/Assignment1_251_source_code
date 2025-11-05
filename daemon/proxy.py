import socket
import threading
from .utils import raw_data_to_msg

HOST_COUNTERS = {}
COUNTERS_LOCK = threading.Lock()

def forward_request(host, port, request):
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        backend.connect((host, port))
        backend.sendall(request.encode('utf-8'))
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
    proxy_pass_list, dist_policy = routes.get(hostname,([], 'round-robin'))
    if isinstance(proxy_pass_list, list):
        if len(proxy_pass_list) == 0:
            print("{} has no backend".format(hostname))
            return None, None
        elif len(proxy_pass_list) == 1:
            print("{} has one backend".format(hostname))
            proxy_host, proxy_port = proxy_pass_list[0].split(":", 1)
        else:
            print("{} has multiple backends".format(hostname))
            # Default to RoundRobin
            with COUNTERS_LOCK:
                current_index = HOST_COUNTERS.get(hostname, 0)
                selected_backend = proxy_pass_list[current_index]
                proxy_host, proxy_port = selected_backend.split(":", 1)
                new_index = (current_index + 1) % len(proxy_pass_list)
                HOST_COUNTERS[hostname] = new_index
                print(f"[Proxy] RoundRobin: {hostname} -> index {current_index} ({selected_backend})")
    else:
        proxy_host, proxy_port = proxy_pass_list.split(":", 1)
    return proxy_host, proxy_port

def handle_client(ip, port, conn, addr, routes):
    msg = raw_data_to_msg(conn)
    headers = msg.split('\r\n\r\n', 1)[0]
    hostname = "unknown"
    for line in headers.splitlines():
        if line.lower().startswith('host:'):
            hostname = line.split(':', 1)[1].strip()
            break
    print("{} at host: {}".format(addr, hostname))
    proxy_host, proxy_port = resolve_routing_policy(hostname, routes)
    if proxy_host and proxy_port is not None:
        proxy_port = int(proxy_port)
        print("Host {} forwards to {}:{}".format(hostname, proxy_host, proxy_port))
        response = forward_request(proxy_host, proxy_port, msg)
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
    run_proxy(ip, port, routes)