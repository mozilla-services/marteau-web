import socket
import urllib
import os
import time
import datetime
from ConfigParser import NoSectionError
import requests

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound, HTTPNotFound
from pyramid.response import FileResponse
from pyramid_simpleform import Form
#from pyramid_simpleform.renderers import FormRenderer
from pyramid.security import authenticated_userid, forget
from pyramid.exceptions import Forbidden

from mako.lookup import TemplateLookup
import paramiko
import yaml
from redis import Redis

from marteau.node import Node
import marteau
from marteau.util import generate_key
from marteau.fixtures import get_fixtures, get_fixture
from marteau.host import Host

from marteauweb.schemas import JobSchema, NodeSchema


TOPDIR = os.path.dirname(__file__)
MEDIADIR = os.path.join(TOPDIR, 'media')
TMPLDIR = os.path.join(TOPDIR, 'templates')
TMPLS = TemplateLookup(directories=[TMPLDIR])
JOBTIMEOUT = 3600    # one hour
DOCDIR = os.path.join(TOPDIR, 'docs', 'build', 'html')


def check_auth(request):
    if request.user is None:
        raise Forbidden()

    # user white list
    authorized_users = request.registry.settings.get('authorized_users', '')
    authorized_users = authorized_users.split(',')
    for user in authorized_users:
        if request.user == user:
            return request.user

    # domain white list
    authorized_domains = request.registry.settings.get('authorized_domains',
                                                       'mozilla.com')
    authorized_domains = authorized_domains.split(',')
    for domain in authorized_domains:
        if request.user.endswith('@' + domain):
            return request.user

    raise Forbidden()


def time2str(data):
    if data is None:
        return 'Unknown date'
    return datetime.datetime.fromtimestamp(data).strftime('%Y-%m-%d %H:%M:%S')


@view_config(route_name='index', request_method='GET', renderer='index.mako')
def index(request):
    """Index page."""
    queue = request.registry['queue']
    fixtures = get_fixtures().items()
    fixtures.sort()

    return {'jobs': queue.get_jobs(),
            'workers': queue.get_workers(),
            'nodes': list(queue.get_nodes()),
            'failures': queue.get_failures(),
            'successes': queue.get_successes(),
            'get_result': queue.get_result,
            'running': queue.get_running_jobs(),
            'time2str': time2str,
            'messages': request.session.pop_flash(),
            'user': authenticated_userid(request),
            'fixtures': fixtures}


@view_config(route_name='profile', request_method=('GET', 'POST'),
             renderer='profile.mako')
def profile(request):
    """Profile page."""
    queue = request.registry['queue']
    user = authenticated_userid(request)
    if user is None:
        key = None
        hosts = []
    else:
        if 'generate' in request.POST:
            key = generate_key()
            queue.set_key(user, key)
        else:
            key = queue.get_key(user)

        redis = Redis()
        hosts = redis.smembers('marteaudb:hosts:%s' % user)
        hosts = [Host.from_json(host) for host in hosts]

    return {'user': user, 'key': key, 'hosts': hosts,
            'messages': request.session.pop_flash()}


@view_config(route_name='purge', request_method='GET')
def purge(request):
    """Purges all queues in Redis"""
    check_auth(request)
    request.registry['queue'].purge()
    request.session.flash('Purged')
    return HTTPFound('/')


@view_config(route_name='reset', request_method='GET')
def reset_nodes(request):
    """Resets the nodes state to idle."""
    check_auth(request)
    request.registry['queue'].reset_nodes()
    request.session.flash('Reset done.')
    return HTTPFound('/')


@view_config(route_name='test', request_method='GET')
def get_all_jobs(request):
    """Returns all Job"""
    return request.registry['queue'].get_jobs()


@view_config(route_name='addjob', request_method='GET',
             renderer='addjob.mako')
def add_job(request):
    fixtures = get_fixtures().items()
    fixtures.sort()
    return {'time2str': time2str,
            'messages': request.session.pop_flash(),
            'user': authenticated_userid(request),
            'fixtures': fixtures}


