import os
import json

from flask import render_template, g, session, redirect, url_for, request
from bson.objectid import ObjectId
import redis

from app import app, app_mongo, cdn_theme_url

from views.navigation import Navigation
from views.auth import auth
from views.jump_freighter import jf
from views.admin import admin
from views.account import account
from views.corp import corp
from views.fittings import fittings
from views.buyback import buyback
from views.ordering import ordering
from views.security import security
from views.recruitment import recruitment
from views.auth import requires_sso, auth_check
# noinspection PyUnresolvedReferences
from views import api  # Attaches API module


app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(jf, url_prefix="/jf")
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(account, url_prefix="/account")
app.register_blueprint(corp, url_prefix="/corp")
app.register_blueprint(fittings, url_prefix="/fittings")
app.register_blueprint(buyback, url_prefix="/buyback")
app.register_blueprint(ordering, url_prefix="/ordering")
app.register_blueprint(security, url_prefix="/security")
app.register_blueprint(recruitment, url_prefix="/recruitment")
Navigation(app)


@app.before_first_request
def app_init():
    # Check if stations are loaded
    db_check_stations = app_mongo.db.stations.find_one({"_id": 60003760})  # Use Jita as check
    if not db_check_stations:
        # Load statics into memory
        with open("resources/staStations.json", "r") as staStations_file:
            stations_list = json.load(staStations_file)
        app_mongo.db.stations.insert([{"_id": int(key), "name": value} for key, value in stations_list.items()])

    # Refresh Items
    app_mongo.db.items.drop()
    with open("resources/invTypes.json", "r") as invTypes_file:
        items_list = json.load(invTypes_file)
    # Adjust packed volumes of ships
    with open("resources/invVolumes.json", "r") as invVolumes_file:
        volumes_list = json.load(invVolumes_file)
    # Open refine amounts
    with open("resources/invTypeMaterials.json", "r") as invTypesMaterials_file:
        materials_list = json.load(invTypesMaterials_file)

    adjusted_items_list = []
    for key, value in items_list.items():
        corrected_volume = volumes_list[key] if volumes_list.get(key) else value["volume"]
        adjusted_items_list.append({"_id": int(key), "name": value["name"], "volume": corrected_volume,
                                    "meta": value["meta"], "materials": materials_list.get(key, []),
                                    "market_group_id": value["market_group_id"], "skill_id": value["skill_id"],
                                    "batch": value["batch"]})
    app_mongo.db.items.insert(adjusted_items_list)

    # Check if roles are loaded
    app_mongo.db.eve_auth.update({"_id": "super_admin"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "jf_admin"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "jf_pilot"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "user_admin"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "fittings_admin"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "buyback_admin"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "ordering_admin"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "ordering_marketeer"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "security_officer"}, {"$setOnInsert": {"users": []}}, upsert=True)
    app_mongo.db.eve_auth.update({"_id": "recruiter"}, {"$setOnInsert": {"users": []}}, upsert=True)


@app.before_request
def db_init():
    g.mongo = app_mongo

    if request.path not in ["/settings"] and not any([
        request.path.endswith(".js"),
        request.path.endswith(".css"),
        request.path.endswith(".ico"),
        request.path.endswith(".png"),
    ]):
        session["prev_path"] = request.path

    # Check css
    if session.get("default_css", True):
        app.extensions['bootstrap']['cdns']["theme"].baseurl = cdn_theme_url
    else:
        cdn_theme_dark_url = "https://maxcdn.bootstrapcdn.com/bootswatch/3.3.5/slate/"
        app.extensions['bootstrap']['cdns']["theme"].baseurl = cdn_theme_dark_url

    if os.environ.get("maintenance") == "True":
        return render_template("maintenance.html")

    # Redis
    # read url
    try:
        redis_host = app.config["CELERY_BROKER_URL"][8:].split("@")[1].split(":")[0]
        redis_password = app.config["CELERY_BROKER_URL"][9:].split("@")[0]
    except IndexError:
        redis_host = app.config["CELERY_BROKER_URL"][8:].split(":")[0]
        redis_password = None
    redis_port = int(app.config["CELERY_BROKER_URL"][9:].split(":")[1].split("/")[0])
    redis_db = int(app.config["CELERY_BROKER_URL"][9:].split("/")[1])

    g.redis = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, password=redis_password)


@app.teardown_request
def cleanup(exception=None):
    if exception:
        print("Error: ", exception)


@app.route('/')
def home():
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    return render_template("index.html", forum_url=base_config["forum_url"])


@app.route("/settings")
def settings():
    session.setdefault("default_css", True)
    session["default_css"] = False if session.get("default_css") else True
    if session.get("CharacterOwnerHash"):
        return redirect(session.get("prev_path", url_for("account.home")))
    else:
        return redirect(session.get("prev_path", url_for("home")))


@requires_sso(None)
@app.route("/issues", methods=["GET", "POST"])
def issues():
    editor = auth_check("user_admin")
    if request.form.get("action") == "submit":
        g.mongo.db.issues.insert({
            "submitter": session["CharacterName"],
            "issue": request.form.get("issue").strip()
        })
    elif request.form.get("action") == "delete":
        if editor:
            g.mongo.db.issues.remove({"_id": ObjectId(request.form.get("id"))})
        else:
            g.mongo.db.issues.remove({"_id": ObjectId(request.form.get("id")), "submitter": session["CharacterName"]})

    issue_list = []
    for db_issue in g.mongo.db.issues.find():
        timestamp = ObjectId(db_issue["_id"]).generation_time.strftime("%Y-%m-%d %H:%M:%S")
        can_delete = True if editor or session["CharacterName"] == db_issue["submitter"] else False
        issue_list.append([timestamp, db_issue["issue"], db_issue["submitter"], can_delete, db_issue["_id"]])

    return render_template("issues.html", issue_list=issue_list)


# noinspection PyUnusedLocal
@app.errorhandler(404)
def error_missing(exception):
    error_message = "This page cannot be found."
    return render_template("error.html", error_code=404, error_message=error_message), 404


# noinspection PyUnusedLocal
@app.errorhandler(403)
def error_unauthorized(exception):
    error_message = "You are not authorized to view this page. Ensure you have the correct permissions."
    return render_template("error.html", error_code=403, error_message=error_message), 403


# noinspection PyUnusedLocal
@app.errorhandler(500)
def error_crash(exception):
    error_message = "This page has crashed due to an exception. Contact Kazuki Ishikawa and submit a bug report."
    return render_template("error.html", error_code=500, error_message=error_message), 500


if not os.environ.get("EXTERNAL") and __name__ == "__main__":

    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'
    os.environ["maintenance"] = 'False'

    @app.route('/test')
    def test():
        g.redis.publish('titdev-test', 'Look at this. Very " \'cool # message;. ')
        g.redis.publish('titdev-marketeer', 'This is a test of the emergency annoyance system.')
        return render_template("base.html")

    profile = False
    # Profiling
    if profile:
        from werkzeug.contrib.profiler import ProfilerMiddleware
        app.config["PROFILE"] = True
        app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

    app.debug = True
    app.run(host="0.0.0.0")
