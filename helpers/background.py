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
        # rate_limit = 30
        # rate_wait = 1
        # error_rate_limit = 300
        # error_wait = 300
        # Discord:
        rate_limit = 1
        rate_wait = 10
        error_rate_limit = 120
        error_wait = 60
        counter = 0
        for api_group in g.mongo.db.api_keys.find():
            user_api_list = set()
            if not api_group.get("keys") and api_group["_id"] == "unassociated":
                pass
            else:
                print("ID: {0}".format(api_group["_id"]))
                # Refresh Crest
                try:
                    temp1, temp2 = auth_crest(api_group["_id"], True, True)
                except KeyError:
                    print("Failed at {0}".format(api_group["_id"]))
                else:
                    if not temp1 or not temp2:
                        print("Failed at {0}".format(api_group["_id"]))

                for api_key_item in api_group["keys"]:
                    counter += 1
                    if not counter % rate_limit:
                        print("At api {0}. Waiting {1}.".format(counter, rate_wait))
                        time.sleep(rate_wait)
                    if not counter % error_rate_limit:
                        print("At api {0}. Waiting {1}.".format(counter, error_wait))
                        time.sleep(error_wait)
                    user_api_list.add((api_key_item["key_id"], api_key_item["vcode"]))
                api_keys(list(user_api_list), dashboard_id=api_group["_id"])
        print("Finished at api {0}.".format(counter))

        print("Forcing forum log outs")
        for user in g.mongo.db.users.find():
            if user.get("email"):
                forum_edit(user, "log_out")
        print("Finished forcing forum log outs for all users")

        g.mongo.db.preferences.update_one({"_id": "updates"}, {
            "$set": {"api_validation": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}})
