from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup, Link, RawTag
from flask import session


class Navigation:

    base = ['TiT', View('Home', 'home'),  View('Account', "account.home")]
    after_base = [View('JF Service', "jf.home"), View('Fittings', "fittings.home")]
    alliance = base + after_base

    news_elements = []
    forum_elements = []
    tool_elements = []
    market_elements = []
    news_elements = [Subgroup('News',Link("EN24","http://www.evenews24.com/"),Link("TheMittani","https://www.themittani.com/"),Link("Dev Blog","http://http://community.eveonline.com/news/dev-blogs/"))]
    forum_elements = [Subgroup('Forums',Link("TiT","http://tit.site.nfoservers.com/forums/index.php/"),Link(".EXE","http://www.the-executives.de/smf/index.php/"),Link("Goonswarm","https://goonfleet.com/index.php/"))]
    market_elements = [Subgroup('Market',Link("EVE-Central","https://eve-central.com/"),Link("Evepraisal","http://evepraisal.com/"),Link("Market Basics","https://wiki.goonfleet.com/Using_The_Market"))]
    tactical_elements = [Subgroup('Tactical',Link("Jump Bridge Map","http://www.the-executives.de/smf/index.php?action=dlattach;topic=10062.0;attach=109758;image/"))]
    navigation_elements = [Subgroup('Navigation',Link("dotlan","http://www.dotlan.com/"))]
    wiki_elements = [Subgroup('Wiki',Link(".EXE Wiki","http://www.the-executives.de/smf/dokuwiki/doku.php/"),Link("Goon Wiki","https://wiki.goonfleet.com/"))]
    tool_elements = [Subgroup('Tools',Link(".EXE App","http://www.the-executives.de/app/"))]
    corp = base + [View('Corp Main', "corp.home")] + forum_elements + tool_elements + navigation_elements + market_elements + tactical_elements + wiki_elements + news_elements + after_base

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





