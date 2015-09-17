import os
from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup
from flask import session

class Sub_Navigation:

    def __init__(self, app):
        sub_nav = Nav()
        #@sub_nav.navigation('security')
        #def nav_security():
            #return  NavBar([View('Test 1', 'auth.log_out'), View('Test 2', 'auth.log_out'), View('Test 3', 'auth.log_out')])
            # for role in session.get("UI_Roles"):
            # if role == "user_admin":

        # Get current page
        # url = os.environ["REQUEST_URI"]

        # Verify user is authenticated for the sub nav access

        sub_nav.init_app(app)





