from flask import session

from app_core import app
from helpers import ensure_schema

ensure_schema()

from routes import auth, dashboard, tickets, management, exports


@app.context_processor
def inject_user():
    return {"current_user": session}


if __name__ == "__main__":
    app.run(debug=True)
