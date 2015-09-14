# TITDev

## Setting up your environment
### Requires
* Python 3.4.3
* "Secrets" json file

### Resources
* Modules found in requirements.txt
* Heroku
* Mongodb (Using Mongolab Heroku Resource)
* PyCharm Community Edition

### Instructions
1. Clone the macalik/TITDev 
2. Create a virtual environment and install dependencies
  * You can initialize one using PyCharm after opening the project by going to: 
    * File > Settings > Project:TITDev > Project Interpreter > Gear > Create VirtualEnv
  * Activate your virtual environment (Windows)
  ```
  (directory you saved the venv)\Scripts\activate.bat
  pip install -r (root github directory)\requirements.txt
  ```
  * In Unix, open terminal and run
  ```
  source (directory you saved the venv)/bin/activate
  pip install -r (root github directory)/requirements.txt
  ```
    * When you want to run the code or install more requirements, you must reactivate your venv.
    * If you are using PyCharm, the instructions above set your default interpreter to the new venv.
      * Right-clicking main.py and selecting "Run 'main'" will run it in the venv interpreter.
3. In the same directory as the cloned github folder, create a folder called "Other-Secrets". Place the "TITDev.json" file there.
    * Directory structure should be (same outer)/Other-Secrets/TITDev.json and (same outer)/TITDev/(Project Files)
4. Run main.py
5. Navigate to localhost:5000

## Dev Notes
### Authentication
* Authentication using the EVE SSO has been implemented. To use on an endpoint, use the decorator:
```
from views.auth import requires_sso
 
@app.route("/")
@requires_sso("level")
def page():
```
  * level is equal to an id found in the eve_auth mongodb database. If the users CharacterOwnerHash in found in the "users" property, it will succeed.
  * "alliance" and "corporation" levels are also available. Matches xml api alliance/corporation ids to the base.json config file.

### EVE XML API Cache
* Any repeatable API calls are cached. Use the following functions in the helpers.caches file to refresh the cache.
  * helpers.caches.stations(): Refreshes the names of all conquerable stations (outposts).
    * Tied to stations collection
  * heleprs.caches.character(char_ids): Gets character names for those not found in the collection.
    * char_ids is a array containing all character ids to check.
    * Tied to characters collection
  * helpers.caches.contracts(keys): Pulls all contracts for the jump freighter service
    * Tied to contracts collection
    * Keys is array of tuples of ("service name", "keyID", "vCode").
    * Defaults to updating all contracts.

### SDE Extraction
* resources.sde_extract is to be run separately on a development computer.
* Opens a file dialog for choosing a fuzzwork sqlite conversion of the ccp static data export
* Converts relevant tables from the sqlite file to static json files used by the application

### Other Notes
* Do not use the session keys "UI_Roles", "UI_Corporation", "UI_Alliance", and the like for authentication checks. 
* If you must do a specific auth check, use views.auth.auth_check(role), where role is an id listed in the eve_auth collection.
  * User must currently be logged in and have a valid session cookie. Session cookie must contain a valid and non-tampered with "CharacterOwnerHash" key.
* Do not use app.debug = True in production. It is trapped by "not os.environ.get("HEROKU")".
* By policy, all auth points will only need the session "CharacterOwnerHash" stored locally client side.
* CharacterOwnerHash is used so that if the character is traded away, the character will lose all roles because the new CharacterOwnerHash taken at sso log in will no longer match with any auth point.
