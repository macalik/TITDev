import json
from hashlib import sha1

from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup, Link, Text
from flask_bootstrap.nav import BootstrapRenderer
from flask import session, url_for
from dominate import tags


class LinkTab(Link):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class LogIn(View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class SeparatorAlign(Text):
    def __init__(self):
        super().__init__("")


class Navigation:

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    base = ['TiT', View('Home', 'home'),  View('Account', "account.home")]
    services = [View('JF Service', "jf.home"), View('Buyback Service', 'buyback.home'),
                View('Fittings', "fittings.home"), View("Market Service", "ordering.home")]
    settings = [SeparatorAlign(), View("Bug Report", 'issues'), View("Change Theme", "settings"),
                View('Log Out', 'auth.log_out')]
    alliance = base + services
    corp = base + [Subgroup("Corporation", View('Corp Main', "corp.home"),
                            LinkTab("Corp Forums", base_config["forum_url"])),
                   Subgroup("Services", *services)]

    def __init__(self, app):
        nav = Nav()

        # noinspection PyUnusedLocal,PyAbstractClass,PyMethodMayBeStatic,PyPep8Naming
        @nav.renderer('custom')
        class CustomRenderer(BootstrapRenderer):

            # External links now open in new tab
            def visit_LinkTab(self, node):
                item = tags.li()
                item.add(tags.a(node.text, href=node.get_url(), target="_blank"))

                return item

            def visit_LogIn(self, node):
                item = tags.li()
                inner = item.add(tags.a(href=node.get_url(), _class="nav-image"))
                inner.add(tags.img(src=url_for("static", filename="sso_login.png")))
                if node.active:
                    item['class'] = 'active'
                return item

            def visit_SeparatorAlign(self, node):
                return NotImplementedError

            def visit_Navbar(self, node):
                # create a navbar id that is somewhat fixed, but do not leak any
                # information about memory contents to the outside
                node_id = self.id or sha1(str(id(node)).encode()).hexdigest()

                root = tags.nav() if self.html5 else tags.div(role='navigation')
                root['class'] = 'navbar navbar-default'

                cont = root.add(tags.div(_class='container-fluid'))

                # collapse button
                header = cont.add(tags.div(_class='navbar-header'))
                btn = header.add(tags.button())
                btn['type'] = 'button'
                btn['class'] = 'navbar-toggle collapsed'
                btn['data-toggle'] = 'collapse'
                btn['data-target'] = '#' + node_id
                btn['aria-expanded'] = 'false'
                btn['aria-controls'] = 'navbar'

                btn.add(tags.span('Toggle navigation', _class='sr-only'))
                btn.add(tags.span(_class='icon-bar'))
                btn.add(tags.span(_class='icon-bar'))
                btn.add(tags.span(_class='icon-bar'))

                # title may also have a 'get_url()' method, in which case we render
                # a brand-link
                if node.title is not None:
                    if hasattr(node.title, 'get_url'):
                        header.add(tags.a(node.title.text, _class='navbar-brand',
                                          href=node.title.get_url()))
                    else:
                        header.add(tags.span(node.title, _class='navbar-brand'))

                bar = cont.add(tags.div(
                    _class='navbar-collapse collapse',
                    id=node_id,
                ))
                bar_list = bar.add(tags.ul(_class='nav navbar-nav'))
                bar_list_right = bar.add(tags.ul(_class='nav navbar-nav navbar-right'))

                to_right = False
                for item in node.items:
                    if isinstance(item, SeparatorAlign):
                        to_right = True
                        continue
                    if not to_right:
                        bar_list.add(self.visit(item))
                    else:
                        bar_list_right.add(self.visit(item))

                return root

        @nav.navigation('anon')
        def nav_anon():
            return Navbar('TiT', View('Home', 'home'),
                          View('Buyback Service', 'buyback.home'), View('JF Service', "jf.home"),
                          View('Recruitment', 'recruitment.home'),
                          SeparatorAlign(), View("Change Theme", "settings"), LogIn('Log In', 'auth.sso_redirect'))

        @nav.navigation('neut')
        def nav_neut():
            return Navbar('TiT', View('Home', 'home'), View('Account', "account.home"),
                          View('Buyback Service', 'buyback.home'), View('JF Service', "jf.home"),
                          View('Recruitment', 'recruitment.home'),
                          SeparatorAlign(), View("Change Theme", "settings"), View('Log Out', 'auth.log_out'))

        @nav.navigation('corporation')
        def nav_corp():
            items = Navigation.corp + Navigation.settings
            return Navbar(*items)

        @nav.navigation('alliance')
        def nav_alliance():
            items = Navigation.alliance + Navigation.settings
            return Navbar(*items)

        @nav.navigation('admin')
        def nav_admin():
            admin_elements = []
            role_elements = []
            market_service = False
            for role in session.get("UI_Roles"):
                if role == "jf_admin":
                    admin_elements += [View('JF Routes', "jf.admin"), View('JF Stats', "jf.stats")]
                elif role == "user_admin":
                    admin_elements.append(View('User Roles', "admin.roles"))
                elif role == "jf_pilot":
                    role_elements.append(View('JF Service', "jf.pilot"))
                elif role == "buyback_admin":
                    admin_elements.append(View('Buyback Service', 'buyback.admin'))
                elif role in ["ordering_marketeer", "ordering_admin"] and not market_service:
                    role_elements.append(View('Market Service', 'ordering.admin'))
                    market_service = True
                elif role == "security_officer":
                    role_elements.append(View('Security Info', 'security.home'))
                    admin_elements.append(View('Recruitment Settings', 'recruitment.admin'))
                elif role in ["recruiter", "security_officer"]:
                    role_elements.append(View('Recruitment Apps', 'recruitment.applications'))
            subs = []
            if role_elements:
                subs.append(Subgroup('Role Pages', *role_elements))
            if admin_elements:
                subs.append(Subgroup('Admin Pages', *admin_elements))
            if session["UI_Corporation"]:
                items = Navigation.corp + subs + Navigation.settings
            elif session["UI_Alliance"]:
                items = Navigation.alliance + subs + Navigation.settings
            else:
                return nav_neut()

            return Navbar(*items)

        nav.init_app(app)
