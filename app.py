from datetime import datetime

from flask import Flask, render_template

app = Flask(__name__)


@app.context_processor
def inject_current_year():
    """Make the current year available to shared page content."""
    return {"current_year": datetime.now().year}


@app.route("/")
def home():
    return render_template("home.html")


# Temporary routes until authentication is implemented.
@app.route("/login")
def login():
    return "Log in is coming soon."


@app.route("/register")
def register():
    return "Registration is coming soon."


if __name__ == "__main__":
    app.run(debug=True)
