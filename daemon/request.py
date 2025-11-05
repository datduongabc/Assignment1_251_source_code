from .dictionary import CaseInsensitiveDict

class Request():
    def __init__(self):
        #: HTTP verb to send to the server.
        self.method = None
        #: HTTP URL to send the request to.
        self.url = None
        #: dictionary of HTTP headers.
        self.headers = None
        #: HTTP path
        self.path = None        
        # The cookies set used to create Cookie header
        self.cookies = None
        #: request body to send to the server.
        self.body = None
        #: Routes
        self.routes = {}
        #: Hook point for routed mapped-path
        self.hook = None

    def extract_request_line(self, request):
        try:
            lines = request.splitlines()
            if not lines:
                return None, None, None
            first_line = lines[0]
            method, path, version = first_line.split()
            if path == '/':
                path = '/index.html'
        except Exception:
            return None, None, None
        return method, path, version
             
    def prepare_headers(self, request):
        lines = request.split('\r\n')
        headers = CaseInsensitiveDict()
        for line in lines[1:]:
            if ': ' in line:
                key, val = line.split(': ', 1)
                headers[key] = val
        return headers

    def prepare(self, request, routes=None):
        try:
            header_text, body_text = request.split('\r\n\r\n', 1)
        except ValueError:
            header_text = request
            body_text = ""
        # Prepare the request line from the request header
        self.method, self.path, self.version = self.extract_request_line(header_text)
        if not self.method:
            self.headers = {}
            self.body = {}
            self.cookies = {}
            return
        print("[Request] {} path {} version {}".format(self.method, self.path, self.version))
        self.headers = self.prepare_headers(header_text)

        def parse_body(body_str):
            if not body_str:
                return {}
            
            dict_body = {}
            for pair in body_str.split('&'):
                if '=' in pair:
                    key, val = pair.split('=', 1)
                    dict_body[key] = val
            return dict_body

        self.body = parse_body(body_text)
            
        def parse_cookies(cookies_str):
            if not cookies_str:
                return {}
            
            cookies = {}
            for pair in cookies_str.split(';'):
                if '=' in pair:
                    key, val = pair.strip().split('=', 1)
                    cookies[key] = val
            return cookies
        cookies_str = self.headers.get('cookie', '')
        self.cookies = parse_cookies(cookies_str)
        if not routes == {}:
            self.routes = routes
            self.hook = routes.get((self.method, self.path))
            
    def prepare_body(self, data, files, json=None):
        pass

    def prepare_content_length(self, body):
        pass

    def prepare_auth(self, auth, url=""):
        pass

    def prepare_cookies(self, cookies):
        pass