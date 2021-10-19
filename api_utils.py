import collections 
import platform
if platform.system() == "Windows":
    crypt = None
else:
    import crypt
import datetime
import functools
import inspect
import itertools
import json
import queue
import sys
import threading
import traceback

try:
    import werkzeug
except ImportError:
    from os import system
    system("pip install werkzeug")
    import werkzeug

import werkzeug.routing
from werkzeug.exceptions import (
    HTTPException,
    NotFound,
    Unauthorized,
    UnprocessableEntity,
    UnsupportedMediaType,
)
from werkzeug.middleware.dispatcher import DispatcherMiddleware


try:
    import jwt
except ImportError:
    # Do not complain now, but only when auth classes get instantiated
    jwt = None


class API:
    """JSON API.

    >>> app = API()
    >>> @app.GET("/")
    ... def root(request):
    ...     return "Hello World"
    ...
    >>> from werkzeug.test import Client
    >>> client = Client(app)
    >>> body, code, *_ = client.get('/')
    >>> json.loads(b''.join(body))
    'Hello World'

    Now with generic POST data: add a data parameter and optionally specify it's
    type (default is dict)
    >>> @app.POST("/")
    ... def create(request, data:list):
    ...     print(data)
    ...
    >>> body, code, *_ = client.post("/", json=[1, 2, 3])
    [1, 2, 3]

    >>> body, code, *_ = client.post("/", json={})
    >>> code
    '422 UNPROCESSABLE ENTITY'

    And finally requesting a dict in the POST data with specified fields (and types)

    >>> @app.PUT("/")
    ... def update(request, name, age:int, superhuman:bool=False):
    ...     print(f"{name} is {age} years old.")
    ...     print(f"{name} is {'' if superhuman else 'not '}superhuman.")
    ...
    >>> import json
    >>> data = {"name": "Betsy", "age": 34}
    >>> body, code, *_ = client.put("/", json=data)
    Betsy is 34 years old.
    Betsy is not superhuman.
    >>> code
    '200 OK'

    >>> data = {"name": "Betsy"}
    >>> body, code, *_ = client.put("/", json=data)
    >>> code
    '422 UNPROCESSABLE ENTITY'

    >>> data = {"name": "Betsy", "age": "34"}
    >>> body, code, *_ = client.put("/", json=data)
    >>> code
    '422 UNPROCESSABLE ENTITY'

    >>> data = {"name": "Betsy", "age": 34, "superhuman": True}
    >>> body, code, *_ = client.put("/", json=data)
    Betsy is 34 years old.
    Betsy is superhuman.
    >>> code
    '200 OK'

    >>> data = {"name": "Betsy", "age": 34, "verysmart": True}
    >>> body, code, *_ = client.put("/", json=data)
    >>> code
    '422 UNPROCESSABLE ENTITY'

    >>> data = "This is not valid JSON"
    >>> body, code, *_ = client.put("/", data=data)
    >>> code
    '415 UNSUPPORTED MEDIA TYPE'
    """

    def __init__(self):
        self._url_map = werkzeug.routing.Map()

    def route(self, string, methods=("GET",), func=None):
        """Register a route with a callback.

        This function can be used either directly:

        >>> api = API()
        >>> api.route("/", func=lambda request: "Hello!")  # doctest: +ELLIPSIS
        <function <lambda> at 0x...>

        or as a decorator
        >>> @api.route("/user/<id>")
        ... def home(request, id):
        ...     return f"Welcome home {id}!"
        ...

        To test it use the Client class.
        >>> from werkzeug.test import Client
        >>> client = Client(api)
        >>> client.get("/")       # doctest: +ELLIPSIS
        (<werkzeug.wsgi.ClosingIterator ...>, '200 OK', Headers(...))
        >>> json.loads(b"".join(_[0]))
        'Hello!'
        >>> client.get("/user/007")       # doctest: +ELLIPSIS
        (<werkzeug.wsgi.ClosingIterator ...>, '200 OK', Headers(...))
        >>> json.loads(b"".join(_[0]))
        'Welcome home 007!'
        """
        if func is None:
            return functools.partial(self.route, string, methods)

        rule = werkzeug.routing.Rule(string, methods=methods)
        werkzeug.routing.Map([rule])  # Bind rule temporarily
        url_params = rule.arguments

        sig = inspect.signature(func)
        params = sig.parameters
        param_keys = list(sig.parameters.keys())

        # The first argument is the request, after that, the route parameters follow
        # The order of the parameters is ignored
        func_url_params = set(param_keys[1 : len(url_params) + 1])
        missmatch = url_params ^ func_url_params
        if missmatch:
            raise TypeError(
                f"{func.__name__}() arguments and route parameter missmatch "
                f"({func_url_params} != {url_params})"
            )

        body_params = param_keys[len(url_params) + 1 :]
        body_type = None
        if len(body_params) == 1 and body_params[0] == "data":
            body_type = (
                params["data"].annotation
                if params["data"].annotation is not inspect.Parameter.empty
                else dict
            )
            content_types = {}
        elif body_params:
            body_type = dict
            content_types = {
                key: params[key].annotation
                for key in body_params
                if params[key].annotation is not inspect.Parameter.empty
            }

        if body_type:
            func = _parse_json_body(func, body_type, content_types)

        self._url_map.add(werkzeug.routing.Rule(string, methods=methods, endpoint=func))
        return func

    def GET(self, string):
        """Shorthand for registering GET requests.

        Use as a decorator:
        >>> api = API()
        >>> @api.GET("/admin")
        ... def admin_home(request):
        ...     return "Nothing here"
        ...
        >>> from werkzeug.test import Client
        >>> client = Client(api)
        >>> client.get("/admin")   # doctest: +ELLIPSIS
        (<werkzeug.wsgi.ClosingIterator ...>, '200 OK', Headers(...))
        """
        return self.route(string, ("GET",))

    def POST(self, string):
        """Shorthand for registering POST requests."""
        return self.route(string, ("POST",))

    def PUT(self, string):
        """Shorthand for registering PUT requests."""
        return self.route(string, ("PUT",))

    def PATCH(self, string):
        """Shorthand for registering PATCH requests."""
        return self.route(string, ("PATCH",))

    def DELETE(self, string):
        """Shorthand for registering DELETE requests."""
        return self.route(string, ("DELETE",))

    def __call__(self, environ, start_response):
        try:
            request = werkzeug.Request(environ)
            adapter = self._url_map.bind_to_environ(environ)
            endpoint, values = adapter.match()

            # Dispatch request
            response = endpoint(request, **values)
            if not callable(response):
                response = _json_response(response)
            return response(environ, start_response)
        except HTTPException as e:
            response = _json_response(
                {"code": e.code, "name": e.name, "description": e.description},
                status=e.code,
            )
        except Exception as e:
            response = _json_response(
                {"code": 500, "name": "Internal Server Error"}, status=500
            )
            err = environ["wsgi.errors"]
            print(f"ERROR {e.__class__.__name__}: {str(e)}", file=err)
            traceback.print_exc(file=err)
        return response(environ, start_response)


