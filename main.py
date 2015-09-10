import os
import json

from flask import Flask, render_template, g
from flask_bootstrap import Bootstrap
from flask_pymongo import PyMongo

from views import navigation
from views.auth import auth, requires_sso

app = Flask(__name__)
Bootstrap(app)
navigation.init(app)

app.secret_key = os.urandom(24)
if os.environ.get("HEROKU"):
    app.config["MONGO_URI"] = os.environ["MONGOLAB_URI"]
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)
    app.config["MONGO_HOST"] = secrets["mongo-host"]
    app.config["MONGO_DBNAME"] = secrets["mongo-db"]
    app.config["MONGO_USERNAME"] = secrets["mongo-user"]
    app.config["MONGO_PASSWORD"] = secrets["mongo-password"]
    app.config["MONGO_PORT"] = secrets["mongo-port"]
app_mongo = PyMongo(app)

app.register_blueprint(auth, url_prefix="/auth")


@app.before_request
def db_init():
    g.mongo = app_mongo


@app.route('/')
def home():
    return render_template("index.html", name="hi")


@app.route('/something')
@requires_sso("corporation")
def other():
    return render_template("base.html", name="hello")

if not os.environ.get("HEROKU") and __name__ == "__main__":
    app.debug = True
    app.run()
