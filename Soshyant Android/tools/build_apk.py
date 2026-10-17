"""Build a signed pilot APK using official SDK tools and the installed JDK.

No Gradle/JDK installation or server data changes are needed. Gradle project files
are also supplied for Android Studio. Build tools are cached inside this project.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'.tools'
PACKAGES=[('platform-35_r02.zip','0bb560a90a7a2cbd0dd8348224d518b638fe7949','platform'),
          ('build-tools_r35_windows.zip','af059bb67cf7786f45ee0db85e2d24985df1b4b6','build-tools')]


def run(args):
    subprocess.run([str(item) for item in args],check=True,cwd=ROOT)


def prepare():
    TOOLS.mkdir(exist_ok=True)
    for name,digest,folder in PACKAGES:
        archive=TOOLS/name
        if not archive.exists():
            print('Downloading official Android SDK:',name,flush=True)
            partial=archive.with_suffix('.part')
            with urllib.request.urlopen('https://dl.google.com/android/repository/'+name,timeout=90) as response,partial.open('wb') as output:
                shutil.copyfileobj(response,output)
            partial.replace(archive)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream,'sha1').hexdigest()!=digest:raise RuntimeError('Android SDK checksum mismatch: '+name)
        destination=(TOOLS/folder).resolve()
        if not destination.exists():
            destination.mkdir()
            with zipfile.ZipFile(archive) as source:
                for item in source.infolist():
                    if not (destination/item.filename).resolve().is_relative_to(destination):raise ValueError('Unsafe SDK archive entry')
                source.extractall(destination)
    return next((TOOLS/'platform').rglob('android.jar')),next((TOOLS/'build-tools').rglob('aapt2.exe')).parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    android,tools=prepare()
    if args.prepare_only:return
    for command in ('java','javac','keytool'):
        if not shutil.which(command):raise RuntimeError('Install a JDK and add '+command+' to PATH.')
    build=ROOT/'build';dist=ROOT/'dist'
    for folder in ('resources','generated','classes','dex'):(build/folder).mkdir(parents=True,exist_ok=True)
    dist.mkdir(exist_ok=True)
    namespace='http://schemas.android.com/apk/res/android';ET.register_namespace('android',namespace)
    manifest=ET.parse(ROOT/'app/src/main/AndroidManifest.xml');manifest.getroot().set('package','com.soshyant.expert')
    manifest.write(build/'AndroidManifest.xml',encoding='utf-8',xml_declaration=True)
    run([tools/'aapt2.exe','compile','--dir',ROOT/'app/src/main/res','-o',build/'resources.zip'])
    run([tools/'aapt2.exe','link','-I',android,'--manifest',build/'AndroidManifest.xml','--java',build/'generated',
         '--auto-add-overlay','-o',build/'resources.apk',build/'resources.zip'])
    sources=list((ROOT/'app/src/main/java').rglob('*.java'))+list((build/'generated').rglob('*.java'))
    # Argfiles avoid Windows command-length and path quoting problems.
    arguments=['--release','8','-encoding','UTF-8','-classpath',str(android),'-d',str(build/'classes')]+[str(path) for path in sources]
    (build/'javac.args').write_text('\n'.join('"'+item.replace('\\','/')+'"' for item in arguments),encoding='utf-8')
    run(['javac','@'+str(build/'javac.args')])
    run(['java','-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--min-api','26','--lib',android,'--output',build/'dex',*list((build/'classes').rglob('*.class'))])
    shutil.copy2(build/'resources.apk',build/'unsigned.apk')
    with zipfile.ZipFile(build/'unsigned.apk','a',compression=zipfile.ZIP_DEFLATED) as archive:
        for dex in (build/'dex').glob('*.dex'):archive.write(dex,dex.name)
    run([tools/'zipalign.exe','-f','4',build/'unsigned.apk',build/'aligned.apk'])
    key=TOOLS/'pilot-signing.jks'
    if not key.exists():run(['keytool','-genkeypair','-keystore',key,'-storepass','android','-alias','androiddebugkey',
                            '-keypass','android','-dname','CN=Soshyant Pilot, O=Soshyant, C=US','-keyalg','RSA','-keysize','2048','-validity','3650'])
    apk=dist/'SoshyantExpert-1.1.0.apk'
    run(['java','-jar',tools/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:android','--key-pass','pass:android',
         '--ks-key-alias','androiddebugkey','--out',apk,build/'aligned.apk'])
    run(['java','-jar',tools/'lib/apksigner.jar','verify','--verbose',apk])
    digest=hashlib.sha256(apk.read_bytes()).hexdigest();(dist/'SHA256SUMS.txt').write_text(digest+'  '+apk.name+'\n')
    print('Signed pilot APK:',apk,flush=True)


if __name__=='__main__':main()
