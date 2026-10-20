"""Initialize local environment files without overwriting existing configuration."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
paths = [root / ".env", root / "backend/.env", root / "frontend/.env"]
if any(path.exists() for path in paths):
    raise SystemExit("Environment files already exist. Review them manually; no files changed.")
password = secrets.token_urlsafe(32)
paths[0].write_text(f"POSTGRES_USER=ondc\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB=ondc_fashion\nPOSTGRES_PORT=5432\n", encoding="utf-8")
paths[1].write_text(f'DATABASE_URL=postgresql+psycopg://ondc:{password}@127.0.0.1:5432/ondc_fashion\nCORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]\n', encoding="utf-8")
paths[2].write_text("VITE_API_BASE_URL=http://127.0.0.1:8000\n", encoding="utf-8")
print("Created local .env files with a random database password. No secrets printed.")
