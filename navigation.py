from flask_nav import Nav
from flask_nav.elements import Navbar, View


def init(app):
    nav = Nav()

    @nav.navigation('anon')
    def nav_anon():
        return Navbar('TiT', View('Home', 'hello'), View('Empty', 'other'))

    @nav.navigation('tit')
    def nav_tit():
        return Navbar('TiT', View('Home', 'hello'), View('Empty', 'other'))

    nav.init_app(app)
