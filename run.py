"""Entry point.  Run with:  python run.py   (or: flask --app run <command>)"""
from app import create_app
from app.extensions import db
from config import Config

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # first run: create the SQLite file and tables automatically
    # Debug mode is OFF unless FLASK_DEBUG=1 is set in .env
    app.run(host="127.0.0.1", port=Config.PORT, debug=Config.DEBUG)
