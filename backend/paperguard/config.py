import os
from pathlib import Path
from dataclasses import dataclass, field

ROOT = Path(__file__).resolve().parents[2]

def load_env(path=None):
    path = Path(path or ROOT / '.env')
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('PAPERGUARD_DATA', str(ROOT / 'data'))).resolve())
    sources: tuple = field(default_factory=lambda: tuple(x.strip() for x in os.getenv('PAPERGUARD_SOURCES','crossref,openalex').split(',') if x.strip()))
    timeout: float = field(default_factory=lambda: float(os.getenv('PAPERGUARD_TIMEOUT','20')))
    cache_ttl: int = field(default_factory=lambda: int(os.getenv('PAPERGUARD_CACHE_TTL','604800')))
    email: str = field(default_factory=lambda: os.getenv('PAPERGUARD_EMAIL',''))
    openalex_key: str = field(default_factory=lambda: os.getenv('OPENALEX_API_KEY',''))
    semantic_key: str = field(default_factory=lambda: os.getenv('SEMANTIC_SCHOLAR_API_KEY',''))
    llm_base: str = field(default_factory=lambda: os.getenv('PAPERGUARD_LLM_BASE',''))
    llm_key: str = field(default_factory=lambda: os.getenv('PAPERGUARD_LLM_KEY',''))
    llm_model: str = field(default_factory=lambda: os.getenv('PAPERGUARD_LLM_MODEL',''))
    max_pdf_bytes: int = 50 * 1024 * 1024
