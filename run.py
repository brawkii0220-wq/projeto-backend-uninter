"""Ponto de entrada: python run.py  (perfil via APP_PROFILE, padrão dev)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from raizesdonordeste import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=app.extensions["settings"].server_port)
