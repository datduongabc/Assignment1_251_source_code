"""
daemon.httpadapter

This module provides a http adapter object to manage and persist http settings (headers, bodies).
The adapter supports both raw URL paths and RESTful route definitions, and integrates with Request and Response objects to handle client-server communication.
"""

from .request import Request
from .response import Response

class HttpAdapter:
    __attrs__ = [
        "ip",
        "port",
        "conn",
        "connaddr",
        "routes",
        "request",
        "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes
        self.request = Request()
        self.response = Response()

    def handle_client(self, conn, addr, routes):
        """
        Handle an incoming client connection.

        This method reads the request from the socket, prepares the request object,
        invokes the appropriate route handler if available, builds the response, and sends it back to the client.

        :param conn (socket): The client socket connection.
        :param addr (tuple): The client's address.
        :param routes (dict): The route mapping for dispatching requests.
        """

        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response

        # Handle the request
        header_data = b""
        try:
            while b"\r\n\r\n" not in header_data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                header_data += chunk
            # dùng 'latin-1' (theo chuẩn HTTP)
            header_text = header_data.decode('latin-1')
            body_data = b""
            if "\r\n\r\n" in header_text:
                header_part, body_part_initial = header_text.split("\r\n\r\n", 1)
                body_data = body_part_initial.encode('latin-1')
            else:
                header_part = header_text
            
            temp_headers = {}
            for line in header_part.split('\r\n')[1:]:
                if ': ' in line:
                    key, val = line.split(': ', 1)
                    temp_headers[key.lower()] = val
            content_length = int(temp_headers.get('content-length', 0))
            
            while len(body_data) < content_length:
                bytes_to_read = content_length - len(body_data)
                chunk = conn.recv(min(4096, bytes_to_read))
                if not chunk:
                    break
                body_data += chunk
            body_text = body_data.decode('utf-8')
            msg = header_part + "\r\n\r\n" + body_text
        except Exception as e:
            conn.close()
            return
        req.prepare(msg, routes)

        auth_cookie = req.cookies.get('auth', 'false')

        if auth_cookie != 'true' and req.path != "/login":
                response = resp.build_unauthorized()
                conn.sendall(response)
                conn.close()
                return

        logic_response = None
        # Handle request hook
        if req.hook:
            print("[HttpAdapter] hook in route-path METHOD {} PATH {}".format(req.hook._route_path,req.hook._route_methods))
            logic_response = req.hook(headers = req.headers, body = req.body)
            
        response = None
        
        if req.path == "/login" and req.method == "POST":
            if logic_response is True:
                resp.headers['Set-Cookie'] = 'auth=true'
                req.path = '/index.html'
            else:
                response = resp.build_unauthorized()
                conn.sendall(response)
                conn.close()
                return
        elif isinstance(logic_response, (dict, list)):
            # logic_response is dict
            response = resp.build_json_response(logic_response)
            conn.sendall(response)
            conn.close()
            return
        elif logic_response is False:
            response = resp.build_unauthorized()
            conn.sendall(response)
            conn.close()
            return
        # Build response default
        response = resp.build_response(req)
        conn.sendall(response)
        conn.close()