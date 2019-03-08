import re
from functools import wraps

from atlassian_jwt import Authenticator, encode_token
from chalice import (
    ChaliceViewError,
    NotFoundError,
    Response,
    UnauthorizedError,
)
from jwt import decode
from jwt.exceptions import DecodeError
from requests import get
from .client import AtlassianConnectClient

try:
    # python2
    from urllib import urlencode
except ImportError:
    # python3
    from urllib.parse import urlencode


class _SimpleAuthenticator(Authenticator):
    """Implementation of Authenticator for Atlassian"""
    def __init__(self, addon, *args, **kwargs):
        super(_SimpleAuthenticator, self).__init__(*args, **kwargs)
        self.addon = addon

    def get_shared_secret(self, client_key):
        """ I actually don't fully understand this. Go see atlassian_jwt """
        client = self.addon.client_class.load(client_key)
        if client is None:
            raise Exception('No client for ' + client_key)
        if isinstance(client, dict):
            return client.get('sharedSecret')
        return client.sharedSecret


class AtlassianConnect(object):
    """This class is used to make creating an Atlassian Connect based
    addon a lot simplier and more straight forward. It takes care of all
    the authentication and authorization for you.

    You will need to provide a Client class that
    contains load(id) and save(client) methods.
    """
    def __init__(self, app=None, client_class=AtlassianConnectClient):
        self.app = app
        self.app.url_for = self._url_for

        self.descriptor = {
            "authentication": {"type": "none"},
            "apiMigrations": {"gdpr": True},
            "lifecycle": {},
            "links": {
            },
        }
        if app is not None:
            self.init_app(app)
        self.client_class = client_class()
        self.auth = _SimpleAuthenticator(addon=self)
        self.sections = {}

    def init_app(self, app):
        """
        Initialize Application object stuff

        :param app:
            App Object
        :type app: :py:class:`chalice.Chalice`
        """
        if self.app is not None:
            self.app = app

        app.route('/atlassian-connect.json',
                  methods=['GET'])(self._get_descriptor)
        app.route('/{section}/{name}',
                  methods=['GET', 'POST'])(self._handler_router)
        app.context_processor = self._atlassian_jwt_post_token

        app_descriptor = {
            "name": app.config.get('ADDON_NAME', ""),
            "description": app.config.get('ADDON_DESCRIPTION', ""),
            "key": app.config.get('ADDON_KEY'),

            "scopes": app.config.get('ADDON_SCOPES', ["READ"]),
            "vendor": {
                "name": app.config.get('ADDON_VENDOR_NAME'),
                "url": app.config.get('ADDON_VENDOR_URL')
            },
        }
        self.descriptor.update(app_descriptor)

    def _url_for(self, endpoint, **values):
        reqctx = self.app.current_request

        external = values.pop('_external', False)
        method = values.pop('_method', None)
        scheme = values.pop('_scheme', None)
        rv = None
        for k, v in self.app.routes.items():
            if method is not None:
                x = v.get(method)
                if x and x.view_name == endpoint:
                    rv = k
            else:
                for x in v.values():
                    if x.view_name == endpoint:
                        rv = k

        if rv is None:
            return ChaliceViewError("url not found for '%s'" % endpoint)

        if external:
            if reqctx is None:
                return rv
            if scheme is None:
                scheme = reqctx.headers.get('x-forwarded-proto', 'http')
            rv = "%s%s" % (reqctx.headers['host'], rv)
        if scheme is not None:
            if not external:
                raise ChaliceViewError("When specifying _scheme, _external must be True")  # NOQA
            rv = "%s://%s" % (scheme, rv)

        return rv

    def _atlassian_jwt_post_token(self):
        if not getattr(self.app.current_request, 'ac_client', None):
            return dict()

        _args = {}
        if self.app.current_request.query_params:
            _args = self.app.current_request.query_params.copy()
        try:
            del _args['jwt']
        except KeyError:
            pass

        signature = encode_token(
            'POST',
            self.app.current_request.context['path'] + '?' + urlencode(_args),
            self.app.current_request.ac_client.clientKey,
            self.app.current_request.ac_client.sharedSecret
        )
        _args['jwt'] = signature
        return dict(atlassian_jwt_post_url=self.app.current_request.context.path + '?' + urlencode(_args))

    def _get_descriptor(self):
        """Output atlassian connector descriptor file"""
        descriptor_external_link = self.app.url_for('_get_descriptor', _external=True)
        descriptor_internal_link = self.app.url_for('_get_descriptor', _external=False)
        self.descriptor["baseUrl"] = descriptor_external_link.replace(
            descriptor_internal_link, '')
        self.descriptor["links"]["self"] = descriptor_external_link
        return self.descriptor

    def _handler_router(self, section, name):
        """
        Main Router for Atlassian Connect plugin

        TODO: Rest of params
        """
        method = self.sections.get(section, {}).get(name)
        if method is None:
            self.app.log.error(
                'Invalid handler for %s -- %s' % (section, name))
            print((section, name, self.sections))
            raise NotFoundError
        ret = method()
        if ret is not None:
            return ret
        return Response(status_code=204, body={})

    @staticmethod
    def _make_path(section, name):
        return "/".join(['', section, name])

    def _provide_client_handler(self, section, name, kwargs_updator=None):
        def _wrapper(func):
            @wraps(func)
            def _handler(**kwargs):
                try:
                    client_key = self.auth.authenticate(
                        self.app.current_request.method,
                        self.app.current_request.context['path'],
                        self.app.current_request.headers)
                    client = self.client_class.load(client_key)
                    if not client:
                        raise UnauthorizedError
                    self.app.current_request.ac_client = client
                    kwargs['client'] = client
                    if kwargs_updator:
                        kwargs.update(kwargs_updator(**kwargs))
                except DecodeError:
                    pass

                ret = func(**kwargs)
                if ret is not None:
                    return ret
                return Response(status_code=204, body={})
            self._add_handler(section, name, _handler)
            return func
        return _wrapper

    def _add_handler(self, section, name, handler):
        self.sections.setdefault(section, {})[name] = handler

    def lifecycle(self, name):
        """
        Lifecycle decorator. See `external lifecycle`_ documentation

        Example::

            @ac.lifecycle("installed")
            def lifecycle_installed(client):
                print "New client installed!!!!"
                print client

        Payload::

            {
                "key": "installed-addon-key",
                "clientKey": "unique-client-identifier",
                "sharedSecret": "a-secret-key-not-to-be-lost",
                "serverVersion": "server-version",
                "pluginsVersion": "version-of-connect",
                "baseUrl": "http://example.atlassian.net",
                "productType": "jira",
                "description": "Atlassian JIRA at https://example.atlassian.net",
                "serviceEntitlementNumber": "SEN-number",
                "eventType": "installed"
            }

        :param name:
            Which atlassian connect lifecycle to handle.

            At time of writing, the following are the only options:
                * installed
                * uninstalled
                * enabled
                * disabled

            Each of the above will call your Client's save and load methods
        :type name: string

        .. _external lifecycle: https://developer.atlassian.com/static/connect/docs/beta/modules/lifecycle.html
        """
        section = "lifecycle"

        self.descriptor['authentication'] = {'type': 'jwt'}
        self.descriptor.setdefault(
            section, {}
        )[name] = AtlassianConnect._make_path(section, name)

        def _decorator(func):
            if name == "installed":
                self._add_handler(section, name,
                                  self._installed_wrapper(func))
            else:
                self._add_handler(section, name, func)
            return func
        return _decorator

    def _installed_wrapper(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            json_body = self.app.current_request.json_body
            if json_body is None:
                raise Exception("Invalid Credentials")
            client = self.client_class
            client.__init__(**json_body)
            response = get(
                client.baseUrl.rstrip('/') +
                '/plugins/servlet/oauth/consumer-info')
            response.raise_for_status()

            key = re.search(r"<key>(.*)</key>", response.text).groups()[0]
            public_key = re.search(
                r"<publicKey>(.*)</publicKey>", response.text
            ).groups()[0]

            if key != client.clientKey or public_key != client.publicKey:
                raise Exception("Invalid Credentials")

            stored_client = self.client_class.load(client.clientKey)
            if stored_client:
                token = self.app.current_request.headers.get('authorization', '').lstrip('JWT ')
                if not token:
                    # Is not first install, but did not sign the request
                    # properly for an update
                    raise UnauthorizedError
                try:
                    decode(
                        token,
                        stored_client.sharedSecret,
                        options={"verify_aud": False})
                except (ValueError, DecodeError):
                    # Invalid secret, so things did not get installed
                    raise UnauthorizedError

            self.client_class.save(client)
            kwargs['client'] = client
            return func(*args, **kwargs)
        return inner

    def webhook(self, event, exclude_body=False, **kwargs):
        """
        Webhook decorator. See `external webhooks`_ documentation

        Example::

            @ac.webhook("jira:issue_created")
            def jira_issue_created(client, event):
                print "An issue was just created!"
                print "Take a look at this:"
                print event

        :param event:
            Specifies the named event you would like to listen to
            (e.g., "enabled", "jira:issue_created", etc.)
        :type event: string

        :param exclude_body:
            Specifies if webhook will send JSON body when triggered.
            By default, a webhook will send a request with a JSON body.
        :type event: bool

        :param filter:
            Filter for entities that the webhook will be triggered for.
            Refer to the documentation on filtering_ for details.
        :type event: string

        :param propertyKeys:
            Specifies entity properties which will be returned inside JSON body.
            If not specified no properties will be returned.
        :type event: array

        .. _filtering: https://developer.atlassian.com/cloud/confluence/modules/webhook/#Filtering
        .. _external webhooks: https://developer.atlassian.com/jiradev/jira-apis/webhooks
        """
        section = 'webhooks'

        webhook = {
            "event": event,
            "url": AtlassianConnect._make_path(section, event.replace(":", "")),
            "excludeBody": exclude_body
        }
        if kwargs.get('filter'):
            webhook["filter"] = kwargs.pop('filter')
        if kwargs.get('propertyKeys'):
            webhook["propertyKeys"] = kwargs.pop('propertyKeys')

        self.descriptor.setdefault(
            'modules', {}
        ).setdefault(
            section, []
        ).append(webhook)

        def _wrapper(**kwargs):
            del kwargs
            content = self.app.current_request.json_body()
            return {"event": content}

        return self._provide_client_handler(
            section, event.replace(":", ""), kwargs_updator=_wrapper)

    def module(self, key, name=None, location=None):
        """
        Module decorator. See `external modules`_ documentation

        Example::

            @ac.module("configurePage", name="Configure")
            def configure_page(client):
                return '<h1>Configure Page</h1>', 200

        :param key:
            A key to identify this module.

            This key must be unique relative to the add on, with the exception
            of Confluence macros: Their keys need to be globally unique.

            Keys must only contain alphanumeric characters and dashes.
        :type event: string

        :param location:
            The location in the application interface where the web section
            should appear.
            For the Atlassian application interface, a location is something
            like the coordinates on a map.
            It points to a particular drop-down menu or navigation list in
            the UI.
        :type event: string

        :param name:
            A human readable name.
        :type event: string

        .. _external modules: https://developer.atlassian.com/static/connect/docs/beta/modules/common/web-section.html
        """
        name = name or key
        location = location or key
        section = 'modules'

        self.descriptor.setdefault(
            section, {}
        )[location] = {
            "url": AtlassianConnect._make_path(section, key),
            "name": {"value": name},
            "key": key
        }

        return self._provide_client_handler(section, key)

    def confluence_blueprint(self, key, description, name=None, **kwargs):
        """
        Blueprint decorator. See `external blueprint`_ documentation

        Example::

            @ac.confluence_blueprint(key="remote-blueprint",
                name="Simple Remote Blueprint",
                template=[{
                    "condition": "project_type",
                    "params": {"projectTypeKey": "service_desk"}
                }])
            def employee_information_panel(client):
                return 'this is issue %s' % request.args.get('issueKey')

        :param key:
            A key to identify this module.

            This key must be unique relative to the add on, with the exception
            of Confluence macros: Their keys need to be globally unique.

            Keys must only contain alphanumeric characters and dashes.
        :type event: string

        :param template:
            Defines where the blueprint template is located.
        :type event: Blueprint Template

        :param name:
            A human readable name.
        :type event: string

        Anything else from the `external blueprint`_ docs should also work

        .. _external webpanel: https://developer.atlassian.com/cloud/confluence/modules/blueprint/
        """
        name = name or key.replace('-', ' ').title()
        section = 'blueprints'

        if not re.search(r"^[a-zA-Z0-9-]+$", key):
            raise Exception("Blueprint(%s) must match ^[a-zA-Z0-9-]+$" % key)

        blueprint = {
            "key": key,
            "name": {"value": name},
            "template": {
                "url": AtlassianConnect._make_path(section, key),
            },
            "description": {"value": description},
        }
        if kwargs.get('createResult'):
            createResult = kwargs.pop('createResult')
            if not re.search(r"^(edit|EDIT|view|VIEW)$", createResult):
                raise Exception("Blueprint createResult value must be edit|EDIT|view|VIEW")
            blueprint['createResult'] = createResult
        if kwargs.get('icon'):
            blueprint['icon'] = {'url': '/images/' + kwargs.pop('icon'), 'width': 48, 'height': 48}
        if kwargs.get('conditions'):
            blueprint['conditions'] = kwargs.pop('conditions')

        self.descriptor.setdefault(
            'modules', {}
        ).setdefault(
            section, []
        ).append(blueprint)
        return self._provide_client_handler(section, key)

    def confluence_blueprint_context(self, key, **kwargs):
        """
        Blueprint template context decorator. See `external blueprint template context`_ documentation

        Example::

            @ac.confluence_blueprint_context(key="remote-blueprint",
            def blueprint_context():
                ctx = [{
                    'identifier': 'ContentPageTitle',
                    'value': 'page title',
                    'representation': 'plain'
                }]
                return Response(body=ctx)

        :param key:
            A key to identify this blueprint context.

            This key must be identical to a defined confluence_blueprint key
        :type event: string

        Anything else from the `external blueprint`_ docs should also work

        .. _external webpanel: https://developer.atlassian.com/cloud/confluence/modules/blueprint-template-context/
        """
        section = 'blueprint_contexts'

        registered_blueprints = self.descriptor['modules']['blueprints']
        my_blueprint = list(filter(lambda x: x['key'] == key, registered_blueprints))
        if my_blueprint is None:
            raise Exception("Blueprint template context(%s) must correspond to defined confluence_blueprint" % key)
        other_blueprints = list(filter(lambda x: x['key'] != key, registered_blueprints))

        blueprint_context = {
            "blueprintContext": {
                "url": AtlassianConnect._make_path(section, key)
            }
        }

        my_blueprint[0]['template'].update(blueprint_context)
        registered_blueprints = my_blueprint + other_blueprints
        self.descriptor['modules']['blueprints'] = registered_blueprints
        return self._provide_client_handler(section, key)

    def webpanel(self, key, name=None, location=None, **kwargs):
        """
        Webpanel decorator. See `external webpanel`_ documentation

        Example::

            @ac.webpanel(key="userPanel",
                name="Employee Information",
                location="atl.jira.view.issue.right.context",
                conditions=[{
                    "condition": "project_type",
                    "params": {"projectTypeKey": "service_desk"}
                }])
            def employee_information_panel(client):
                return 'this is issue %s' % request.args.get('issueKey')

        :param key:
            A key to identify this module.

            This key must be unique relative to the add on, with the exception
            of Confluence macros: Their keys need to be globally unique.

            Keys must only contain alphanumeric characters and dashes.
        :type event: string

        :param location:
            The location in the application interface where the web section
            should appear.
            For the Atlassian application interface, a location is something
            like the coordinates on a map.
            It points to a particular drop-down menu or navigation list in
            the UI.
        :type event: string

        :param name:
            A human readable name.
        :type event: string

        Anything else from the `external webpanel`_ docs should also work

        .. _external webpanel: https://developer.atlassian.com/static/connect/docs/beta/modules/common/web-panel.html
        """
        name = name or key
        location = location or key
        section = 'webPanels'

        if not re.search(r"^[a-zA-Z0-9-]+$", key):
            raise Exception("Webpanel(%s) must match ^[a-zA-Z0-9-]+$" % key)

        webpanel_capability = {
            "key": key,
            "name": {"value": name},
            "url": AtlassianConnect._make_path(section.lower(), key) + '?issueKey={issue.key}',
            "location": location
        }
        if kwargs.get('conditions'):
            webpanel_capability['conditions'] = kwargs.pop('conditions')

        self.descriptor.setdefault(
            'modules', {}
        ).setdefault(
            section, []
        ).append(webpanel_capability)
        return self._provide_client_handler(section, key)

    def tasks(self):
        """Function that turns a collection of tasks
        suitable for pyinvoke_

        Example::

            from app.web import ac
            ns = Collection()
            ns.add_collection(ac.tasks())

        .. _pyinvoke: http://www.pyinvoke.org/
        """
        from invoke import task, Collection

        @task
        def list(ctx):
            """Show all clients in the database"""
            from json import dumps
            with self.app.app_context():
                print(dumps([
                    dict(c) for c in self.client_class.all()
                ]))

        @task
        def show(ctx, clientKey):
            """Lookup one client from the database"""
            from json import dumps
            with self.app.app_context():
                print(dumps(dict(self.client_class.load(clientKey))))

        @task
        def install(ctx, data):
            """Add a given client from the database"""
            from json import loads
            with self.app.app_context():
                client = loads(data)
                self.client_class.save(client)
                print("Added")

        @task()
        def uninstall(ctx, clientKey):
            """Remove a given client from the database"""
            with self.app.app_context():
                self.client_class.delete(clientKey)
                print("Deleted")

        ns = Collection('clients')
        ns.add_task(list)
        ns.add_task(show)
        ns.add_task(install)
        ns.add_task(uninstall)
        return ns
