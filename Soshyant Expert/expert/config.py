import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


class Config:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.settings = read_json(self.root / "config/server.json")
        self.domain_path = self.root / "config/domain.json"
        self.data = self.root / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        for key in ("model_file", "llama_executable", "embedding_directory"):
            path = Path(self.settings[key])
            self.settings[key] = str((self.root / path).resolve()) if not path.is_absolute() else str(path)

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
