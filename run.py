"""Arranca la app en local: `python run.py`."""
from cv_adaptativo.web import crear_app

if __name__ == "__main__":
    app = crear_app()
    app.run(debug=True)
