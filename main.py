import os
import json
import logging
import datetime

from flask import Flask, render_template, g, session, jsonify, request
from flask_bootstrap import Bootstrap
from flask_pymongo import PyMongo
from flask_oauthlib.provider import OAuth2Provider
from bson.objectid import ObjectId

from views.navigation import Navigation
from views.auth import auth, requires_sso
from views.jump_freighter import jf
from views.admin import admin
from views.account import account
from views.corp import corp
from views.fittings import fittings
from views.buyback import buyback
from views.ordering import ordering

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
oauth = OAuth2Provider(app)

app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(jf, url_prefix="/jf")
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(account, url_prefix="/account")
app.register_blueprint(corp, url_prefix="/corp")
app.register_blueprint(fittings, url_prefix="/fittings")
app.register_blueprint(buyback, url_prefix="/buyback")
app.register_blueprint(ordering, url_prefix="/ordering")

# Set up logging
console_logger = logging.StreamHandler()
console_format = logging.Formatter(" %(asctime)s %(levelname)s: %(message)s [in %(module)s:%(lineno)d]")
console_logger.setFormatter(console_format)
console_logger.setLevel(logging.WARNING)
app.logger.addHandler(console_logger)


@app.before_first_request
def app_init():
    # Check if stations are loaded
    db_check_stations = app_mongo.db.stations.find_one({"_id": 60003760})  # Use Jita as check
    if not db_check_stations:
        # Load statics into memory
        with open("resources/staStations.json", "r") as staStations_file:
            stations_list = json.load(staStations_file)
        app_mongo.db.stations.insert([{"_id": int(key), "name": value} for key, value in stations_list.items()])

    # Check if items are loaded
    db_check_items = app_mongo.db.items.find_one({"_id": 34})  # Use Tritanium as check
    if not db_check_items:
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


@app.before_request
def db_init():
    g.mongo = app_mongo


@app.teardown_request
def cleanup(exception=None):
    if exception:
        print("Error: ", exception)


@app.route('/')
def home():
    return render_template("index.html")


# API and OAuth2

class OAuth2Client:

    name = ""
    description = ""

    user_id = ""
    user = ""

    client_id = ""
    client_secret = ""

    client_type = "public"
    redirect_uris = []
    default_redirect_uri = ""
    default_scopes = []

    def __init__(self, input_client_id=None):
        if input_client_id:
            db_info = g.mongo.db.oauth2_clients.find_one({"_id": ObjectId(input_client_id)})
            self.name = db_info.get("name")
            self.description = db_info.get("description")
            self.user_id = db_info.get("user_id")
            self.user = db_info.get("user")
            self.client_id = str(db_info["_id"])
            self.client_secret = db_info["client_secret"]
            self.client_type = db_info["client_type"]
            self.redirect_uris = db_info["redirect_uris"]
            self.default_redirect_uri = db_info["redirect_uris"][0]
            self.default_scopes = db_info["default_scopes"]


class OAuth2Grant:

    grant_id = ObjectId()
    user = ""
    client_id = ""
    code = ""
    redirect_uri = ""
    expires = datetime.datetime.utcnow()
    scopes = []

    def __init__(self, input_client_id=None, input_code=None):
        if input_client_id and input_code:
            db_info = g.mongo.db.oauth2_grants.find_one({"client_id": input_client_id, "code": input_code})
            self.user = db_info["user"]
            self.client_id = db_info["client_id"]
            self.code = db_info["code"]
            self.redirect_uri = db_info["redirect_uri"]
            self.expires = db_info["expires"].replace(tzinfo=None)
            self.scopes = db_info["scopes"]
            self.grant_id = db_info["_id"]

    def delete(self):
        g.mongo.db.oauth2_grants.remove({"_id": self.grant_id})
        return self


