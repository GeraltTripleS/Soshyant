import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# English OCR for scanned pages (see OCR.md); older server.json files get these defaults.
OCR_DEFAULTS = {
    "ocr_enabled": True,
    "ocr_model": "assets/ocr/unlimited-ocr-Q4_K_M.gguf",
    "ocr_projector": "assets/ocr/mmproj-unlimited-ocr-bf16.gguf",
    "ocr_port": 18196,
    "ocr_gpu_layers": 0,
    "ocr_threads": 0,
    "ocr_max_pages": 200,
    "ocr_max_side": 1600,
    "ocr_max_tokens": 2048,
    "ocr_page_seconds": 300,
    "ocr_idle_seconds": 120,
}


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


class Config:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.settings = read_json(self.root / "config/server.json")
        for key, value in OCR_DEFAULTS.items():
            self.settings.setdefault(key, value)
        self.settings.setdefault('speech_enabled', False)
        self.settings.setdefault('speech_device', 'cpu')
        self.domain_path = self.root / "config/domain.json"
        self.data = self.root / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        for key in ("model_file", "llama_executable", "embedding_directory", "ocr_model", "ocr_projector"):
            path = Path(self.settings[key])
            self.settings[key] = str((self.root / path).resolve()) if not path.is_absolute() else str(path)

    def save_setting(self, key, value):
        """Persist one server setting atomically, keeping the file's other values as written."""
        path = self.root / "config/server.json"
        saved = read_json(path)
        saved[key] = value
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        temporary.replace(path)
        self.settings[key] = value

    def domain(self):
        return self.validate_domain(read_json(self.domain_path))

    @staticmethod
    def validate_domain(value):
        if not isinstance(value, dict):
            raise ValueError("Domain settings must be an object.")
        result = {}
        for key, limit in {"name": 100, "description": 500, "scope": 3000,
                           "language": 50, "answer_style": 1000}.items():
            text = value.get(key, "")
            if not isinstance(text, str) or len(text) > limit:
                raise ValueError(f"Invalid domain field: {key}")
            result[key] = text.strip()
        if not result["name"] or not result["scope"]:
            raise ValueError("A workspace name and scope are required.")
        glossary = value.get("glossary", {})
        fields = value.get("clarification_fields", [])
        if not isinstance(glossary, dict) or len(glossary) > 100:
            raise ValueError("Glossary must contain at most 100 terms.")
        if any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 80 or len(v) > 300
               for k, v in glossary.items()):
            raise ValueError("Glossary terms are too long or invalid.")
        if not isinstance(fields, list) or len(fields) > 20 or any(
                not isinstance(v, str) or len(v) > 100 for v in fields):
            raise ValueError("Clarification fields must be a list of short names.")
        result.update(glossary=glossary, clarification_fields=fields)
        return result

    def save_domain(self, value):
        domain = self.validate_domain(value)
        temporary = self.domain_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(domain, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.domain_path)
        return domain
