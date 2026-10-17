"""Admin-only registry of existing local GGUF files. Never downloads models."""
import hashlib
import json
import os
from pathlib import Path
import struct
import threading
from .cloud import CloudProfiles


class ModelLibrary:
    def __init__(self, config, engine):
        self.config, self.engine = config, engine
        self.path = config.data / 'local-models.json'
        self.folder_path = config.data / 'model-folder.json'
        self.clouds = CloudProfiles(config)
        self.lock = threading.Lock()
        self.directory = config.root / 'assets/models'
        self.directory.mkdir(parents=True, exist_ok=True)

    def registered(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []

    def folder(self):
        return json.loads(self.folder_path.read_text(encoding='utf-8')) if self.folder_path.exists() else {
            'path': str(self.directory), 'recursive': True, 'files': [], 'invalid': [], 'truncated': False}

    def local_path(self, value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('Enter a local folder path on the server.')
        value=value.strip()
        if len(value)>1 and value[0]==value[-1] and value[0] in ('"', "'"):
            value=value[1:-1]
        path=Path(value).expanduser()
        if not path.is_absolute():path=self.config.root/path
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Choose a local folder on the server, not a network share.')
        path=path.resolve()
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Choose a local folder on the server, not a network share.')
        return path

    def folders(self, value=None):
        path=self.local_path(value or self.folder()['path'])
        if not value and not path.is_dir():path=self.directory
        if not path.is_dir():raise ValueError('The selected folder does not exist on the server.')
        roots=[]
        if os.name=='nt':
            import ctypes
            mask=ctypes.windll.kernel32.GetLogicalDrives()
            for index in range(26):
                drive=chr(65+index)+':\\'
                if mask & (1<<index) and ctypes.windll.kernel32.GetDriveTypeW(drive) in (2,3):
                    roots.append(drive)
        else:roots=['/']
        directories=[]
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                        if os.name=='nt' and getattr(entry.stat(follow_symlinks=False),'st_file_attributes',0)&0x400:continue
                        directories.append({'name':entry.name,'path':entry.path})
                        if len(directories)>=1000:break
        except OSError as exc:raise ValueError('This folder cannot be opened by the server account.') from exc
        directories.sort(key=lambda row:row['name'].casefold())
        return {'path':str(path),'parent':str(path.parent),'roots':roots,'directories':directories,
                'limited':len(directories)>=1000}

    def scan_folder(self, value, recursive=True):
        if not isinstance(recursive,bool):raise ValueError('Choose whether to include subfolders.')
        path=self.local_path(value)
        if not path.exists():raise ValueError('The selected folder does not exist on the server.')
        if not path.is_dir():raise ValueError('Choose a folder, not an individual model file.')
        files,invalid,unreadable=[],[],[]
        pending=[path];visited=0;truncated=False
        while pending and not truncated:
            directory=pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited+=1
                        if visited>20000 or len(files)>=200:
                            truncated=True;break
                        if entry.is_symlink():continue
                        if os.name=='nt' and getattr(entry.stat(follow_symlinks=False),'st_file_attributes',0)&0x400:continue
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith('.gguf'):
                            try:self.validate(Path(entry.path))
                            except (ValueError,OSError):invalid.append(entry.path)
                            else:files.append(str(Path(entry.path).resolve()))
            except OSError:unreadable.append(str(directory))
        state={'path':str(path),'recursive':recursive,'files':sorted(files,key=str.casefold),
               'invalid':invalid,'unreadable':unreadable,'truncated':truncated}
        with self.lock:
            temporary=self.folder_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
            temporary.replace(self.folder_path)
        result=self.catalog()
        result['scan']={'found':len(files),'invalid':len(invalid),'unreadable':len(unreadable),'truncated':truncated}
        return result

    @staticmethod
    def identify(path):
        return hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()[:24]

    @staticmethod
    def validate(path):
        if path.suffix.lower() != '.gguf' or not path.is_file():
            raise ValueError('Choose an existing local GGUF file on the server.')
        with path.open('rb') as stream:
            header = stream.read(24)
        if len(header) != 24 or header[:4] != b'GGUF' or struct.unpack('<I', header[4:8])[0] not in (2, 3):
            raise ValueError('The selected file is not a supported GGUF model.')
        if path.stat().st_size <= 24:
            raise ValueError('The model file is incomplete.')

    def catalog(self):
        active = Path(self.config.settings['model_file']).resolve()
        paths = [active] + [Path(row) for row in self.registered()]
        folder=self.folder()
        paths += [Path(path) for path in folder['files']]
        if not self.folder_path.exists():
            paths += [path for path in self.directory.glob('*.gguf') if not path.is_symlink()]
        models, seen = [], set()
        for path in paths:
            path = path.resolve()
            identity = self.identify(path)
            if identity in seen:
                continue
            seen.add(identity)
            models.append({'id': identity, 'name': path.name, 'path': str(path),
                           'bytes': path.stat().st_size if path.is_file() else 0,
                           'available': path.is_file(), 'kind':'local',
                           'active': path == active and not self.config.settings.get('cloud_model_id')})
        for profile in self.clouds.rows():
            models.append({**self.clouds.public(profile),'kind':'cloud','available':True,
                           'active':profile['id']==self.config.settings.get('cloud_model_id')})
        return {'models': models, 'directory': str(self.directory), 'folder':folder,
                'state': self.engine.model.state, 'changing': self.engine.model_changing}

    def register(self, value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('Enter a local GGUF path on the server.')
        path = self.local_path(value)
        if not path.is_absolute():
            path = self.config.root / path
        # Do not turn a path registration into a network file request.
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Network shares are not supported. Use a local server file.')
        path = path.resolve()
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Network shares are not supported. Use a local server file.')
        self.validate(path)
        with self.lock:
            rows = self.registered()
            if str(path) not in rows:
                rows.append(str(path))
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(rows, indent=2), encoding='utf-8')
                temporary.replace(self.path)
        return self.catalog()

    def active_info(self):
        identity=self.config.settings.get('cloud_model_id')
        if identity:
            try:
                profile=self.clouds.get(identity)
                return {'kind':'cloud','name':profile['name'],'model':profile['model'],'base_url':profile['base_url']}
            except ValueError:return {'kind':'cloud','name':'Unavailable API connection','base_url':''}
        return {'kind':'local','name':Path(self.config.settings['model_file']).name}

    def activate(self, identity, confirm_cloud=False):
        if not isinstance(identity, str):
            raise ValueError('Choose a registered local model.')
        with self.lock:
            choice = next((row for row in self.catalog()['models'] if row['id'] == identity), None)
            if not choice:
                raise ValueError('Choose a registered local model.')
            cloud=choice['kind']=='cloud'
            if cloud and confirm_cloud is not True:
                raise ValueError('Confirm that questions, retrieved document passages, and recent conversation may be sent to this API provider.')
            path = None if cloud else Path(choice['path'])
            if path:self.validate(path)
            with self.engine.inflight_lock:
                if self.engine.inflight or self.engine.model_changing:
                    raise ValueError('Wait for pending answers to finish before changing the model.')
                self.engine.model_changing = True
            previous = self.config.settings['model_file']
            previous_cloud=self.config.settings.get('cloud_model_id')
            try:
                self.engine.model.close()
                self.config.settings['cloud_model_id']=identity if cloud else ''
                if path:self.config.settings['model_file'] = str(path)
                # Health check the actual runtime before saving the selection.
                self.engine.model.ensure()
                settings_path = self.config.root / 'config/server.json'
                saved = json.loads(settings_path.read_text(encoding='utf-8'))
                if path:
                    try:saved['model_file'] = str(path.relative_to(self.config.root))
                    except ValueError:saved['model_file'] = str(path)
                saved['cloud_model_id']=identity if cloud else ''
                temporary = settings_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(saved, indent=2), encoding='utf-8')
                temporary.replace(settings_path)
            except Exception as exc:
                self.engine.model.close()
                self.config.settings['model_file'] = previous
                if previous_cloud is None:self.config.settings.pop('cloud_model_id',None)
                else:self.config.settings['cloud_model_id']=previous_cloud
                raise ValueError('Model activation failed. The previous selection is retained. '+str(exc)) from None
            finally:
                with self.engine.inflight_lock:
                    self.engine.model_changing = False
        return self.catalog()
