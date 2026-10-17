"""Create a private LAN CA and correctly named server certificate using OpenSSL.

Does not install trust roots, open firewall ports, or start a network listener.
Share only server-ca.crt, never the key files. Existing CA identity is retained.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import ssl
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def prepare(address,folder,port=8096):
    ip=ipaddress.ip_address(address)
    if ip.version!=4 or ip.is_unspecified or ip.is_multicast:raise ValueError('Use the specific Wi-Fi IPv4 address.')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    openssl=shutil.which('openssl')
    if not openssl:
        fallback=Path(r'C:\Program Files\Git\mingw64\bin\openssl.exe')
        if fallback.is_file():openssl=str(fallback)
    if not openssl:raise RuntimeError('OpenSSL is required to prepare local certificates. Git for Windows includes it.')
    configuration=folder/'openssl.cnf'
    configuration.write_text('[req]\ndistinguished_name=dn\n[dn]\n',encoding='ascii')
    def run(*args):
        result=subprocess.run([openssl,*map(str,args)],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError('Local certificate preparation failed. Check OpenSSL and the certificate folder permissions.')
    ca=folder/'server-ca.crt';ca_key=folder/'server-ca.key'
    if ca.exists()!=ca_key.exists():raise ValueError('The existing CA certificate/key pair is incomplete. Restore it before generating new server certificates.')
    if not ca.exists():
        run('req','-config',configuration,'-x509','-newkey','rsa:3072','-nodes','-sha256','-days','3650','-subj','/CN=Soshyant Private Wi-Fi CA',
            '-keyout',ca_key,'-out',ca,'-addext','basicConstraints=critical,CA:TRUE,pathlen:0',
            '-addext','keyUsage=critical,keyCertSign,cRLSign')
        os.chmod(ca_key,0o600)
    key=folder/'server.key';csr=folder/'server.csr';cert=folder/'server.crt'
    # Generate into temporary files before publishing a new matching pair.
    temp_key=folder/'server.next.key';temp_cert=folder/'server.next.crt'
    run('req','-config',configuration,'-new','-newkey','rsa:2048','-nodes','-sha256','-subj','/CN='+str(ip),'-keyout',temp_key,'-out',csr)
    extensions=folder/'server.ext'
    extensions.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:'+str(ip)+'\n',encoding='ascii')
    run('x509','-req','-in',csr,'-CA',ca,'-CAkey',ca_key,'-set_serial',str(secrets.randbits(128)),'-days','365','-sha256','-extfile',extensions,'-out',temp_cert)
    run('verify','-CAfile',ca,temp_cert)
    os.chmod(temp_key,0o600);temp_key.replace(key);temp_cert.replace(cert)
    digest=hashlib.sha256(ssl.PEM_cert_to_DER_cert(ca.read_text(encoding='ascii'))).hexdigest()
    metadata={'server_url':f'https://{ip}:{port}','ca_sha256':digest,'ca_file':str(ca),'certificate':str(cert),'private_key':str(key)}
    (folder/'connection.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return metadata


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--address',required=True);parser.add_argument('--port',type=int,default=8096)
    parser.add_argument('--directory',type=Path,default=ROOT/'data/mobile-tls');args=parser.parse_args()
    result=prepare(args.address,args.directory,args.port)
    print('Phone server address:',result['server_url']);print('Import this public certificate:',result['ca_file'])
    print('CA SHA-256 fingerprint:',result['ca_sha256']);print('Do not share any .key files.')


if __name__=='__main__':main()
