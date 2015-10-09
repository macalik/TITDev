from flask import g, session

from helpers import caches

def add_api(request):

 # insert api to database
 error_list = []
 if request.method == "POST":
        if request.form.get("action") == "add":
            g.mongo.db.api_keys.insert( { "key_id": request.form.get("key_id"), "vcode": request.form.get("vcode")})
        elif request.form.get("action") == "remove":
            print(request.form.get("key_id"))
            print(session["CharacterOwnerHash"])
            g.mongo.db.api_keys.update({"_id": session["CharacterOwnerHash"]},
               {
                   "$pull": {
                       "keys": {"key_id": int(request.form.get("key_id"))}
                   }
               })
