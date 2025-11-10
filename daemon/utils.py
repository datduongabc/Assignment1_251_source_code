from urllib.parse import urlparse, unquote
from .dictionary import CaseInsensitiveDict
import socket

def get_auth_from_url(url):
    parsed = urlparse(url)
    try:
        auth = (unquote(parsed.username), unquote(parsed.password))
    except (AttributeError, TypeError):
        auth = ("", "")
    return auth

def raw_data_to_msg(conn):
    try:
        # 1. Read header
        header_byte = b""
        while b"\r\n\r\n" not in header_byte:
            # Return type is bytes
            chunk = conn.recv(1024)
            if not chunk:
                break
            header_byte += chunk
        header_string = header_byte.decode('latin-1')
        
        body_byte = b""
        if "\r\n\r\n" in header_string:
            headers, extra_data_after_headers = header_string.split("\r\n\r\n", 1)
            body_byte = extra_data_after_headers.encode('latin-1')
        else:
            headers = header_string
        
        # 2. Read Content-Length
        headers_dict = {}
        for line in headers.split('\r\n')[1:]:
            if ': ' in line:
                key, val = line.split(': ', 1)
                headers_dict[key.lower()] = val
        content_length = int(headers_dict.get('content-length', 0))
        
        # 3. Read Body
        while len(body_byte) < content_length:
            body_byte_remain = content_length - len(body_byte)
            chunk = conn.recv(min(4096, body_byte_remain))
            if not chunk:
                break
            body_byte += chunk
        bodies = body_byte.decode('utf-8')

        # 4. Request = headers + bodies
        return headers + "\r\n\r\n" + bodies
    except Exception:
        raise
    
def send_http_request(tracker_url, method, path, body_data=None, auth_cookie=None):
    try:
        parsed_url = urlparse(tracker_url)
        host = parsed_url.hostname or "localhost"
        port_from_url = parsed_url.port
        port = port_from_url if port_from_url else 8000
        
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(10)
        client_socket.connect((host, port))
        
        body_str = ""
        if body_data:
            if isinstance(body_data, dict):
                body_str = "&".join(f"{k}={v}" for k, v in body_data.items())
            else:
                body_str = str(body_data)
        
        headers = CaseInsensitiveDict()
        headers['Host'] = f"{host}:{port}"
        headers['Connection'] = 'close'
        headers['User-Agent'] = 'P2P-Peer/1.0'
        
        if auth_cookie:
            headers['Cookie'] = auth_cookie
        
        if body_data:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers['Content-Length'] = str(len(body_str))
        
        request_lines = ["{} {} HTTP/1.1".format(method.upper(), path)]
        for header, value in headers.items():
            request_lines.append(f"{header}: {value}")
        request_lines.extend(["", body_str])
        
        request_raw = "\r\n".join(line for line in request_lines).encode('utf-8')
        client_socket.sendall(request_raw)
        response_str = raw_data_to_msg(client_socket)
        client_socket.close()

        if '\r\n\r\n' not in response_str:
            return 500, "", b""
            
        headers_raw, body_content_str = response_str.split('\r\n\r\n', 1)
        status_line = headers_raw.split('\r\n', 1)[0]
        
        try:
            status_code = int(status_line.split(' ')[1])
        except (IndexError, ValueError):
            status_code = 500
        return status_code, headers_raw, body_content_str.encode('utf-8')
        
    except Exception:
        return 500, "", b""