def _json_response(data, status=200):
    if data is None:
        return werkzeug.Response(status=status)
    else:
        data = json.dumps(data, indent=2, default=str) + "\n"
        return werkzeug.Response(data, status=status, mimetype="text/json")


def _check_value(key, value, value_type):
    if value_type is bool and (value is True or value is False):
        return value
    elif value_type == float and isinstance(value, int):
        return float(value)
    if isinstance(value_type, type) and isinstance(value, value_type):
        return value
    elif (
        isinstance(value, str)
        and callable(value_type)
        and value_type not in (bool, int, float, str, list, dict)
    ):
        func = value_type
        try:
            return func(value)
        except ValueError:
            raise UnprocessableEntity(
                f"Invalid format: '{key}' cannot be converted to {func.__name__}."
            )
    else:
        raise UnprocessableEntity(
            f"Invalid format: '{key}' must be of type {value_type.__name__}."
        )


def _parse_json_body(func=None, body_type=dict, content_types={}):  # noqa: C901
    if func is None:
        return functools.partial(
            _parse_json_body, body_type=body_type, content_types=content_types
        )

    sig = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            data = str(request.data, "utf-8").strip()
        except UnicodeDecodeError:
            raise UnsupportedMediaType("Cannot parse request body: invalid UTF-8 data")

        if not data:
            raise UnsupportedMediaType("Cannot parse request body: no data supplied")

        try:
            data = json.loads(data)
        except json.decoder.JSONDecodeError:
            raise UnsupportedMediaType("Cannot parse request body: invalid JSON")

        if not isinstance(data, body_type):
            raise UnprocessableEntity(
                f"Invalid data format: {body_type.__name__} expected"
            )

        if body_type == dict and content_types:
            too_many = data.keys() - sig.parameters.keys()
            if too_many:
                raise UnprocessableEntity(f"Key not allowed: {', '.join(too_many)}")

            kwargs.update(data)
            bound = sig.bind_partial(request, *args, **kwargs)

            for key, value in bound.arguments.items():
                if key in content_types:
                    bound.arguments[key] = _check_value(key, value, content_types[key])

            bound.apply_defaults()

            missing = sig.parameters.keys() - bound.arguments.keys()
            if missing:
                raise UnprocessableEntity(f"Key missing: {', '.join(missing)}")

        else:
            kwargs["data"] = data

        return func(request, *args, **kwargs)

    return wrapper


