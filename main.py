import os
from flask import Flask, render_template
from flask_bootstrap import Bootstrap

import navigation

app = Flask(__name__)
Bootstrap(app)

navigation.init(app)


@app.route('/')
def hello():
    return render_template("index.html", name="hi")


@app.route('/something')
def other():
    return render_template("base.html", name="hello")

if "HEROKU" not in os.environ and __name__ == "__main__":
    app.debug = True
    app.run()
