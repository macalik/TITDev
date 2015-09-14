from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup
from flask import session


class Navigation:
    def __init__(self, app):
        nav = Nav()

        @nav.navigation('anon')
        def nav_anon():
            return Navbar('TiT', View('Home', 'home'), View('Log In', 'auth.sso_redirect'))

        @nav.navigation('corporation')
        def nav_corp():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"), View('Log Out', 'auth.log_out'))

        @nav.navigation('alliance')
        def nav_alliance():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"), View('Log Out', 'auth.log_out'))

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

            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"),
                          Subgroup('Admin Pages', *admin_elements),
                          View('Log Out', 'auth.log_out'))

        nav.init_app(app)
