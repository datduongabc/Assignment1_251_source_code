"""
Requirements:
- socket: provide socket networking interface.
- threading: enables concurrent client handling via threads.
- argparse: parses command-line arguments for server configuration.
- re: used for regular expression matching in configuration parsing
- response: response utilities.
- httpadapter: the class for handling HTTP requests.
- urlparse: parses URLs to extract host and port information.
- daemon.create_proxy: initializes and starts the proxy server.
"""

import argparse
import re
from daemon import create_proxy

PROXY_PORT = 8080

def parse_virtual_hosts(config_file):
    with open(config_file, 'r') as f:
        config_text = f.read()
    host_blocks = re.findall(r'host\s+"([^"]+)"\s*\{(.*?)\}', config_text, re.DOTALL)
    routes = {}
    for host, block in host_blocks:
        proxy_passes = re.findall(r'proxy_pass\s+http://([^\s;]+);', block)
        policy_match = re.search(r'dist_policy\s+([\w-]+)', block)
        if policy_match:
            dist_policy_map = policy_match.group(1)
        else:
            dist_policy_map = 'round-robin'
        routes[host] = (proxy_passes, dist_policy_map)
    for key, value in routes.items():
        print({key: value})
    return routes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='Proxy', description='', epilog='Proxy daemon')
    parser.add_argument('--server-ip', default='0.0.0.0')
    parser.add_argument('--server-port', type=int, default=PROXY_PORT)
    args = parser.parse_args()
    ip = args.server_ip
    port = args.server_port
    routes = parse_virtual_hosts("config/proxy.conf")
    create_proxy(ip, port, routes)