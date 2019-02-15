#!/usr/bin/env python
import logging
import re
from _mysql import IntegrityError

from flasgger import Swagger
from flask import Flask, request, jsonify
from flask_cors import CORS

from ensembl_prodinf.utils import app_logging
from ensembl_prodinf.resource_lock import ResourceLocker, LockException

app = Flask(__name__, instance_relative_config=True)
app.config['SWAGGER'] = {
    'title': 'Production resource lock REST endpoints',
    'uiversion': 2,
    'definitions': {
        'ResourceUri': {
            'type': 'string',
            'example': 'ProteinFeaturePipeline'
        },
        'ClientName': {
            'type': 'string',
            'example': 'mysql://server:3306/mydb'
        },
        'Resource': {
            'required': ['resource_id', 'uri'],
            'properties': {
                'resource_id': {
                    'type': 'integer',
                    'example': 88
                },
                'uri': {
                    '$ref': '#/definitions/ResourceUri'
                }
            }
        },
        'Client': {
            'required': ['client_id', 'name'],
            'properties': {
                'client_id': {
                    'type': 'integer',
                    'example': 69
                },
                'name': {
                    '$ref': '#/definitions/ClientName'
                }
            }
        },
        'LockType': {
            'type': 'string',
            'enum': ['read', 'write'],
            'example': 'read'
        },
        'LockRequest': {
            'required': ['resource_uri', 'client_name', 'lock_type'],
            'properties': {
                'resource_uri': {
                    '$ref': '#/definitions/ResourceUri'
                },
                'client_name': {
                    '$ref': '#/definitions/ClientName'
                },
                'lock_type': {
                    '$ref': '#/definitions/LockType'
                }
            }
        },
        'Lock': {
            'required': ['resource_lock_id', 'lock_type', 'created', 'client', 'resource'],
            'properties': {
                'resource_lock_id': {
                    'type': 'integer',
                    'example': 22
                },
                'lock_type': {
                    '$ref': '#/definitions/LockType'
                },
                'created': {
                    'type': 'date',
                    'example': 'Tue, 17 Apr 2018 13:39:57 GMT'
                },
                'client': {
                    '$ref': '#/definitions/Client'
                },
                'resource': {
                    '$ref': '#/definitions/Resource'
                }
            }
        }
    }
}

app.config.from_object('lock_config')
app.config.from_pyfile('lock_config.py', silent=True)
app_logging.add_app_handler(app.logger, __name__)

if app.config.get("LOCK_URI") is None:
    raise ValueError("LOCK_URI not set in configuration")

swagger = Swagger(app)

locker = None


def get_locker():
    """Lazily load the locker object"""
    global locker
    if locker is None:
        locker = ResourceLocker(app.config["LOCK_URI"])
    return locker


def jsonify_obj(obj):
    """Utility to jsonify a SQLalchemy object or list of objects"""
    if type(obj) == list:
        return jsonify([o.to_dict() for o in obj])
    else:
        return jsonify(obj.to_dict())


cors = CORS(app)

# use re to support different charsets
json_pattern = re.compile("application/json")


@app.route('/', methods=['GET'])
def info():
    """
    Get basic information about the REST app
    ---
    tags:
      - info
    operationId: info
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: App details
        schema:
           properties:
               title:
                   type: string
                   example: Production resource lock REST endpoints 
    """
    return jsonify({"title": app.config['SWAGGER']['title']})


@app.route('/ping', methods=['GET'])
def ping():
    """
    Get status of service
    ---
    tags:
     - info
    operationId: ping
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: App details
        schema:
           properties:
               status:
                   type: string
                   example: ok 
    """
    return jsonify({"status": "ok"})


@app.route('/locks', methods=['POST'])
def lock():
    """
    Request a lock on a resource
    ---
    tags:
     - locks
    parameters:
     - in: body
       name: body
       description: Lock request specification
       type: object
       schema:
          $ref: '#/definitions/LockRequest'          
       required: true
    operationId: getLock
    consumes:
     - application/json
    produces:
     - application/json
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
     - description: Project repository
     - url: http://github.com/rochacbruno/flasgger
    responses:
      200:
        description: lock successful
        schema:
          $ref: '#/definitions/Lock'          
      400:
        description: lock specification incorrect
        type: string
        examples:
          - Bad lock request: Unsupported lock_type
      415:
        description: unsupported content type
        type: string
        examples:
          - Could not handle input of type text/plain
      424:
        description: resource already locked
        type: string
        examples:
          - Could not obtain lock: Write lock found on 1 - cannot lock for reading
    """
    if json_pattern.match(request.headers['Content-Type']):
        logging.debug("Requesting lock " + str(request.json))
        try:
            return jsonify_obj(
                get_locker().lock(request.json['client_name'], request.json['resource_uri'], request.json['lock_type']))
        except ValueError as e:
            return "Bad lock request: " + str(e), 400
        except LockException as e:
            return "Could not obtain lock: " + str(e), 415

    else:
        return "Could not handle input of type " + request.headers['Content-Type'], 415


@app.route('/locks/<int:lock_id>', methods=['GET'])
def get_lock(lock_id):
    """
    Retrieve a lock by ID
    ---
    tags:
      - locks
    parameters:
      - name: lock_id
        in: path
        type: integer
        required: true
        default: 1
        description: id of the lock
    operationId: getLock
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: lock returned
        schema:
          $ref: '#/definitions/Lock'
      404:
        description: lock not found
        examples:
          - Lock 69 not found
    """
    try:
        logging.info("Retrieving lock with ID " + str(lock_id))
        lock = get_locker().get_lock(lock_id)
        if lock is None:
            return "Lock " + str(lock_id) + " not found", 404
        else:
            return jsonify_obj(lock)
    except ValueError:
        return "Lock " + str(lock_id) + " not found", 404


