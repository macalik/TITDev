import json

from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup, Link
from flask import session


class Navigation:

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    base = ['TiT', View('Home', 'home'),  View('Account', "account.home")]
    after_base = [View('JF Service', "jf.home"), View('Buyback Service', 'buyback.home'),
                  View('Fittings', "fittings.home"), View("Market Service", "ordering.home")]
    alliance = base + after_base
    corp = base + [View('Corp Main', "corp.home"), Link("Corp Forums (Testing)", base_config["forum_url"])] + after_base

    def __init__(self, app):
        nav = Nav()

        @nav.navigation('anon')
        def nav_anon():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"),
                          View('Buyback Service', 'buyback.home'), View('Log In', 'auth.sso_redirect'))

        @nav.navigation('neut')
        def nav_neut():
            return Navbar('TiT', View('Home', 'home'), View('Account', "account.home"), View('JF Service', "jf.home"),
                          View('Buyback Service', 'buyback.home'), View('Log Out', 'auth.log_out'))

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
            market_service = False
            for role in session.get("UI_Roles"):
                if role == "jf_admin":
                    admin_elements += [View('JF Routes', "jf.admin"), View('JF Stats', "jf.stats")]
                elif role == "user_admin":
                    admin_elements.append(View('User Roles', "admin.roles"))
                elif role == "jf_pilot":
                    admin_elements.append(View('JF Pilot', "jf.pilot"))
                elif role == "buyback_admin":
                    admin_elements.append(View('Buyback Service', 'buyback.admin'))
                elif role in ["ordering_marketeer", "ordering_admin"] and not market_service:
                    admin_elements.append(View('Market Service', 'ordering.admin'))
                    market_service = True
                elif role == "security_officer":
                    admin_elements.append(View('Security Info', 'security.home'))
            if session["UI_Corporation"]:
                items = Navigation.corp + [Subgroup('Admin Pages', *admin_elements),
                                           View('Log Out', 'auth.log_out')]
            elif session["UI_Alliance"]:
                items = Navigation.alliance + [Subgroup('Admin Pages', *admin_elements),
                                               View('Log Out', 'auth.log_out')]
            else:
                return nav_neut()

            return Navbar(*items)

        nav.init_app(app)
