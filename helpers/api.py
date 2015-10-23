from flask import g, session

from helpers import caches

def add_api(request):

 # insert api to database
 # API Module
    error_list = []
    if request.method == "POST":
        if request.form.get("action") == "add":
            error_list = caches.api_keys([(request.form.get("key_id"), request.form.get("vcode"))])
        elif request.form.get("action") == "remove":
            g.mongo.db.api_keys.update({"_id": session["CharacterOwnerHash"]},
                                       {
                                           "$pull": {
                                               "keys": {"key_id": int(request.form.get("key_id"))}
                                           }
                                       })

            return error_list

