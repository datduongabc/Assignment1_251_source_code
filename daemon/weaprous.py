from .backend import create_backend

class WeApRous:
    def __init__(self):
        self.routes = {}
        self.ip = None
        self.port = None

    def prepare_address(self, ip, port):
        self.ip = ip
        self.port = port

    def route(self, path, methods=['GET']):
        def decorator(func):
            for method in methods:
                self.routes[(method.upper(), path)] = func

            func._route_path = path
            func._route_methods = methods

            return func
        return decorator

    def run(self):
        if not self.ip or not self.port:
            print("Rous app need to prepare address by calling app.prepare_address(ip,port)")
        create_backend(self.ip, self.port, self.routes)