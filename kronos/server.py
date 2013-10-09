import gevent
import gevent.pool
import json
import os
import sys
import time

from collections import defaultdict
from gunicorn.app.base import Application

import kronos

# Validate settings before importing anything else.
from kronos.core.validators import validate_settings
from kronos.conf import settings; validate_settings(settings)

from kronos.constants.order import ResultOrder
from kronos.core.validators import validate_event
from kronos.core.validators import validate_stream
from kronos.storage import router
from kronos.utils.decorators import endpoint
from kronos.utils.decorators import ENDPOINTS
from kronos.utils.streams import get_stream_properties

GREENLET_POOL = gevent.pool.Pool(size=settings.node['greenlet_pool_size'])


@endpoint('/1.0/index')
def index(environment, start_response, headers):
  """
  Return the status of this Kronos instance + its backends>
  Doesn't expect any URL parameters.
  """

  status = {'service': 'kronosd',
            'version': kronos.get_version(),
            'id': settings.node['id'],
            'fields': settings.stream['fields'],
            'storage': {}}

  # Check if each backend is alive
  for name, backend in router.get_backends():
    status['storage'][name] = {'ok': backend.is_alive(),
                               'backend': settings.storage[name]['backend']}

  start_response('200 OK', headers)
  return json.dumps(status)

@endpoint('/1.0/events/put', methods=['POST'])
def put_events(environment, start_response, headers):
  """
  Store events in backends
  POST body should contain a JSON encoded version of:
    { stream_name1 : [event1, event2, ...],
      stream_name2 : [event1, event2, ...],
    ...
    }
  Where each event is a dictionary of keys and values.
  """

  start_time = time.time()
  errors = []
  events_to_insert = defaultdict(list)

  # Validate streams and events
  for stream, events in environment['json'].iteritems():
    try:
      validate_stream(stream)
    except Exception, e:
      errors.append(repr(e))
      continue

    for event in events:
      try:
        validate_event(event)
        events_to_insert[stream].append(event)
      except Exception, e:
        errors.append(repr(e))

  # Spawn greenlets to insert events asynchronously into matching backends.
  greenlets = []
  for stream, events in events_to_insert.iteritems():
    backends = router.backends_to_mutate(stream)
    for backend, conf in backends.iteritems():
      greenlet = GREENLET_POOL.spawn(backend.insert, stream, events, conf)
      greenlets.append(greenlet)

  # TODO(usmanm): Add async option to API and bypass this wait in that case?
  # Wait for all backends to finish inserting.
  gevent.joinall(greenlets)

  # Did any greenlet fail?
  for greenlet in greenlets:
    if not greenlet.successful():
      errors.append(repr(greenlet.exception))

  # Return count of valid events per stream.
  response = { stream : len(events) for stream, events in
                                        events_to_insert.iteritems() }
  response['@took'] = '{0}ms'.format(1000 * (time.time() - start_time))
  if errors:
    response['@errors'] = errors

  start_response('200 OK', headers)
  return json.dumps(response)


# TODO(usmanm): gzip compress response stream?
@endpoint('/1.0/events/get', methods=['POST'])
def get_events(environment, start_response, headers):
  """
  Retrieve events
  POST body should contain a JSON encoded version of:
    { stream : stream_name,
      start_time : starting_time_as_kronos_time,
      end_time : ending_time_as_kronos_time,
      start_id : only_return_events_with_id_greater_than_me,
      limit: optional_maximum_number_of_events,
      order: ResultOrder.ASCENDING or ResultOrder.DESCENDING (default
             ResultOrder.ASCENDING)
    }
  Either start_time or start_id should be specified. If a retrieval breaks
  while returning results, you can send another retrieval request and specify
  start_id as the last id that you saw. Kronos will only return events that
  occurred after the event with that id.
  """

  request_json = environment['json']
  try:
    validate_stream(request_json['stream'])
  except Exception as e:
    start_response('400 Bad Request', headers)
    yield json.dumps({'@errors' : [repr(e)]})
    return

  limit = int(request_json.get('limit', sys.maxint))
  if limit <= 0:
    events_from_backend = []
  else:
    backend, configuration = router.backend_to_retrieve(request_json['stream'])
    events_from_backend = backend.retrieve(
        request_json['stream'],
        long(request_json.get('start_time', 0)),
        long(request_json['end_time']),
        request_json.get('start_id'),
        configuration,
        order=request_json.get('order', ResultOrder.ASCENDING),
        limit=limit)
  
  start_response('200 OK', headers)
  for event in events_from_backend:
    # TODO(usmanm): Once all backends start respecting limit, remove this check.
    if limit <= 0:
      break
    yield '{0}\r\n'.format(json.dumps(event))
    limit -= 1
  yield ''


@endpoint('/1.0/events/delete', methods=['POST'])
def delete_events(environment, start_response, headers):
  """
  Delete events
  POST body should contain a JSON encoded version of:
    { stream : stream_name,
      start_time : starting_time_as_kronos_time,
      end_time : ending_time_as_kronos_time,
      start_id : only_delete_events_with_id_gte_me,
    }
  Either start_time or start_id should be specified. 
  """

  request_json = environment['json']
  try:
    validate_stream(request_json['stream'])
  except Exception as e:
    start_response('400 Bad Request', headers)
    return json.dumps({'@errors' : [repr(e)]})

  backends = router.backends_to_mutate(request_json['stream'])
  status = {}
  for backend, conf in backends.iteritems():
    status[backend.name] = backend.delete(
        request_json['stream'],
        long(request_json.get('start_time', 0)),
        long(request_json['end_time']),
        request_json.get('start_id'),
        conf)
  start_response('200 OK', headers)
  return json.dumps(status)


@endpoint('/1.0/streams', methods=['GET'])
def list_streams(environment, start_response, headers):
  start_response('200 OK', headers)
  streams_seen_so_far = set()
  for pattern, backend in router.get_backend_to_read():
    for stream in backend.streams():
      if stream.startswith(pattern) and stream not in streams_seen_so_far:
        streams_seen_so_far.add(stream)
        properties = get_stream_properties(stream)
        yield '{0}\r\n'.format(json.dumps((stream, properties)))
  yield ''


def wsgi_application(environment, start_response):
  path = environment.get('PATH_INFO', '').rstrip('/')
  if path in ENDPOINTS:
    return ENDPOINTS[path](environment, start_response)
  else:
    start_response('404 NOT FOUND', [('Content-Type', 'text/plain')])
    return "Four, oh, four :'(."


class GunicornApplication(Application):
  def __init__(self, options={}):
    # Try creating log directory, if missing.
    log_dir = settings.node['log_directory'].rstrip('/')
    if not os.path.exists(log_dir):
      os.makedirs(log_dir)

    # Default options
    self.options = {'worker_class': 'gevent',
                    'accesslog': '{0}/{1}'.format(log_dir, 'access.log'),
                    'errorlog': '{0}/{1}'.format(log_dir, 'error.log'),
                    'log_level': 'info',
                    'name': 'kronosd'}

    # Apply user specified options
    self.options.update(options)

    super(GunicornApplication, self).__init__()

  def init(self, *args):
    config = {}
    for key, value in self.options.iteritems():
      if key in self.cfg.settings and value is not None:
        config[key] = value
    return config
  
  def load(self):
    return wsgi_application