def timestamp(string=None):
    """Parse JS date strings to datetime objects.

    Returns the current datetime (now), if called with no argument.

    `timestamp` returns UCT timestamps.

    Example usage:

    To convert a JS timestamp, create one in the browser or in node:
    > let now = new Date()
    > JSON.stringify(now)
    '"2020-12-09T23:44:53.782Z"'

    Convert the value to a native Python datetime object:
    >>> timestamp(json.loads('"2020-12-09T23:44:53.782Z"'))
    datetime.datetime(2020, 12, 9, 23, 44, 53, 782000, tzinfo=datetime.timezone.utc)

    To get the current time:
    >>> timestamp()                                         # doctest: +ELLIPSIS
    datetime.datetime(2..., tzinfo=datetime.timezone.utc)

    This function can be used as an annotation in request handlers:
    >>> api = API()
    >>> @api.POST("/reminder")
    ... def reminder(request, date:timestamp, text:str):
    ...     pass
    ...
    """
    if string:
        return datetime.datetime.fromisoformat(string.replace("Z", "+00:00"))
    else:
        return datetime.datetime.now().astimezone(datetime.timezone.utc)


class BaseJWTAuthMiddleware:
    """Middleware authorizing access to chained application using JWT.

    Attention: Authentication must be provided.

    This middleware exposes two endpoints:
     - /auth/login/ for generation new tokens.
     - /auth/renew/ for renewing an existing token

    Tokens are short-lived and are valid for only 15 minutes, but expired tokens
    can be renewed during one week starting from their initial issueing date.

    Upon successful authentication the username is stored in the WSGI environment,
    and can be retrieved from Werkzeug's Request object: `request.remote_user`
    """

    def __init__(
        self,
        app,
        secret,
        *,
        exempt=[],
        prefix="/auth",
        login_methods=("POST",),
    ):
        if jwt is None:
            print("WARNING: No module named 'jwt'", file=sys.stderr)
            print("Cannot perform authentication without PyJWT", file=sys.stderr)
            print("Run `pip install PyJWT` to fix this", file=sys.stderr)
            raise ModuleNotFoundError("No module named 'jwt'")

        auth_api = API()
        auth_api.route(
            "/login", methods=login_methods, func=functools.partial(self._login)
        )
        auth_api.route("/renew", methods=("POST",), func=functools.partial(self._renew))

        self.app = DispatcherMiddleware(app, {prefix: auth_api})

        prefix = prefix.lower().rstrip("/")
        self.exempt = (
            [(method.upper(), path.lower().rstrip("/")) for method, path, *_ in exempt]
            + [(method.upper(), prefix + "/login") for method in login_methods]
            + [("POST", prefix + "/renew")]
        )

        self.secret = secret

    def __call__(self, environ, start_response):
        try:
            request_line = (
                environ["REQUEST_METHOD"].upper(),
                environ["PATH_INFO"].lower().rstrip("/"),
            )
            if request_line not in self.exempt:
                # Check authorization (throws an exception if it fails)
                username = self._check_authorization(environ)
                assert isinstance(username, str)
                assert username != ""
                del environ["HTTP_AUTHORIZATION"]
                environ["REMOTE_USER"] = username
            return self.app(environ, start_response)
        except HTTPException as e:
            response = _json_response(
                {"code": e.code, "name": e.name, "description": e.description},
                status=e.code,
            )
        except Exception as e:
            response = _json_response(
                {"code": 500, "name": "Internal Server Error"}, status=500
            )
            err = environ["wsgi.errors"]
            print(f"ERROR {e.__class__.__name__}: {str(e)}", file=err)
            traceback.print_exc(file=err)

        return response(environ, start_response)

    def _check_authorization(self, environ):
        """Verify request authorization header.

        Returns username if authorization passed.

        Raises a 401 Unauthorized exception if authorization failed.
        """
        if "HTTP_AUTHORIZATION" not in environ:
            raise Unauthorized("No authorization header supplied")

        auth = environ["HTTP_AUTHORIZATION"]

        if not auth.startswith("Bearer "):
            raise Unauthorized("Invalid authorization header")

        token = auth[len("Bearer ") :]
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                options={"require_exp": True, "require_iat": True},
            )
        except jwt.ExpiredSignatureError:
            raise Unauthorized("Expired token")
        except jwt.InvalidTokenError:
            raise Unauthorized("Invalid token")
        return claims["username"]

    def _login(self, request):
        username = self.authenticate(request)
        if username is None:
            raise Unauthorized("User authentication failed")
        now = datetime.datetime.utcnow()
        claims = {
            "username": username,
            "iat": now,
            "exp": now + datetime.timedelta(minutes=15),
        }
        token = jwt.encode(claims, self.secret, algorithm="HS256")

        return {"token": token}

    def _renew(self, request, token: str):
        now = datetime.datetime.utcnow()
        try:
            # Valid tokens can always be renewed withing their short lifetime,
            # independent of the issuing date
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                options={"require_exp": True, "require_iat": True},
            )
        except jwt.ExpiredSignatureError:
            # Expired tokens can be renewed for at most one week after the
            # first issuing date
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                options={
                    "require_exp": True,
                    "require_iat": True,
                    "verify_exp": False,
                },
            )
            issued_at = datetime.datetime.utcfromtimestamp(claims["iat"])
            if issued_at + datetime.timedelta(days=7) < now:
                raise Unauthorized("Unrenewable expired token")
        except jwt.InvalidTokenError:
            raise Unauthorized("Invalid token")

        claims["exp"] = now + datetime.timedelta(minutes=15)

        token = jwt.encode(claims, self.secret, algorithm="HS256")

        return {"token": token}

    def authenticate(self, request):
        """Authenticate user.

        Returns a user identification string (usually the username) if
        authentication passed, None otherwise.  This method must be
        overwritten in an implementing subclass.
        """
        raise NotImplementedError()


