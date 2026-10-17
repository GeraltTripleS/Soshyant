"""TLS-only, chat-scoped LAN gateway to the existing loopback API."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from .config import Config


READ_ROUTES=re.compile(r'^/(healthz|api/(bootstrap|me|status|conversations|conversations/[a-f0-9]+/messages|jobs/[a-f0-9]+))$')
WRITE_ROUTES=re.compile(r'^/api/(login|logout|conversations|conversations/[a-f0-9]+/(rename|delete)|ask|feedback|jobs/[a-f0-9]+/cancel)$')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='SoshyantMobile'
    def log_message(self,*args):pass
    def reply(self,status,body,content_type='application/json; charset=utf-8',cookies=()):
        self.close_connection=True
        self.send_response(status)
        for name,value in [('Content-Type',content_type),('Content-Length',str(len(body))),('Cache-Control','no-store'),
                           ('X-Content-Type-Options','nosniff'),('Connection','close')]:self.send_header(name,value)
        for cookie in cookies:
            self.send_header('Set-Cookie',cookie if re.search(r';\s*secure(?:;|$)',cookie,re.I) else cookie+'; Secure')
        self.end_headers();self.wfile.write(body)
    def do_GET(self):self.forward(False)
    def do_POST(self):self.forward(True)
    def forward(self,write):
        try:
            host=self.headers.get('Host','').lower()
            if host!=self.server.authority.lower():
                return self.reply(403,b'{"error":"Host is not allowed."}')
            origin=self.headers.get('Origin')
            if origin and (urlsplit(origin).scheme!='https' or urlsplit(origin).netloc.lower()!=host):
                return self.reply(403,b'{"error":"Cross-origin requests are not allowed."}')
            route=urlsplit(self.path)
            if route.scheme or route.netloc or not (WRITE_ROUTES if write else READ_ROUTES).fullmatch(route.path):
                return self.reply(404,b'{"error":"This Wi-Fi gateway exposes chat APIs only."}')
            if self.headers.get('Transfer-Encoding'):
                return self.reply(400,b'{"error":"Unsupported request encoding."}')
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>100000 or (not write and length):
                return self.reply(400,b'{"error":"Request exceeds the size limit."}')
            headers={name:self.headers[name] for name in ('Cookie','X-CSRF-Token','Content-Type') if name in self.headers}
            headers['Origin']=self.server.backend
            request=urllib.request.Request(self.server.backend+self.path,data=self.rfile.read(length) if write else None,
                                           headers=headers,method='POST' if write else 'GET')
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            try:response=opener.open(request,timeout=30)
            except urllib.error.HTTPError as error:response=error
            with response:
                body=response.read(8*1024*1024+1)
                if len(body)>8*1024*1024:return self.reply(502,b'{"error":"Upstream response exceeds the size limit."}')
                if 300<=response.status<400:return self.reply(502,b'{"error":"Upstream redirect rejected."}')
                self.reply(response.status,body,response.headers.get('Content-Type','application/json'),response.headers.get_all('Set-Cookie',[]))
        except (BrokenPipeError,ConnectionResetError):pass
        except ValueError:self.reply(400,b'{"error":"Invalid request."}')
        except Exception:self.reply(502,b'{"error":"The local server is unavailable. Start Soshyant Expert on this computer."}')


def create_gateway(host,port,cert,key,backend):
    address=ipaddress.ip_address(host)
    if address.version!=4 or address.is_unspecified or address.is_multicast:
        raise ValueError('Choose the specific local Wi-Fi IPv4 address.')
    endpoint=urlsplit(backend)
    if endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost') or endpoint.username or endpoint.password or endpoint.path not in ('','/') or endpoint.query or endpoint.fragment:
        raise ValueError('The gateway backend must be the loopback HTTP server.')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert,key)
    server=ThreadingHTTPServer((host,port),GatewayHandler)
    server.backend=backend.rstrip('/');server.authority=f'{host}:{server.server_port}'
    server.socket=context.wrap_socket(server.socket,server_side=True)
    return server


def main():
    parser=argparse.ArgumentParser(description='Secure Wi-Fi API gateway for Soshyant Android')
    parser.add_argument('--host',required=True);parser.add_argument('--port',type=int,default=8096)
    parser.add_argument('--cert',required=True);parser.add_argument('--key',required=True)
    parser.add_argument('--backend',default=None);args=parser.parse_args()
    server=create_gateway(args.host,args.port,args.cert,args.key,args.backend or 'http://127.0.0.1:'+str(Config().settings['port']))
    print(f'Android Wi-Fi API ready: https://{server.authority}',flush=True)
    print('The existing desktop server stays on loopback. Close this window to stop Wi-Fi access.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
