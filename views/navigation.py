from flask_nav import Nav
from flask_nav.elements import Navbar, View


class Navigation:
    def __init__(self, app):
        nav = Nav()

        @nav.navigation('anon')
        def nav_anon():
            return Navbar('TiT', View('Home', 'home'), View('Log In', 'auth.sso_redirect'))

        @nav.navigation('tit')
        def nav_tit():
            return Navbar('TiT', View('Home', 'home'), View('JF Service', "jf.home"), View('Log Out', 'auth.log_out'))

        nav.init_app(app)