class ExternalAuth(BaseJWTAuthMiddleware):
    """Rely on external authentication.

    The username of an authenticated user must be passed with the
    `REMOTE_USER` key in the wsgi environment.
    """
    def __init__(self, *args, login_methods=("GET", "POST"), **kwargs):
        super().__init__(*args, login_methods=login_methods, **kwargs)

    def authenticate(self, request):
        return request.remote_user


class DummyAuth(BaseJWTAuthMiddleware):
    """Dummy authenticator for testing and development.

    Login always passes and always returns "dummyuser" as username.

    Here is an example session:

    Create an API:
    >>> api = API()
    >>> @api.GET("/")
    ... def root(request):
    ...     return "Hello World"
    ...

    Wrap it with an authentication/authorization layer:
    >>> app = DummyAuth(api, "not a secret")

    >>> from werkzeug.test import Client
    >>> client = Client(app)

    By default, access is denied:
    >>> client.get("/")       # doctest: +ELLIPSIS
    (<werkzeug.wsgi.ClosingIterator ...>, '401 UNAUTHORIZED', Headers(...))

    Login to get a token:
    >>> body, code, *_ = client.post("/auth/login")
    >>> code
    '200 OK'
    >>> token = json.loads(b"".join(body))["token"]
    >>> token                                                      # doctest: +ELLIPSIS
    'eyJ...'

    Use the token to gain access:
    >>> headers = {"Authorization": f"Bearer {token}"}
    >>> client.get("/", headers=headers)                           # doctest: +ELLIPSIS
    (<werkzeug.wsgi.ClosingIterator ...>, '200 OK', Headers(...))
    """

    def authenticate(self, request):
        return "dummyuser"


