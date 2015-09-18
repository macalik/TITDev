from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup
from flask import session


class Navigation:

    base = ['TiT', View('Home', 'home'),  View('Account', "account.home")]
    alliance = base + [View('JF Service', "jf.home")]
    corp = base + [View('Corp Main', "corp.home"), View('JF Service', "jf.home")]

    def __init__(self, app):
        nav = Nav()

        @nav.navigation('anon')
        def nav_anon():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"),
                          View('Log In', 'auth.sso_redirect'))

        @nav.navigation('neut')
        def nav_neut():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"),
                          View('Log Out', 'auth.log_out'))

        @nav.navigation('corporation')
        def nav_corp():
            items = Navigation.corp + [View('Log Out', 'auth.log_out')]
            return Navbar(*items)

        @nav.navigation('alliance')
        def nav_alliance():
            items = Navigation.alliance + [View('Log Out', 'auth.log_out')]
            return Navbar(*items)

        @nav.navigation('admin')
        def nav_admin():
            admin_elements = []
            for role in session.get("UI_Roles"):
                if role == "jf_admin":
                    admin_elements.append(View('JF Service', "jf.admin"))
                elif role == "user_admin":
                    admin_elements.append(View('User Roles', "admin.roles"))
                elif role == "jf_pilot":
                    admin_elements.append(View('JF Pilot', "jf.pilot"))
            if session["UI_Corporation"]:
                items = Navigation.corp + [Subgroup('Admin Pages', *admin_elements),
                                           View('Log Out', 'auth.log_out')]
            elif session["UI_Alliance"]:
                items = Navigation.alliance + [Subgroup('Admin Pages', *admin_elements),
                                               View('Log Out', 'auth.log_out')]
            else:
                items = ['TiT', View('Home', 'home'), View('Log Out', 'auth.log_out')]

            return Navbar(*items)

        nav.init_app(app)
