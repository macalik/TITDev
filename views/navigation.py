from flask_nav import Nav
from flask_nav.elements import Navbar, View


def init(app):
    nav = Nav()

    @nav.navigation('anon')
    def nav_anon():
        return Navbar('TiT', View('Home', 'home'), View('Log In', 'auth.sso_redirect'))

    @nav.navigation('tit')
    def nav_tit():
        return Navbar('TiT', View('Home', 'home'))

    nav.init_app(app)