class UsernamePasswordAuth(BaseJWTAuthMiddleware):
    """Authenticate with a username and password combination.

    `dataset` user tables are supported natively. It must contain an unique
    and identifyable `username` and a `password` column. Alternatively, a
    custom password hash retrieval function may be specified.

    Passwords are expected to be hashed with Python's crypt.crypt function.

    Example usage:

    Let's create a in-memory database with a user table containing one entry:
    >>> import dataset
    >>> db = dataset.connect("sqlite:///:memory:")
    >>> db['user'].insert(dict(username="paul", password=crypt.crypt("john")))
    1

    Assemble a dummy application and client:
    >>> app = UsernamePasswordAuth(API(), "not a secret", user_table=db['user'])
    >>> from werkzeug.test import Client
    >>> client = Client(app)

    Logging in with correct credentials is now possible:
    >>> cred = {"username": "paul", "password": "john"}
    >>> body, code, *_ = client.post("/auth/login", json=cred)
    >>> code
    '200 OK'
    >>> json.loads(b"".join(body))["token"]         # doctest: +ELLIPSIS
    'eyJ...'

    Requests with invalid passwords fail:
    >>> cred = {"username": "paul", "password": "george"}
    >>> body, code, *_ = client.post("/auth/login", json=cred)
    >>> code
    '401 UNAUTHORIZED'

    The same is true for non-existant users:
    >>> cred = {"username": "yoko", "password": "john"}
    >>> body, code, *_ = client.post("/auth/login", json=cred)
    >>> code
    '401 UNAUTHORIZED'
    """

    def __init__(
        self,
        app,
        secret,
        user_table=None,
        find_password=None,
        *,
        exempt=[],
        prefix="/auth",
        login_methods=("POST",),
    ):
        """Initialize the authentication middleware

        The `user_table` argument is expected to be a dataset table containing
        at least a unique identifying `username` and a `password` field.

        Alternatively the `find_password` parameter expects a function taking
        a username as argument, and returning the corresponding password hash.
        The function must return None if the user or password cannot be found.

        If both present, the `user_table` parameter takes precedence over
        `find_password`.
        """
        super().__init__(
            app, secret, exempt=exempt, prefix=prefix, login_methods=login_methods
        )
        if user_table is not None:

            def user_table_find_password(username):
                user = user_table.find_one(username=username)
                if user:
                    return user["password"]

            self.find_password = user_table_find_password
        elif find_password is not None:
            self.find_password = find_password
        else:
            raise ValueError("One of 'user_table' and 'find_password' must be supplied")

    def authenticate(self, request):
        @_parse_json_body(content_types=dict(username=str, password=str))
        def handler(request, username, password):
            pw_hash = self.find_password(username)
            if pw_hash and crypt.crypt(password, pw_hash) == pw_hash:
                return username

        return handler(request)


def run(app, port=3000, hostname="localhost"):
    """Run a wsgi application like an API.

    Optionally specify a listening `port` (default: 3000) and a bind
    `hostname` (default: localhost). Set the hostname to the empty string,
    to listen on all interfaces.
    """
    werkzeug.run_simple(hostname, port, app, threaded=True, use_reloader=True)


Event = collections.namedtuple("Event", ["id", "event_type", "data"])


