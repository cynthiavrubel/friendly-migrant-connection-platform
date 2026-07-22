from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <h1>Friendly</h1>
    <p>This is the beginning of my Software Development portfolio project.</p>
    <button><b>Get Started</b></button>    """


if __name__ == "__main__":
    app.run(debug=True)