import requests
from flask import session, Blueprint, redirect
from flask import request


from grano import authz
from grano.lib.exc import BadRequest
from grano.lib.serialisation import jsonify
from grano.views.cache import validate_cache
from grano.core import db, github, url_for
from grano.model import Account
from grano.logic import accounts


blueprint = Blueprint('sessions_api', __name__)


@blueprint.route('/api/1/sessions', methods=['GET'])
def status():
    if request.account is not None:
        validate_cache(last_modified=request.account.updated_at)
    return jsonify({
        'logged_in': authz.logged_in(),
        'api_key': request.account.api_key if authz.logged_in() else None,
        'account': accounts.to_rest(request.account) if request.account else None
    })


# TODO: move to project controller
#@blueprint.route('/sessions/authz')
#def get_authz():
#    permissions = {}
#    dataset_name = request.args.get('dataset')
#    if dataset_name is not None:
#        dataset = Dataset.find(dataset_name)
#        permissions[dataset_name] = {
#            'view': True,
#            'edit': authz.dataset_edit(dataset),
#            'manage': authz.dataset_manage(dataset)
#        }
#    return jsonify(permissions)


@blueprint.route('/api/1/sessions/login', methods=['GET'])
def login():
    callback=url_for('sessions_api.authorized')
    if not request.args.get('next_url'):
        raise BadRequest("No 'next_url' is specified.")
    session['next_url'] = request.args.get('next_url')
    return github.authorize(callback=callback)


@blueprint.route('/api/1/sessions/logout', methods=['GET'])
def logout():
    authz.require(authz.logged_in())
    session.clear()
    return redirect(request.args.get('next_url', '/'))


@blueprint.route('/api/1/sessions/callback', methods=['GET'])
@github.authorized_handler
def authorized(resp):
    next_url = session.get('next_url', '/')
    if resp is None or not 'access_token' in resp:
        return redirect(next_url)
    access_token = resp['access_token']
    session['access_token'] = access_token, ''
    res = requests.get('https://api.github.com/user?access_token=%s' % access_token,
            verify=False)
    data = res.json()
    account = Account.by_github_id(data.get('id'))
    if account is None:
        account = accounts.create(data)
        db.session.commit()
    session['id'] = account.id
    return redirect(next_url)
