from .request import Request
from .response import Response
from .utils import raw_data_to_msg

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
        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response
        msg = raw_data_to_msg(conn)
        req.prepare(msg, routes)
        if not req.method:
            conn.close()
            return
        auth_cookie = req.cookies.get('auth', 'false')
        if req.path == "/login" or req.path == "/login.html":
            if req.method == "GET":
                req.path = '/login.html'
                response = resp.build_response(req)
            elif req.method == "POST":
                if req.hook:
                    API_return = req.hook(header=req.headers, body=req.body)
                if API_return != True:
                    response = resp.build_unauthorized()
                else:
                    resp.headers['Set-Cookie'] = 'auth=true'
                    req.path = '/index.html'
                    response = resp.build_response(req)
        elif req.path == "/" or req.path == "/index.html":
            if auth_cookie != 'true':
                response = resp.build_unauthorized()
            else:
                req.path = '/index.html'
                response = resp.build_response(req)
        elif req.path == "/submit-info":
            API_return = None
            if req.hook:
                API_return = req.hook(header=req.headers, body=req.body)
            if API_return == True:
                response = resp.build_json_response({"status": "success"})
            else:
                response = resp.build_json_response({"status": "failed"})
        elif req.path == "/get-list":
            API_return = None
            if req.hook:
                API_return = req.hook(header=req.headers, body=req.body)
            if isinstance(API_return, (dict, list)):
                response = resp.build_json_response(API_return)
            else:
                response = resp.build_json_response({"status": "failed"})
        elif req.path.startswith("/static/") or req.path.startswith("/css/") or req.path.startswith("/images/") or req.path.startswith("/js/"):
            response = resp.build_response(req)
        else:
            response = resp.build_notfound()
        conn.sendall(response)
        conn.close()
        return