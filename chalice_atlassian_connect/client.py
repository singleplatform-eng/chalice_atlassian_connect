"""Contains a default Client object if nothing else is provided"""
import boto3


class AtlassianConnectClient(object):
    """
    Reference implementation of Client object

    :ivar clientKey: Confluence/Jira/Etc Unique Identifier
    :ivar sharedSecret: Shared secret between instance and addon
    :ivar baseUrl: Url for Confluence/Jira/Etc
    """
    _clients = {}

    def __init__(self, **kwargs):
        super(AtlassianConnectClient, self).__init__()
        self.clientKey = None
        self.sharedSecret = None
        self.baseUrl = None
        for k, v in list(kwargs.items()):
            setattr(self, k, v)

    @staticmethod
    def delete(client_key):
        """
        Removes a client from the database

        :param client_key:
            jira/confluence clientKey to load from db
        :type app: string"""
        del AtlassianConnectClient._clients[client_key]

    @staticmethod
    def all():
        """
        Returns a list of all clients stored in the database

        :returns: list of all clients
        :rtype: list"""
        return AtlassianConnectClient._clients

    @staticmethod
    def load(client_key):
        """
        Loads a Client from the (internal) database

        :param client_key:
            jira/confluence clientKey to load from db
        :type app: string
        :rtype: Client or None"""
        return AtlassianConnectClient._clients.get(client_key)

    @staticmethod
    def save(client):
        """
        Save a client to the database

        :param client:
            Client object (Default Class or overriden class) to save
        :type app: Client"""
        AtlassianConnectClient._clients[client.clientKey] = client


class DynamoDBAtlassianConnectClient(AtlassianConnectClient):
    _table = boto3.resource('dynamodb').Table('SP-Atlassian-Plugin-DB-ClientsTable-8WIBWGIOC8GR')

    def __init__(self, **kwargs):
        super(DynamoDBAtlassianConnectClient, self).__init__()
    #     self.clientKey = None
    #     self.sharedSecret = None
    #     self.baseUrl = None
    #     for k, v in list(kwargs.items()):
    #         setattr(self, k, v)

    @staticmethod
    def delete(client_key):
        DynamoDBAtlassianConnectClient._table.delete_item(Key={'clientKey': client_key})

    @staticmethod
    def all():
        response = DynamoDBAtlassianConnectClient._table.scan()
        return response['Items']

    @staticmethod
    def load(client_key):
        response = DynamoDBAtlassianConnectClient._table.get_item(Key={'clientKey': client_key})
        return response.get('Items')
        if response:
            response.clientKey = response['clientKey']
            response.sharedSecret = response['sharedSecret']
            response.baseUrl = response['baseUrl']
        return response

    @staticmethod
    def save(client):
        DynamoDBAtlassianConnectClient._table.put_item(
            Item={
                'clientKey': client.clientKey,
                'sharedSecret': client.sharedSecret,
                'baseUrl': client.baseUrl,
            }
        )
