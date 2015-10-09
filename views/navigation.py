from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup
from flask import session


class Navigation:

    base = ['TiT', View('Home', 'home'),  View('Account', "account.home")]
    after_base = [View('JF Service', "jf.home"), View('Fittings', "fittings.home")]
    alliance = base + after_base
    corp = base + [View('Corp Main', "corp.home")] + after_base

    def __init__(self, app):
        nav = Nav()

        @nav.navigation('anon')
        def nav_anon():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"),
                          View('Log In', 'auth.sso_redirect'))

        @nav.navigation('neut')
        def nav_neut():
            return Navbar('TiT', View('Home', 'home'), View('Account', "account.home"), View('JF Service', "jf.home"),
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
                    admin_elements += [View('JF Service', "jf.admin"), View('JF Stats', "jf.stats")]
                elif role == "user_admin":
                    admin_elements.append(View('User Roles', "admin.roles"))
                    admin_elements.append(View('Security Dashboard', "security_dashboard.load"))
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