@view_config(route_name='test', request_method='POST', renderer='json')
def add_run(request):
    """Adds a run into Marteau"""
    check_auth(request)
    owner = request.user

    #form = Form(request, schema=JobSchema)

    #if not form.validate():
    #    items = form.errors.items()
    #    msg = '%s for "%s"' % (items[0][1], items[0][0])
    #    request.session.flash(msg)
    #    return HTTPFound('/')

    #data = form.data
    data = request.POST
    repo = data.get('repo')
    redirect_url = data.get('redirect_url')
    cycles = data.get('cycles')
    duration = data.get('duration')
    nodes = data.get('nodes')
    test = data.get('test')
    script = data.get('script')

    fixture_plugin = data.get('fixture_plugin')
    fixture_options = {}

    for key, value in request.POST.items():
        if key.startswith('fixture_') and key != 'fixture_plugin':
            fixture_options[key[len('fixture_'):]] = value

    metadata = {'created': time.time(), 'repo': repo}
    queue = request.registry['queue']

    try:
        options = dict(request.registry.settings)
        if 'who.api_factory' in options:
            del options['who.api_factory']
    except NoSectionError:
        options = {}

    job_id = queue.enqueue('marteau.job:run_loadtest', repo=repo,
                           cycles=cycles, nodes_count=nodes, duration=duration,
                           metadata=metadata, email=owner,
                           test=test, script=script,
                           fixture_plugin=fixture_plugin,
                           fixture_options=fixture_options,
                           options=options,
                           workdir=options.get('working_directory'),
                           reportsdir=options.get('reports_directory'))

    request.session.flash("Job %r added." % job_id)

    if 'api_call' not in request.POST:
        return HTTPFound(location='/test/%s' % job_id)

    return {'job_id': job_id}


@view_config(route_name='cancel', request_method='GET')
def _cancel_job(request):
    """Cancels a running Job."""
    check_auth(request)
    jobid = request.matchdict['jobid']
    queue = request.registry['queue']
    queue.cancel_job(jobid)
    queue.cleanup_job(jobid)
    return HTTPFound(location='/')


@view_config(route_name='delete', request_method='GET')
def _delete_job(request):
    """Deletes a job."""
    check_auth(request)
    jobid = request.matchdict['jobid']
    queue = request.registry['queue']
    queue.delete_job(jobid)
    return HTTPFound(location='/')


@view_config(route_name='replay', request_method='GET')
def _requeue_job(request):
    """Replay a job."""
    check_auth(request)
    jobid = request.matchdict['jobid']
    queue = request.registry['queue']
    job_id = queue.replay(jobid)
    return HTTPFound(location='/test/%s' % job_id)


@view_config(route_name='job', request_method='GET', renderer='console.mako')
def _get_result(request):
    """Gets results from a run"""
    jobid = request.matchdict['jobid']
    queue = request.registry['queue']
    status, console = queue.get_result(jobid)
    if status is None:
        status = 'Running'
    else:
        status = status['msg']

    report = status == 'Success'

    return {'status': status,
            'console': console,
            'job': queue.get_job(jobid),
            'time2str': time2str,
            'report': report,
            'user': authenticated_userid(request)}


@view_config(route_name='nodes', request_method='GET',
             renderer='nodes.mako')
def _nodes(request):
    """Nodes page"""
    queue = request.registry['queue']
    return {'nodes': list(queue.get_nodes()),
            'user': authenticated_userid(request)}


@view_config(route_name='node_enable', request_method='GET')
def enable_node(request):
    """Enables/Disables a node."""
    check_auth(request)
    # load existing
    queue = request.registry['queue']
    name = request.matchdict['name']
    node = queue.get_node(name)

    # update the flag
    node.enabled = not node.enabled

    queue.save_node(node)
    return HTTPFound(location='/nodes')


@view_config(route_name='node_test', request_method='GET', renderer='string')
def test_node(request):
    """Runs an SSH call on a node."""
    check_auth(request)
    # trying an ssh connection
    connection = paramiko.client.SSHClient()
    connection.load_system_host_keys()
    connection.set_missing_host_key_policy(paramiko.WarningPolicy())
    name = request.matchdict['name']

    host, port = urllib.splitport(name)
    if port is None:
        port = 22

    username, host = urllib.splituser(host)
    credentials = {}

    if username is not None and ':' in username:
        username, password = username.split(':', 1)
        credentials = {"username": username, "password": password}
    elif username is not None:
        password = None
        credentials = {"username": username}

    try:
        connection.connect(host, port=port, timeout=5, **credentials)
        return 'Connection to %r : OK' % name
    except (socket.gaierror, socket.timeout), error:
        return str(error)


@view_config(route_name='node', request_method='GET')
def get_or_del_node(request):
    """Gets or Deletes a node."""
    name = request.matchdict['name']
    queue = request.registry['queue']

    if 'delete' in request.params:
        check_auth(request)
        queue.delete_node(name)
        return HTTPFound(location='/nodes')

    return queue.get_node(name)


