import os
import re
from os.path import dirname as parent
APPROOT = parent(parent(parent((os.path.realpath(__file__)))))

# Basic configuration settings
DEBUG = True
HOST = '0.0.0.0'
PORT = 8152
SECRET_KEY = 'a secret key --- MUST set this to something unique and strong'
FORCE_SSL = False
# DANGEROUS: Allow arbitrary Python queries from the browser
ALLOW_PYCODE = False
SYSTEM_EMAIL = 'noreply@yourcompany.com'  # Emails sent from here

# Precompute settings
PRECOMPUTE = True
# The cache is written here; can be the same as KRONOS_URL
CACHE_KRONOS_URL = 'http://localhost:8150'
CACHE_KRONOS_NAMESPACE = 'default_cache'
# It is not recommended to expose the scheduler outside the LAN
SCHEDULER_HOST = '127.0.0.1'
SCHEDULER_PORT = 8157
SCHEDULER_DATABASE_URI = 'sqlite:///%s/scheduler.db' % APPROOT
# When precompute query code fails, emails will be sent to the following
SCHEDULER_FAILURE_EMAILS = [
  'you@yourcompany.com',
  'other@yourcompany.com',
]

# Kronos and metis pointers
KRONOS_URL = 'http://localhost:8150'
KRONOS_NAMESPACE = 'kronos'
METIS_URL = 'http://localhost:8151'

# This database persists all dashboards and settings
SQLALCHEMY_DATABASE_URI = 'sqlite:///%s/app.db' % APPROOT

ENABLE_GOOGLE_AUTH = False
# Google authentication to protect your board from random users
ALLOWED_EMAILS = map(re.compile, [
  # Only user IDs matching regexes in this list will be allowed to create
  # accounts 
  '.+@YOUR_DOMAIN.COM$',
])
GOOGLE_CLIENT_ID = ''
GOOGLE_CLIENT_SECRET = ''
# Set http://yourdomain.com/google_callback as an authorized redirect URI
# when you set up your client ID at https://console.developers.google.com/