class OAuth2Token:

    token_id = ObjectId()
    client_id = ""
    user = ""

    token_type = ""

    access_token = ""
    refresh_token = ""
    expires = datetime.datetime.utcnow()
    scopes = []

    def __init__(self, input_access_token=None, input_refresh_token=None):
        db_info = None
        if input_access_token or input_refresh_token:
            if input_access_token:
                db_info = g.mongo.db.oauth2_tokens.find_one({"access_token": input_access_token})
            else:
                db_info = g.mongo.db.oauth2_tokens.find_one({"refresh_token": input_refresh_token})

        if db_info:
            self.client_id = db_info["client_id"]
            self.user = db_info["user"]
            self.token_type = db_info["token_type"]
            self.access_token = db_info["access_token"]
            self.refresh_token = db_info["refresh_token"]
            self.expires = db_info["expires"].replace(tzinfo=None)
            self.scopes = db_info["scopes"]
            self.token_id = db_info["_id"]


@oauth.clientgetter
def load_client(client_id):
    return OAuth2Client(client_id)


@oauth.grantgetter
def load_grant(client_id, code):
    return OAuth2Grant(client_id, code)


# noinspection PyUnusedLocal
@oauth.grantsetter
def save_grant(client_id, code, inner_request, *args, **kwargs):
    expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=300)
    g.mongo.db.oauth2_grants.insert({
        "client_id": client_id,
        "code": code["code"],
        "redirect_uri": inner_request.redirect_uri,
        "scopes": inner_request.scopes,
        "user": session["CharacterName"],
        "expires": expires
    })
    grant = OAuth2Grant()
    grant.client_id = client_id
    grant.code = code["code"]
    grant.redirect_uri = inner_request.redirect_uri,
    grant.scopes = inner_request.scopes
    grant.user = session["CharacterName"],
    grant.expires = expires

    return grant


# noinspection PyShadowingNames
@oauth.tokengetter
def load_token(access_token=None, refresh_token=None):
    if access_token:
        return OAuth2Token(input_access_token=access_token)
    else:
        return OAuth2Token(input_refresh_token=refresh_token)


# noinspection PyUnusedLocal
@oauth.tokensetter
def save_token(token, inner_request, *args, **kwargs):
    g.mongo.db.oauth2_tokens.remove({"client_id": inner_request.client.client_id, "user": inner_request.user})

    expires_in = token.get("expires_in")
    expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
    g.mongo.db.oauth2_tokens.insert({
        "client_id": inner_request.client_id,
        "user": inner_request.user,
        "token_type": token["token_type"],
        "access_token": token["access_token"],
        "refresh_token": token["refresh_token"],
        "expires": expires,
        "scopes": token["scope"].split()
    })

    tok = OAuth2Token()
    tok.access_token = token["access_token"]
    tok.refresh_token = token["refresh_token"]
    tok.token_type = token["token_type"]
    tok.scopes = token["scope"].split()
    tok.expires = expires
    tok.client_id = inner_request.client.client_id
    tok.user = inner_request.user

    return tok


# noinspection PyUnusedLocal
@app.route("/oauth/authorize", methods=['GET', 'POST'])
@requires_sso("forum")
@oauth.authorize_handler
def authorize(*args, **kwargs):
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})
    if user and user.get("email") and user["corporation_id"] == base_config["corporation_id"]:
        return True
    return False


@app.route("/oauth/token", methods=['POST'])
@oauth.token_handler
def access_token():
    return None


@app.route("/oauth/revoke")
@oauth.revoke_handler
def revoke_token(): pass


@app.route("/api/user/<name>")
@oauth.require_oauth()
def api_user(name):
    if name == "me":
        # noinspection PyUnresolvedReferences
        db_user = g.mongo.db.users.find_one({"character_name": request.oauth.user})
    else:
        db_user = g.mongo.db.users.find_one({"character_name": name})

    if db_user:
        return jsonify(
            user_id=db_user["character_id"],
            username=db_user["character_name"],
            name=db_user["character_name"],
            email=db_user.get("email", "None")
        )
    else:
        return jsonify(
            user_id=0,
            username="Null",
            name="Null",
            email="None"
        )


if not os.environ.get("HEROKU") and __name__ == "__main__":

    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

    @app.route('/test')
    def test():
        return render_template("base.html")

    # Profiling
    # from werkzeug.contrib.profiler import ProfilerMiddleware
    # app.config["PROFILE"] = True
    # app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

    app.debug = True
    app.run()
