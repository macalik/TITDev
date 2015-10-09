import os
import json
import time

from flask import Flask, render_template, g
from flask_bootstrap import Bootstrap
from flask_pymongo import PyMongo

from views.navigation import Navigation
from views.auth import auth
from views.jump_freighter import jf
from views.admin import admin
from views.account import account
from views.corp import corp
from views.fittings import fittings
from views.security.dashboard import security_dashboard
from views.security.api_manager import api_manager

app = Flask(__name__)
Bootstrap(app)
Navigation(app)

if os.environ.get("HEROKU"):
    app.config["MONGO_URI"] = os.environ["MONGOLAB_URI"]
    app.secret_key = os.environ["random_key"]
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)
    app.config["MONGO_HOST"] = secrets["mongo-host"]
    app.config["MONGO_DBNAME"] = secrets["mongo-db"]
    app.config["MONGO_USERNAME"] = secrets["mongo-user"]
    app.config["MONGO_PASSWORD"] = secrets["mongo-password"]
    app.config["MONGO_PORT"] = secrets["mongo-port"]
    app.secret_key = secrets["random_key"]
app_mongo = PyMongo(app)

app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(jf, url_prefix="/jf")
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(account, url_prefix="/account")
app.register_blueprint(corp, url_prefix="/corp")
app.register_blueprint(security_dashboard, url_prefix="/security")
app.register_blueprint(api_manager, url_prefix="/security/api_manager")
app.register_blueprint(fittings, url_prefix="/fittings")


@app.before_first_request
def app_init():
    db_check_stations = app_mongo.db.stations.find_one({"_id": 60003760})  # Use Jita as check
    if not db_check_stations:
        # Load statics into memory
        with open("resources/staStations.json", "r") as staStations_file:
            stations_list = json.load(staStations_file)
        app_mongo.db.stations.insert([{"_id": int(key), "name": value} for key, value in stations_list.items()])

    db_check_items = app_mongo.db.items.find_one({"_id": 34})  # Use Tritanium as check
    if not db_check_items:
        with open("resources/invTypes.json", "r") as invTypes_file:
            items_list = json.load(invTypes_file)
        # Adjust packed volumes of ships
        with open("resources/invVolumes.json", "r") as invVolumes_file:
            volumes_list = json.load(invVolumes_file)

        adjusted_items_list = []
        for key, value in items_list.items():
            corrected_volume = volumes_list[key] if volumes_list.get(key) else value["volume"]
            adjusted_items_list.append({"_id": int(key), "name": value["name"], "volume": corrected_volume})
        app_mongo.db.items.insert(adjusted_items_list)


@app.before_request
def db_init():
    if os.environ.get("TIMINGS"):
        g.timings = True
    else:
        g.timings = False
    g.mongo = app_mongo
    g.start_time = time.time()
    print("Request start: {}".format(g.start_time)) if g.timings else None


@app.teardown_request
def cleanup(exception=None):
    end_time = time.time()
    print("Request end: {}, Total: {}".format(end_time, end_time - g.start_time)) if g.timings else None
    if exception:
        print("Error: ", exception)


@app.route('/')
def home():
    return render_template("index.html")


if not os.environ.get("HEROKU") and __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0")
