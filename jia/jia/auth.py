import functools
import urllib
import requests

from flask import Blueprint
from flask import current_app
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask import session

from jia import db
from jia.models import User

auth_uri = 'https://accounts.google.com/o/oauth2/auth'
token_uri = 'https://accounts.google.com/o/oauth2/token'
scope = ('https://www.googleapis.com/auth/userinfo.profile',
         'https://www.googleapis.com/auth/userinfo.email')
profile_uri = 'https://www.googleapis.com/oauth2/v1/userinfo'

ERROR_MESSAGE = """
User {} is not allowed.
<a href="https://security.google.com/settings/security/permissions">
Revoke access on this account before trying again</a>.
"""

auth = Blueprint('auth', __name__)


def http_scheme():
  if current_app.config['FORCE_SSL']:
    return 'https'
  else:
    return 'http'


def require_auth(fn):
  @functools.wraps(fn)
  def decorated(*args, **kwargs):
    if current_app.config['ENABLE_GOOGLE_AUTH'] and not 'user' in session:
      params = dict(response_type='code',
                    scope=' '.join(scope),
                    client_id=current_app.config['GOOGLE_CLIENT_ID'],
                    approval_prompt='auto',
                    redirect_uri=url_for('auth.google_callback',
                                         _external=True,
                                         _scheme=http_scheme()))
      url = auth_uri + '?' + urllib.urlencode(params)
      session['next'] = request.path
      return redirect(url)
    return fn(*args, **kwargs)
  return decorated


@auth.route('/google_callback')
def google_callback():
  if 'code' in request.args:
    code = request.args.get('code')
    redirect_to = session.pop('next', url_for('app.index', _external=True,
                                              _scheme=http_scheme()))
    data = dict(code=code,
                client_id=current_app.config['GOOGLE_CLIENT_ID'],
                client_secret=current_app.config['GOOGLE_CLIENT_SECRET'],
                redirect_uri=url_for('auth.google_callback', _external=True,
                                     _scheme=http_scheme()),
                grant_type='authorization_code')
    r = requests.post(token_uri, data=data)
    access_token = r.json()['access_token']
    r = requests.get(profile_uri, params={'access_token': access_token})
    user_info = r.json()

    user = User.query.filter_by(email=user_info['email']).first()
    if user:
      session['user'] = user.id
      return redirect(redirect_to)
    else:
      if not user_info['verified_email']:
        return render_template('verify.html')
      for pattern in current_app.config['ALLOWED_EMAILS']:
        if pattern.match(user_info['email']):
          user = User()
          user.name = user_info['name']
          user.email = user_info['email']
          user.picture = user_info['picture']
          user.locale = user_info['locale']
          user.hd = user_info['hd']
          db.session.add(user)
          db.session.commit()
          session['user'] = user.id
          return redirect(redirect_to)
      return ERROR_MESSAGE.format(user_info['email'])
  else:
    return 'ERROR'
