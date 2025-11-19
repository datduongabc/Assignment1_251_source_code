import datetime
import os
import mimetypes
import json

BASE_DIR = ""

class Response():   
    __attrs__ = [ 
       '_content', '_header', 'status_code', 'method', 'headers', 'url', 
       'history', 'encoding', 'reason', 'cookies', 'elapsed', 'request', 'body', 'reason'
    ]

    def __init__(self):
        self._content = False
        self.status_code = None
        self.headers = {}
        self.reason = None
        self.request = None
        
        # Variables not use yet
        # self._content_consumed = False
        # self._next = None
        # self.url = None
        # self.encoding = None
        # self.history = []        
        # self.cookies = CaseInsensitiveDict()
        # self.elapsed = datetime.timedelta(0)

    def get_mime_type(self, path):
        mime_type, _ = mimetypes.guess_type(path)
        # application/octet-stream: no specific format
        return mime_type if mime_type else "application/octet-stream"
        
    def prepare_content_type(self, mime_type='text/html'):        
        base_dir = ""
        try:
            main_type, sub_type = mime_type.split('/', 1)
        except ValueError:
            raise ValueError(f"Invalid MIME type: {mime_type}")
        self.headers['Content-Type'] = mime_type
        if main_type == 'text':
            if sub_type == 'html':
                base_dir = BASE_DIR+"www/"
            elif sub_type == 'css':
                base_dir = BASE_DIR+"static/css/"
            elif sub_type == 'plain':
                base_dir = BASE_DIR+"static/css/"
            else:
                raise ValueError("Unsupported text subtype: {}".format(sub_type))
        elif main_type == 'image':
            if sub_type in ['png', 'jpeg', 'vnd.microsoft.icon', 'x-icon']:
                base_dir = BASE_DIR+"static/images/"
            else:
                raise ValueError("Unsupported image subtype: {}".format(sub_type))
        elif main_type == 'application':
            if sub_type == 'x-x509-ca-cert':
                base_dir = BASE_DIR+"cert/"
            elif sub_type == 'javascript':
                base_dir = BASE_DIR+"static/js/"
            elif sub_type == 'python':
                base_dir = BASE_DIR+"apps/"
            else:
                raise ValueError("Unsupported application subtype: {}".format(sub_type))
        else:
            raise ValueError("Unsupported main MIME type: {}".format(main_type))
        return base_dir

    def build_content(self, path, base_dir):
        filepath = os.path.join(base_dir, path.lstrip('/'))
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            print("[Response] File not found: {}".format(filepath))
            self.status_code = 404
            return b""
        except Exception as e:
            print("[Response] Server error {}: {}".format(filepath, e))
            self.status_code = 500
            return b""

    def build_response_header(self):
        if self.status_code is None:
            self.status_code = 200
            self.reason = "OK"
        elif self.status_code == 401:
            self.reason = "Unauthorized"
        elif self.status_code == 404:
            self.reason = "Not Found"
        elif self.status_code == 500:
            self.reason = "Internal Server Error"
        
        status_line = "HTTP/1.1 {} {}\r\n".format(self.status_code or 200, self.reason)
        
        self.headers['Date'] = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        self.headers['Accept-Ranges'] = 'bytes'
        self.headers['Content-Length'] = str(len(self._content))
        self.headers['Cache-Control'] = 'max-age=86000'
        self.headers['Connection'] = 'close'
        
        header_text = ""
        for header, value in self.headers.items():
            header_text += "{}: {}\r\n".format(header, value)
            
        header_text = status_line + header_text + "\r\n"
        return header_text.encode('utf-8')
        
    def build_response(self, request):
        path = request.path
        mime_type = self.get_mime_type(path)
        try:
            base_dir = self.prepare_content_type(mime_type)
        except:
            print("[Response] Unsupported MIME type: {}".format(mime_type))
            return self.build_notfound()
        path = os.path.basename(path)
        self._content = self.build_content(path, base_dir)
        if self.status_code == 401:
            return self.build_unauthorized()
        elif self.status_code == 404:
            return self.build_notfound()
        elif self.status_code == 500:
            return self.build_internal_error()
        self._header = self.build_response_header()
        return self._header + self._content
    
    def build_json_response(self, data):
        # Convert dictionary to JSON string and encode to bytes
        self._content = json.dumps(data).encode('utf-8')
        self._header = self.build_response_header()
        if self.status_code == 401:
            return self.build_unauthorized()
        elif self.status_code == 404:
            return self.build_notfound()
        elif self.status_code == 500:
            return self.build_internal_error()
        return self._header + self._content

    def build_unauthorized(self):
        return (
                "HTTP/1.1 401 Unauthorized\r\n"
                "Accept-Ranges: bytes\r\n"
                "Content-Type: text/html\r\n"
                "Content-Length: 16\r\n"
                "Cache-Control: max-age=86000\r\n"
                "Connection: close\r\n\r\n"
                "401 Unauthorized"
            ).encode('utf-8')

    def build_notfound(self):
        return (
                "HTTP/1.1 404 Not Found\r\n"
                "Accept-Ranges: bytes\r\n"
                "Content-Type: text/html\r\n"
                "Content-Length: 13\r\n"
                "Cache-Control: max-age=86000\r\n"
                "Connection: close\r\n\r\n"
                "404 Not Found"
            ).encode('utf-8')

    def build_internal_error(self):
        return (
                "HTTP/1.1 500 Internal Server Error\r\n"
                "Accept-Ranges: bytes\r\n"
                "Content-Type: text/html\r\n"
                "Content-Length: 25\r\n"
                "Cache-Control: max-age=86000\r\n"
                "Connection: close\r\n\r\n"
                "500 Internal Server Error"
            ).encode('utf-8')