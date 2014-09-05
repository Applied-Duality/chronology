from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask_sslify import SSLify

app = Flask(__name__)
app.config.from_object('jia.conf.default_settings')
app.secret_key = app.config['SECRET_KEY']
db = SQLAlchemy(app)

if app.config['FORCE_SSL']:
  sslify = SSLify(app)

import jia.models
import jia.views

# Create tables in sqlite3 db if not present.
db.create_all()
