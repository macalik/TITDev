import time
import datetime

from functools import wraps

from celery_app import celery, app, g, app_mongo, app_redis

from helpers.caches import contracts, api_keys
from views.auth import auth_crest, forum_edit, discord_check


def needs_database():
    def decorator(function):
        @wraps(function)
        def decorated_function(*args, **kwargs):
            with app.app_context():
                g.mongo = app_mongo
                g.redis = app_redis
                return function(*args, **kwargs)
        return decorated_function
    return decorator


@celery.task()
def add_together(a, b):
    return a + b


@celery.task(ignore_result=True)
@needs_database()
def jf_update(*args, **kwargs):
    contracts(*args, **kwargs)


@celery.task(ignore_result=True)
@needs_database()
def discord_check_all(*args, **kwargs):
    user_list = []
    for user in g.mongo.db.users.find():
        if user.get("discord_id"):
            user_list.append([user["_id"], user["discord_id"], user["character_name"]])
    print("{0} users to adjust".format(len(user_list)))
    for user_group in user_list:
        print("Discord Sync: {0}".format(user_group[2]))
        discord_check(*user_group)
        time.sleep(25)


@celery.task(ignore_result=True, rate_limit=10)
@needs_database()
def discord_check_wait(user_id, discord_id, character_name):
    discord_check(user_id, discord_id, character_name)


@celery.task(ignore_result=True, rate_limit="1/m")
@needs_database()
def auth_crest_wait(code, refresh=False, discord_roles=True):
    print(">> Running Crest Auth")
    auth_crest(code, refresh, discord_roles)


@celery.task(ignore_result=True, rate_limit="50/m")
@needs_database()
def api_keys_wait(api_key_list, unassociated=False, dashboard_id=None):
    print(">> Running API Key")
    api_keys(api_key_list, unassociated, dashboard_id)


@celery.task(ignore_result=True)
@needs_database()
def api_validation():
    # Check if something is running
    updates = g.mongo.db.preferences.find_one({"_id": "updates"})
    if not updates or not updates.get("api_validation") or not updates.get("api_validation", "").startswith("running"):
        g.mongo.db.preferences.update_one({"_id": "updates"}, {
            "$set": {"api_validation": "running. Started at: {0}".format(
                    datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))}}, upsert=True)
        # EVE:
        # General rate: 30 request / sec
        # Error rate: 300 requests / 3 minutes (avg. 100/min, 5/3sec = 1.67/sec)
        # Discord: 120 requests / minute (avg. 2/sec)
        counter = 0
        auth_crest_list = []
        api_keys_list = []

        for api_group in g.mongo.db.api_keys.find():
            user_api_list = set()
            if not api_group.get("keys") and api_group["_id"] == "unassociated":
                pass
            else:
                # Refresh Crest
                try:
                    auth_crest_list.append([api_group["_id"], True, True])
                except KeyError:
                    print("Failed at {0}".format(api_group["_id"]))

                for api_key_item in api_group["keys"]:
                    user_api_list.add((api_key_item["key_id"], api_key_item["vcode"]))
                api_keys_list.append([list(user_api_list), False, api_group["_id"]])

        # Run without database cursor connection
        for auth_crest_parameters, api_keys_parameters in zip(auth_crest_list, api_keys_list):
            counter += 1
            if not counter % 10:
                print("At user {0}".format(counter))
            auth_crest_wait.delay(*auth_crest_parameters)
            api_keys_wait.delay(*api_keys_parameters)
            time.sleep(60)

        print("Finished at user {0}.".format(counter))

        print("Forcing forum log outs")
        for user in g.mongo.db.users.find():
            if user.get("email"):
                forum_edit(user, "log_out")
        print("Finished forcing forum log outs for all users")

        g.mongo.db.preferences.update_one({"_id": "updates"}, {
            "$set": {"api_validation": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}})