class PubSub:
    """Class implementing a publish/subscribe event passing scheme.

    Basic example usage:
    >>> chat = PubSub()
    >>> subscription = chat.subscribe()
    >>> chat.publish("message", "Hello")
    >>> next(subscription)
    Event(id=0, event_type='message', data='Hello')

    Messages can be differentiated by topic:
    >>> general_room = chat.subscribe(topic="general")
    >>> nerd_room = chat.subscribe(topic="nerd")
    >>> chat.publish("new_user", "guido", topic="nerd")
    >>> chat.publish("message", "Hi geeks!", topic="nerd")
    >>> chat.publish("message", "It is 12 am", topic="general")
    >>> next(general_room)
    Event(id=3, event_type='message', data='It is 12 am')
    >>> next(nerd_room)
    Event(id=1, event_type='new_user', data='guido')
    >>> next(nerd_room)
    Event(id=2, event_type='message', data='Hi geeks!')
    """

    def __init__(self):
        self._main_lock = threading.Lock()
        self._topic_locks = collections.defaultdict(threading.Lock)
        self._queues = collections.defaultdict(set)
        self._replay_log = collections.defaultdict(
            lambda: collections.deque(maxlen=1_000)
        )
        # FIXME: not secure?
        self._current_id = itertools.count()

    def publish(self, event_type, data, topic=None):
        """Publish an event.

        The event has an `event_type`, usually a string, and a `data` payload.
        `data` can be free-formed, but should be JSON-serializable.

        Optionally a topic can be specified. The message will be only forwarded
        to subscribers interested in the specified topic.
        """
        with self._main_lock:
            id = next(self._current_id)
            queues = self._queues[topic]
            replay_log = self._replay_log[topic]
            topic_lock = self._topic_locks[topic]

        to_remove = []
        event = Event(id, event_type, data)

        with topic_lock:
            replay_log.append(event)

            for q in queues:
                try:
                    q.put_nowait(event)
                except queue.Full:  # Somebody fell asleep?!?
                    to_remove.append(q)

            for q in to_remove:
                try:
                    queues.remove(q)
                except KeyError:
                    pass

    def subscribe(self, topic=None):
        """Subscribe to published events.

        Events are returned as tripples, containing a unique event `id`, the
        `event_type`, and the payload `data`.

        Optionally a specific `topic` can be specified
        """
        q = queue.Queue(100)
        with self._main_lock:
            queues = self._queues[topic]
            topic_lock = self._topic_locks[topic]

        with topic_lock:
            queues.add(q)

        def iterator():
            try:
                while q in queues:
                    try:
                        yield q.get(timeout=60)
                    except queue.Empty:
                        pass
            except GeneratorExit:
                try:
                    with topic_lock:
                        queues.remove(q)
                except KeyError:
                    pass

        return iterator()

    def _event_stream(self, replay_events=(), topic=None):
        subscription = self.subscribe(topic)
        for event in itertools.chain(replay_events, subscription):
            yield (
                f"id: {event.id}\n"
                f"event: {event.event_type}\n"
                f"data: {json.dumps(event.data, default=str)}\n\n"
            ).encode("utf-8")

    def _replay_events(self, last_id, topic=None):
        if last_id is None:
            return ()

        last_id = int(last_id)

        with self._main_lock:
            replay_log = self._replay_log[topic]
            topic_lock = self._topic_locks[topic]

        with topic_lock:
            log_iter = iter(replay_log)
            for event in log_iter:
                if event.id == last_id:
                    break
            else:
                raise ValueError(f"{last_id} is not in event log")
            return list(log_iter)

    def streaming_response(self, request, topic=None):
        """Generate a streaming HTTP responses with server-sent events.

        See https://html.spec.whatwg.org/multipage/server-sent-events.html
        for more information about server-sent events.

        When reconnecting after loosing the connection for a while, browsers
        automatically set the `Last-Event-ID` header field to the value of
        the id of the last received event. The response will first replay
        missed events, before sending newly arriving events. When the event
        specified by `Last-Event-ID` is not found, a 404 Not Found response
        is sent, signalling to the browser, that a clean recovery is not
        possible.

        Here is an example session. First, let us create an API:
        >>> api = API()
        >>> chat = PubSub()
        >>> @api.POST("/")
        ... def post_message(request, message:str):
        ...     chat.publish("message", message)
        ...
        >>> @api.GET("/")
        ... def stream(request):
        ...     return chat.streaming_response(request)
        ...

        We can now post messages and see them appear in our subscription:
        >>> subscription = chat.subscribe()
        >>> from werkzeug.test import Client
        >>> client = Client(api)
        >>> resp = client.post("/", json={"message": "hello"})
        >>> resp = client.post("/", json={"message": "everybody"})
        >>> next(subscription)
        Event(id=0, event_type='message', data='hello')
        >>> next(subscription)
        Event(id=1, event_type='message', data='everybody')

        Now, let's simulate a reconnecting browser that only got the first
        message:
        >>> body, code, *_ = client.get("/", headers={"Last-Event-ID": "0"})
        >>> code
        '200 OK'

        The events are formated according to the specification for server-sent
        events:
        >>> print(str(next(body), encoding="utf-8").strip())
        id: 1
        event: message
        data: "everybody"

        Further incoming messages are sent to the listening client, without
        closing the connection:
        >>> resp = client.post("/", json={"message": "howdoyoudo?"})
        >>> print(str(next(body), encoding="utf-8").strip())
        id: 2
        event: message
        data: "howdoyoudo?"
        """
        last_id = request.headers.get("Last-Event-ID", None)
        try:
            replay_events = self._replay_events(last_id)
        except ValueError:
            raise NotFound()

        return werkzeug.Response(
            self._event_stream(replay_events, topic), mimetype="text/event-stream"
        )


__all__ = (
    "API",
    "NotFound",
    "Unauthorized",
    "UnprocessableEntity",
    "timestamp",
    "ExternalAuth",
    "DummyAuth",
    "run",
    "UsernamePasswordAuth",
    "PubSub",
)
