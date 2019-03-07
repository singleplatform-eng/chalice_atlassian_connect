"""Contains a default Client object if nothing else is provided"""
import boto3


class AtlassianConnectClient(object):
    """
    Reference implementation of Client object

    :ivar clientKey: Confluence/Jira/Etc Unique Identifier
    :ivar sharedSecret: Shared secret between instance and addon
    :ivar baseUrl: Url for Confluence/Jira/Etc
    """
    def __init__(self, state=None, **kwargs):
        if state is None:
            state = {}
        self._state = state
        self.clientKey = None
        self.sharedSecret = None
        self.baseUrl = None
        for k, v in list(kwargs.items()):
            setattr(self, k, v)

    def delete(self, client_key):
        """
        Removes a client from the database

        :param client_key:
            jira/confluence clientKey to load from db
        :type app: string"""
        del self._state[client_key]

    def all(self):
        """
        Returns a list of all clients stored in the database

        :returns: list of all clients
        :rtype: list"""
        return self._state

    def load(self, client_key):
        """
        Loads a Client from the (internal) database

        :param client_key:
            jira/confluence clientKey to load from db
        :type app: string
        :rtype: Client or None"""
        return self._state.get(client_key)

    def save(self, client):
        """
        Save a client to the database

        :param client:
            Client object (Default Class or overriden class) to save
        :type app: Client"""
        self._state[client.clientKey] = client


class DynamoDBAtlassianConnectClient(object):
    def __init__(self, table=None, **kwargs):
        if table is None:
            table = boto3.resource('dynamodb').Table('SP-Atlassian-Plugin-DB-ClientsTable-8WIBWGIOC8GR')
        self._table = table
        self.clientKey = None
        self.sharedSecret = None
        self.baseUrl = None
        for k, v in list(kwargs.items()):
            setattr(self, k, v)

    def delete(self, client_key):
        self._table.delete_item(Key={'clientKey': client_key})

    def all(self):
        response = self._table.scan()
        return response.get('Items')

    def load(self, client_key):
        response = self._table.get_item(Key={'clientKey': client_key}).get('Item')
        if response:
            self.clientKey = response['clientKey']
            self.sharedSecret = response['sharedSecret']
            self.baseUrl = response['baseUrl']
            return self

    def save(self, client):
        self._table.put_item(
            Item={
                'clientKey': client.clientKey,
                'sharedSecret': client.sharedSecret,
                'baseUrl': client.baseUrl,
            }
        )
