import os
import json
import logging

from flask import Flask
from flask_bootstrap import Bootstrap, WebCDN
from flask_pymongo import PyMongo
import redis


app = Flask(__name__)

# Set up logging
console_logger = logging.StreamHandler()
console_format = logging.Formatter(" %(asctime)s %(levelname)s: %(message)s [in %(module)s:%(lineno)d]")
console_logger.setFormatter(console_format)
console_logger.setLevel(logging.WARNING)
app.logger.addHandler(console_logger)


if os.environ.get("EXTERNAL"):
    app.config["MONGO_URI"] = os.environ["MONGO_URI"]
    app.config["MONGO_CONNECT"] = False
    app.secret_key = os.environ["random_key"]
    app.config["CELERY_BROKER_URL"] = os.environ["REDIS_URL"]
    app.config["CELERY_RESULT_BACKEND"] = os.environ["REDIS_URL"]
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)
    app.config["MONGO_HOST"] = secrets["mongo-host"]
    app.config["MONGO_DBNAME"] = secrets["mongo-db"]
    app.config["MONGO_USERNAME"] = secrets["mongo-user"]
    app.config["MONGO_PASSWORD"] = secrets["mongo-password"]
    app.config["MONGO_PORT"] = secrets["mongo-port"]
    app.config["CELERY_BROKER_URL"] = secrets["redis-host"]
    app.config["CELERY_RESULT_BACKEND"] = secrets["redis-host"]
    app.config["MONGO_CONNECT"] = False
    app.secret_key = secrets["random_key"]

Bootstrap(app)
cdn_theme_url = "https://maxcdn.bootstrapcdn.com/bootswatch/3.3.5/sandstone/"
app.extensions['bootstrap']['cdns']["theme"] = WebCDN(cdn_theme_url)  # CDN Theme
app_mongo = PyMongo(app)

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
app_redis = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, password=redis_password)
