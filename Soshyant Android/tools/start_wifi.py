"""Start the optional Wi-Fi gateway; the desktop server remains unchanged."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT.parent/'Soshyant Expert'
sys.path.insert(0,str(SERVER))
from tools.prepare_mobile_tls import prepare
from expert.mobile_gateway import create_gateway


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--address');parser.add_argument('--port',type=int,default=8096);args=parser.parse_args()
    saved=ROOT/'wifi-settings.json'
    settings=json.loads(saved.read_text()) if saved.exists() else {}
    address=args.address
    if not address:
        default=settings.get('address','')
        address=input('Wi-Fi IPv4 address'+(' ['+default+']' if default else '')+': ').strip() or default
    configuration=json.loads((SERVER/'config/server.json').read_text(encoding='utf-8'))
    backend='http://127.0.0.1:'+str(configuration['port'])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(backend+'/healthz',timeout=4) as response:
            if response.status!=200:raise RuntimeError('Server health check failed.')
    except Exception:raise SystemExit('Start Soshyant Expert with START.bat first, then run START-WIFI.bat again.')
    result=prepare(address,SERVER/'data/mobile-tls',args.port)
    (ROOT/'dist').mkdir(exist_ok=True);shutil.copy2(result['ca_file'],ROOT/'dist/server-ca.crt')
    saved.write_text(json.dumps({'address':address,'port':args.port},indent=2))
    instructions='Soshyant Android\n\nServer address: '+result['server_url']+'\n\nInstall SoshyantExpert-1.1.0.apk on your phone.\nCopy server-ca.crt to your phone and import it inside the app.\nSign in using the account created on your computer.\n\nCA SHA-256 fingerprint: '+result['ca_sha256']+'\n\nKeep both server windows open. Do not share private .key files.\n'
    (ROOT/'dist/PHONE-CONNECTION.txt').write_text(instructions,encoding='utf-8')
    server=create_gateway(address,args.port,result['certificate'],result['private_key'],backend)
    print(instructions,flush=True)
    print('Wi-Fi access is running. Close this window or press Ctrl+C to stop it.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
