from urllib.parse import urlparse, unquote

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