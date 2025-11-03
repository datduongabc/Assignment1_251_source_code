"""
daemon.response

This module provides a :class: `Response <Response>` object to manage and
persist response settings (cookies, auth, proxies)
and to construct HTTP responses based on incoming requests.

The current version supports MIME type detection, content loading and header formatting
"""
import datetime
import os
import mimetypes
from .dictionary import CaseInsensitiveDict
import json

BASE_DIR = ""

class Response():   
    """The :class:`Response <Response>` object, which contains a
    server's response to an HTTP request.

    Instances are generated from a :class:`Request <Request>` object, and
    should not be instantiated manually; doing so may produce undesirable
    effects.

    :class:`Response <Response>` object encapsulates headers, content, 
    status code, cookies, and metadata related to the request-response cycle.
    It is used to construct and serve HTTP responses in a custom web server.

    :attrs status_code (int): HTTP status code (e.g., 200, 404).
    :attrs headers (dict): dictionary of response headers.
    :attrs url (str): url of the response.
    :attrsencoding (str): encoding used for decoding response content.
    :attrs history (list): list of previous Response objects (for redirects).
    :attrs reason (str): textual reason for the status code (e.g., "OK", "Not Found").
    :attrs cookies (CaseInsensitiveDict): response cookies.
    :attrs elapsed (datetime.timedelta): time taken to complete the request.
    :attrs request (PreparedRequest): the original request object.

    Usage::

      >>> import Response
      >>> resp = Response()
      >>> resp.build_response(req)
      >>> resp
      <Response>
    """

    def __init__(self, request=None):
        """
        Initializes a new :class:`Response <Response>` object.

        : params request : The originating request object.
        """

        self._content = False
        self._content_consumed = False
        self._next = None
        #: Integer Code of responded HTTP Status
        self.status_code = None
        #: Case-insensitive Dictionary of Response Headers.
        self.headers = {}
        #: URL location of Response.
        self.url = None
        #: Encoding to decode with when accessing response text.
        self.encoding = None
        #: A list of :class:`Response <Response>` objects from
        #: the history of the Request.
        self.history = []
        #: Textual reason of responded HTTP Status, e.g. "Not Found" or "OK".
        self.reason = None
        #: A of Cookies the response headers.
        self.cookies = CaseInsensitiveDict()
        #: The amount of time elapsed between sending the request
        self.elapsed = datetime.timedelta(0)
        #: The :class:`PreparedRequest <PreparedRequest>` object to which this
        #: is a response.
        self.request = None

    def get_mime_type(self, path):
        try:
            mime_type, _ = mimetypes.guess_type(path)
        except Exception:
            return 'application/octet-stream'
        return mime_type or 'application/octet-stream'


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
            else:
                raise ValueError(f"Unsupported text subtype: {sub_type}")
        elif main_type == 'image':
            if sub_type in ['png', 'jpeg', 'vnd.microsoft.icon', 'x-icon']:
                base_dir = BASE_DIR+"static/images/"
            else:
                raise ValueError(f"Unsupported image subtype: {sub_type}")
        elif main_type == 'application':
            if sub_type == 'x-x509-ca-cert':
                base_dir = BASE_DIR+"cert/"
            elif sub_type == 'javascript':
                base_dir = BASE_DIR+"static/js/"
            else:
                base_dir = BASE_DIR+"apps/"
        else:
            raise ValueError(f"Unsupported main MIME type: {main_type}")
        return base_dir

    def build_content(self, path, base_dir):
        filepath = os.path.join(base_dir, path.lstrip('/'))

        print("[Response] serving the object at location {}".format(filepath))
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            return len(content), content
        except FileNotFoundError:
            print("[Response] File not found: {}".format(filepath))
            self.status_code = 404
            return 0, b""
        except Exception as e:
            print("[Response] Server error {}: {}".format(filepath, e))
            self.status_code = 500
            return 0, b""

    def build_response_header(self, request):
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
        print("[Response] {} path {} mime_type {}".format(request.method, request.path, mime_type))
        try:
            base_dir = self.prepare_content_type(mime_type)
        except:
            print("[Response] Unsupported MIME type: {}".format(mime_type))
            return self.build_notfound()
        file_name = os.path.basename(path)
        c_len, self._content = self.build_content(file_name, base_dir)
        if self.status_code == 404:
             return self.build_notfound()
        if self.status_code == 500:
            return self.build_internal_error()
        self._header = self.build_response_header(request)
        return self._header + self._content
    
    def build_json_response(self, data):
        try:
            # Convert dictionary to JSON string and encode to bytes
            self._content = json.dumps(data).encode('utf-8')
            self.headers['Content-Type'] = 'application/json'
            self._header = self.build_response_header(request=None)
            return self._header + self._content
        except Exception:
            return self.build_internal_error()

    def build_unauthorized(self):
        return (
                b"HTTP/1.1 401 Unauthorized\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 16\r\n"
                b"Connection: close\r\n\r\n"
                b"401 Unauthorized"
            )

    def build_notfound(self):
        return (
                b"HTTP/1.1 404 Not Found\r\n"
                b"Content-Type: text/html\r\n"
                b"Content-Length: 13\r\n"
                b"Connection: close\r\n\r\n"
                b"404 Not Found"
            )
    
    def build_internal_error(self):
        return (
                b"HTTP/1.1 500 Internal Server Error\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 25\r\n"
                b"Connection: close\r\n\r\n"
                b"500 Internal Server Error"
            )