@view_config(route_name='nodes', request_method='POST')
def add_node(request):
    """Adds a new into Marteau"""
    check_auth(request)
    owner = request.user

    form = Form(request, schema=NodeSchema)

    if not form.validate():
        request.session.flash("Bad node name")
        return HTTPFound(location='/nodes')

    node_name = form.data.get('name')
    node = Node(name=node_name, owner=owner)
    queue = request.registry['queue']
    queue.save_node(node)
    return HTTPFound(location='/nodes')


@view_config(route_name='karaoke', request_method='GET')
def karaoke_file(request):
    filename = os.path.join(MEDIADIR, 'marteau.kar')
    return FileResponse(filename,  content_type='audio/midi',
                        content_encoding='UTF-8')


@view_config(route_name='report_file')
def report_dir(request):
    """Returns report files"""
    jobid = request.matchdict['jobid']
    filename = request.matchdict['filename']
    elmts = filename.split(os.sep)
    for unsecure in ('.', '..'):
        if unsecure in elmts:
            return HTTPNotFound()

    reports = dict(request.registry.settings)['reports_directory']
    path = os.path.join(reports, jobid, filename)
    if not os.path.exists(path):
        return HTTPNotFound()
    return FileResponse(path, request)


@view_config(route_name='report_index')
def report_index(request):
    """Redirects / to /index.html"""
    jobid = request.matchdict['jobid']
    return HTTPFound(location='/report/%s/index.html' % jobid)


@view_config(route_name='docs_index')
def doc_index(request):
    """Redirects / to /index.html"""
    return HTTPFound('/docs/index.html')


@view_config(route_name='docs_file')
def doc_dir(request):
    """Returns Sphinx files"""
    filename = request.matchdict['file']
    elmts = filename.split(os.sep)
    for unsecure in ('.', '..'):
        if unsecure in elmts:
            return HTTPNotFound()

    path = os.path.join(DOCDIR, filename)
    return FileResponse(path, request)


@view_config(route_name='fixture_options', renderer='json',
             request_method='GET')
def fixture_options(request):
    fixture = request.matchdict['fixture']
    fixture = get_fixture(fixture)
    # name, default
    # XXX we'll see for the type later
    # name : description, default
    options = []
    for argument in fixture.get_arguments():
        options.append({'name': argument[0], 'description': argument[3],
                        'default': argument[2]})
    return {'items': options}


_PATTERNS = ('https://raw.github.com/mozilla/%s/master/.marteau.yml',
             'https://raw.github.com/mozilla-services/%s/master/.marteau.yml')


@view_config(route_name='project_options', renderer='json',
             request_method='GET')
def project_options(request):
    project = request.matchdict['project']
    project = project.replace('github.com', 'raw.github.com').rstrip('/')
    config = project + '/master/.marteau.yml'

    res = requests.get(config)

    if res.status_code == 200:
        return yaml.load(res.content)

    return {}


@view_config(route_name='hosts', request_method='POST')
def add_host(request):
    user = check_auth(request)
    redis = Redis()
    host = request.POST['host']   # XXX protect

    if redis.sismember('marteaudb:hosts', host):
        request.session.flash('Host already registered.')
        return HTTPFound(location='/profile')

    # creating host
    host = Host(name=host, user=user)
    redis.sadd('marteaudb:hosts:%s' % user, host.to_json())
    redis.sadd('marteaudb:hosts', host.name)
    request.session.flash('Host added.')
    return HTTPFound(location='/profile')


@view_config(route_name='host', request_method=('DELETE', 'GET'))
def delete_host(request):
    user = check_auth(request)
    redis = Redis()
    host = request.matchdict['host']

    if not redis.sismember('marteaudb:hosts', host):
        request.session.flash('Host not found.')
        return HTTPFound(location='/profile')

    user_hosts = 'marteaudb:hosts:%s' % user
    for data in redis.smembers(user_hosts):
        host_ob = Host.from_json(data)
        if host_ob.name == host:
            redis.srem(user_hosts, data)
            redis.srem('marteaudb:hosts', host)
            request.session.flash('Host removed.')
            break

    return HTTPFound(location='/profile')


@view_config(route_name='verify_host', request_method='GET')
def verify_host(request):
    user = check_auth(request)
    redis = Redis()
    host = request.matchdict['host']

    if not redis.sismember('marteaudb:hosts', host):
        request.session.flash('Host not found.')
        return HTTPFound(location='/profile')

    user_hosts = 'marteaudb:hosts:%s' % user
    for data in redis.smembers(user_hosts):
        host_ob = Host.from_json(data)
        if host_ob.name == host:
            if host_ob.verify():
                redis.srem(user_hosts, data)
                redis.sadd(user_hosts, host_ob.to_json())
                request.session.flash('Host verified.')
            else:
                request.session.flash('Host verification failed.')
            break

    return HTTPFound(location='/profile')