@app.route('/locks/<int:lock_id>', methods=['DELETE'])
def unlock(lock_id):
    """
    Remove a specified lock
    ---
    tags:
      - locks
    parameters:
      - name: lock_id
        in: path
        type: integer
        required: true
        default: 1
        description: id of the lock
    operationId: deleteLock
    produces:
      - application/json
    responses:
      200:
        description: lock removed
        schema:
          $ref: '#/definitions/Lock'
      404:
        description: lock not found
        examples:
          - Lock 1 not found
    """
    try:
        get_locker().unlock(lock_id)
        return jsonify({"id": lock_id})
    except ValueError:
        return "Lock " + str(lock_id) + " not found", 404


@app.route('/locks', methods=['GET'])
def get_locks():
    """
    Return active locks matching requirements
    ---
    tags:
      - locks
    parameters:
      - name: client_name
        in: query
        type: ClientName
      - name: resource_uri
        in: query
        type: ResourceUri
      - name: lock_type
        in: query
        type: LockType       
    operationId: listLocks
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: List of matching locks
        schema:
          type: array
          items:
            $ref: '#/definitions/Lock'
    """
    return jsonify_obj(get_locker().get_locks(client_name=request.args.get('client_name'),
                                              resource_uri=request.args.get('resource_uri'),
                                              lock_type=request.args.get('lock_type')))


@app.route('/clients', methods=['POST'])
def client():
    """
    Create a new client
    ---
    tags:
      - clients
    parameters:
      - name: client_name
        in: query
        type: ClientName
    operationId: createClient
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: Client
        schema:
           $ref: '#/definitions/Client'
    """
    if json_pattern.match(request.headers['Content-Type']):
        logging.debug("Creating client " + str(request.args.get('client_name')))
        return jsonify_obj(get_locker().get_client(request.args.get('client_name')))
    else:
        return "Could not handle input of type " + request.headers['Content-Type'], 415


@app.route('/clients/<int:client_id>', methods=['DELETE'])
def delete_client(client_id):
    """
    Delete a client
    ---
    tags:
      - clients
    parameters:
      - name: client_id
        in: path
        type: integer
        example: 1
    operationId: deleteClient
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: Client confirmation
        schema:
           properties:
               id:
                   type: integer
                   example: 1
    """
    try:
        get_locker().delete_client(client_id)
        return jsonify({"id": client_id})
    except IntegrityError:
        return "Client " + str(client_id) + " has active locks", 400
    except ValueError:
        return "Client " + str(client_id) + " not found", 404


@app.route('/clients', methods=['GET'])
def get_clients():
    """
    Return current clients
    ---
    tags:
      - clients
    operationId: listClients
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: List of clients
        schema:
          type: array
          items:
            $ref: '#/definitions/Client'
    """
    return jsonify_obj(get_locker().get_clients())


@app.route('/clients/<int:client_id>', methods=['GET'])
def get_client(client_id):
    """
    Retrieve a client
    ---
    tags:
      - clients
    parameters:
      - name: client_id
        in: path
        type: integer
        example: 1
    operationId: retrieveClient
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: Client found
        schema:
            $ref: '#/definitions/Client'
      404:
        description: Client not found
        examples:
            - Client 1 not found
    """
    client = get_locker().get_client_by_id(client_id)
    if client is None:
        return "Client " + str(client_id) + " not found", 404
    else:
        return jsonify_obj(client)


@app.route('/resources', methods=['POST'])
def resource():
    """
    Create a new resource
    ---
    tags:
      - resources
    parameters:
      - name: resource_uri
        in: query
        type: resourceUri
    operationId: createResource
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: Resource created
        schema:
           $ref: '#/definitions/Resource'
    """
    logging.debug("Creating resource " + str(request.args.get('resource_uri')))
    return jsonify_obj(get_locker().get_resource(request.args.get('resource_uri')))


@app.route('/resources/<int:resource_id>', methods=['DELETE'])
def delete_resource(resource_id):
    """
    Delete a resource
    ---
    tags:
      - resources
    parameters:
      - name: resource_id
        in: path
        type: integer
        example: 1
    operationId: deleteResource
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: Resource confirmation
        schema:
           properties:
               id:
                   type: integer
                   example: 1
    """
    get_locker().delete_resource(resource_id)
    return jsonify_obj({"id": resource_id})


@app.route('/resources', methods=['GET'])
def get_resources():
    """
    Return current resources
    ---
    tags:
      - resources
    operationId: listResources
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: List of resources
        schema:
          type: array
          items:
            $ref: '#/definitions/Resource'
    """
    return jsonify_obj(get_locker().get_resources())


@app.route('/resources/<int:resource_id>', methods=['GET'])
def get_resource(resource_id):
    """
    Retrieve a resource
    ---
    tags:
      - resources
    parameters:
      - name: resource_id
        in: path
        type: integer
        example: 1
    operationId: retrieveResource
    produces:
      - application/json
    schemes: ['http', 'https']
    responses:
      200:
        description: Resource found
        schema:
            $ref: '#/definitions/Resource'
      404:
        description: Resource not found
        examples:
            - Resource 1 not found
    """
    resource = get_locker().get_resource_by_id(resource_id)
    if resource is None:
        return "Resource " + str(resource_id) + " not found", 404
    else:
        return jsonify_obj(resource)


if __name__ == "__main__":
    app.run(debug=True)
