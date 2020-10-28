#!/usr/bin/env python

import logging
import re

from elasticsearch import Elasticsearch, TransportError, NotFoundError
from sqlalchemy.exc import OperationalError
from flasgger import Swagger
from flask import Flask, request, jsonify
from flask_cors import CORS

import app_logging
from ensembl_prodinf.handover_tasks import handover_database
from ensembl_prodinf.exceptions import HTTPRequestError


app = Flask(__name__, instance_relative_config=True)
app.config.from_object('handover_config')
app.logger.addHandler(app_logging.default_handler())
app.config['SWAGGER'] = {
    'title': 'Handover App',
    'uiversion': 2
}

swagger = Swagger(app)
cors = CORS(app)

# use re to support different charsets
json_pattern = re.compile("application/json")
es_host = app.config['ES_HOST']
es_port = str(app.config['ES_PORT'])
es_index = app.config['ES_INDEX']


@app.route('/', methods=['GET'])
def info():
    app.config['SWAGGER'] = {'title': 'Handover REST endpoints', 'uiversion': 2}
    return jsonify(app.config['SWAGGER'])


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok"})


@app.route('/handovers', methods=['POST'])
def handovers():
    """
    Endpoint to submit an handover job
    This is using docstring for specifications
    ---
    tags:
      - handovers
    parameters:
      - in: body
        name: body
        description: healthcheck object
        required: false
        schema:
          $ref: '#/definitions/handovers'
    operationId: handovers
    consumes:
      - application/json
    produces:
      - application/json
    security:
      handovers_auth:
        - 'write:handovers'
        - 'read:handovers'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      handovers:
        title: handover job
        description: A job to handover a database, the database will be healthchecked, copied and added to metadata database
        type: object
        required:
          -src_uri
          -contact
          -type
          -comment
        properties:
          src_uri:
            type: string
            example: 'mysql://user@server:port/saccharomyces_cerevisiae_core_91_4'
          comment:
            type: string
            example: 'handover new Panda OF'
          contact:
            type: string
            example: 'joe.blogg@ebi.ac.uk'
    responses:
      200:
        description: submit of an handover job
        schema:
          $ref: '#/definitions/handovers'
        examples:
          {src_uri: "mysql://user@server:port/saccharomyces_cerevisiae_core_91_4", contact: "joe.blogg@ebi.ac.uk", comment: "handover new Panda OF"}
    """
    if json_pattern.match(request.headers['Content-Type']):
        app.logger.debug('Submitting handover request %s', request.json)
        spec = request.json
        if 'src_uri' not in spec or 'contact' not in spec or 'comment' not in spec:
            raise HTTPRequestError("Handover specification incomplete - please specify src_uri, contact and comment")
        ticket = handover_database(spec)
        app.logger.info('Ticket: %s', ticket)
        return jsonify(ticket);
    else:
        raise HTTPRequestError('Could not handle input of type %s' % request.headers['Content-Type'])


@app.route('/handovers/<string:handover_token>', methods=['GET'])
def handover_result(handover_token):
    """
    Endpoint to get an handover job detail
    This is using docstring for specifications
    ---
    tags:
      - handovers
    parameters:
      - name: handover_token
        in: path
        type: string
        required: true
        default: 15ce20fd-68cd-11e8-8117-005056ab00f0
        description: handover token for the database handed over
    operationId: handovers
    consumes:
      - application/json
    produces:
      - application/json
    security:
      handovers_auth:
        - 'write:handovers'
        - 'read:handovers'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      handovers:
        title: Get a handover job details
        description: This will retrieve a handover job details
        type: object
        required:
          -handover_token
        properties:
          handover_token:
            type: string
            example: '15ce20fd-68cd-11e8-8117-005056ab00f0'
    responses:
      200:
        description: Retrieve an handover job ticket
        schema:
          $ref: '#/definitions/handovers'
        examples:
          [{"comment": "handover new Tiger database", "contact": "maurel@ebi.ac.uk", "handover_token": "605f1191-7a13-11e8-aa7e-005056ab00f0", "id": "X1qcQWQBiZ0vMed2vaAt", "message": "Metadata load complete, Handover successful", "progress_total": 3, "report_time": "2018-06-27T15:19:08.459", "src_uri": "mysql://ensro@mysql-ens-general-prod-1:4525/panthera_tigris_altaica_core_93_1", "tgt_uri": "mysql://ensro@mysql-ens-general-dev-1:4484/panthera_tigris_altaica_core_93_1"} ]
    """
    es = Elasticsearch([{'host': es_host, 'port': es_port}])
    handover_detail = []
    res_error = es.search(index=es_index, body={"query": {"bool": {
        "must": [{"term": {"params.handover_token.keyword": str(handover_token)}},
                 {"term": {"report_type.keyword": "ERROR"}}], "must_not": [], "should": []}}, "from": 0, "size": 1,
        "sort": [{"report_time": {"order": "desc"}}], "aggs": {}})
    app.logger.info('Retrieving handover data with token %s', handover_token)
    if len(res_error['hits']['hits']) != 0:
        for doc in res_error['hits']['hits']:
            result = {"id": doc['_id']}
            result['message'] = doc['_source']['message']
            result['comment'] = doc['_source']['params']['comment']
            result['handover_token'] = doc['_source']['params']['handover_token']
            result['contact'] = doc['_source']['params']['contact']
            result['src_uri'] = doc['_source']['params']['src_uri']
            result['tgt_uri'] = doc['_source']['params']['tgt_uri']
            result['report_time'] = doc['_source']['report_time']
            handover_detail.append(result)
    else:
        res = es.search(index=es_index, body={"query": {"bool": {
            "must": [{"term": {"params.handover_token.keyword": str(handover_token)}},
                     {"term": {"report_type.keyword": "INFO"}}], "must_not": [], "should": []}}, "from": 0,
            "size": 1, "sort": [{"report_time": {"order": "desc"}}], "aggs": {}})
        for doc in res['hits']['hits']:
            result = {"id": doc['_id']}
            result['message'] = doc['_source']['message']
            result['comment'] = doc['_source']['params']['comment']
            result['handover_token'] = doc['_source']['params']['handover_token']
            result['contact'] = doc['_source']['params']['contact']
            result['src_uri'] = doc['_source']['params']['src_uri']
            result['tgt_uri'] = doc['_source']['params']['tgt_uri']
            result['progress_complete'] = doc['_source']['params']['progress_complete']
            result['progress_total'] = doc['_source']['params']['progress_total']
            result['report_time'] = doc['_source']['report_time']
            handover_detail.append(result)
    if len(handover_detail) == 0:
        raise HTTPRequestError('Handover token %s not found' % handover_token, 404)
    else:
        return jsonify(handover_detail)


@app.route('/handovers', methods=['GET'])
def handover_results():
    """
    Endpoint to get a list of all the handover by release
    This is using docstring for specifications
    ---
    tags:
      - handovers
    operationId: handovers
    parameters:
      - name: release
        in: query
        type: string
        description: get handover list for the given release
    consumes:
      - application/json
    produces:
      - application/json
    security:
      handovers_auth:
        - 'write:handovers'
        - 'read:handovers'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      handovers:
        title: Retrieve a list of handover databases
        description: This will retrieve all the handover job details
        type: object
    responses:
      200:
        description: Retrieve all the handover job details
        schema:
          $ref: '#/definitions/handovers'
        examples:
          [{"comment": "handover new Tiger database", "contact": "maurel@ebi.ac.uk", "handover_token": "605f1191-7a13-11e8-aa7e-005056ab00f0", "id": "QFqRQWQBiZ0vMed2vKDI", "message": "Handling {u'comment': u'handover new Tiger database', 'handover_token': '605f1191-7a13-11e8-aa7e-005056ab00f0', u'contact': u'maurel@ebi.ac.uk', u'src_uri': u'mysql://ensro@mysql-ens-general-prod-1:4525/panthera_tigris_altaica_core_93_1', 'tgt_uri': 'mysql://ensro@mysql-ens-general-dev-1:4484/panthera_tigris_altaica_core_93_1'}", "report_time": "2018-06-27T15:07:07.462", "src_uri": "mysql://ensro@mysql-ens-general-prod-1:4525/panthera_tigris_altaica_core_93_1", "tgt_uri": "mysql://ensro@mysql-ens-general-dev-1:4484/panthera_tigris_altaica_core_93_1"}, {"comment": "handover new Leopard database", "contact": "maurel@ebi.ac.uk", "handover_token": "5dcb1aca-7a13-11e8-b24e-005056ab00f0", "id": "P1qRQWQBiZ0vMed2rqBh", "message": "Handling {u'comment': u'handover new Leopard database', 'handover_token': '5dcb1aca-7a13-11e8-b24e-005056ab00f0', u'contact': u'maurel@ebi.ac.uk', u'src_uri': u'mysql://ensro@mysql-ens-general-prod-1:4525/panthera_pardus_core_93_1', 'tgt_uri': 'mysql://ensro@mysql-ens-general-dev-1:4484/panthera_pardus_core_93_1'}", "report_time": "2018-06-27T15:07:03.145", "src_uri": "mysql://ensro@mysql-ens-general-prod-1:4525/panthera_pardus_core_93_1", "tgt_uri": "mysql://ensro@mysql-ens-general-dev-1:4484/panthera_pardus_core_93_1"} ]
    """
    release = request.args.get('release', str(app.config['RELEASE']))
    app.logger.info("Retrieving all handover report")
    es = Elasticsearch([{'host': es_host, 'port': es_port}])
    res = es.search(index=es_index, body={
        "query": {
            "bool": {
                "must": [{
                    "query_string": {
                        "fields": ["message"],
                        "query": "Handling*",
                        "analyze_wildcard": "true"}
                },
                {
                    "query_string": {
                        "fields": ["params.tgt_uri"],
                        "query": "/.*_{}(_[0-9]+)?/".format(release)}
                }]
            }
        },
        "size": 1000,
        "sort": [{
            "report_time": {"order": "desc"}
        }]
    })
    list_handovers = []
    for doc in res['hits']['hits']:
        if valid_handover(doc, release):
            result = {"id": doc['_id']}
            result['message'] = doc['_source']['message']
            result['comment'] = doc['_source']['params']['comment']
            result['handover_token'] = doc['_source']['params']['handover_token']
            res_error = es.search(index=es_index, body={"query": {"bool": {
                "must": [{"term": {"params.handover_token.keyword": str(doc['_source']['params']['handover_token'])}},
                         {"term": {"report_type.keyword": "ERROR"}}], "must_not": [], "should": []}}, "from": 0,
                "size": 1, "sort": [{"report_time": {"order": "desc"}}],
                "aggs": {}})
            if len(res_error['hits']['hits']) != 0:
                for doc_error in res_error['hits']['hits']:
                    result['current_message'] = doc_error['_source']['message']
            else:
                res2 = es.search(index=es_index, body={"query": {"bool": {"must": [
                    {"term": {"params.handover_token.keyword": str(doc['_source']['params']['handover_token'])}},
                    {"term": {"report_type.keyword": "INFO"}}], "must_not": [], "should": []}}, "from": 0, "size": 1,
                    "sort": [{"report_time": {"order": "desc"}}], "aggs": {}})
                for doc2 in res2['hits']['hits']:
                    result['current_message'] = doc2['_source']['message']
            result['contact'] = doc['_source']['params']['contact']
            result['src_uri'] = doc['_source']['params']['src_uri']
            result['tgt_uri'] = doc['_source']['params']['tgt_uri']
            result['report_time'] = doc['_source']['report_time']
            list_handovers.append(result)
    return jsonify(list_handovers)


def valid_handover(doc, release):
    src_uri = doc['_source']['params']['src_uri']
    match = re.match(r'^.*?_(?P<first>\d+)(_(?P<second>\d+))?(_(\d+))?$', src_uri)
    if match:
        first = match.group('first')
        second = match.group('second')
        return (first == release) or ((second == release) and (int(second) - int(first) == 53))
    return False


@app.route('/handovers/<string:handover_token>', methods=['DELETE'])
def delete_handover(handover_token):
    """
    Endpoint to delete all the reports linked to a handover_token
    This is using docstring for specifications
    ---
    tags:
      - handovers
    parameters:
      - name: handover_token
        in: path
        type: string
        required: true
        default: 15ce20fd-68cd-11e8-8117-005056ab00f0
        description: handover token for the database handed over
    operationId: handovers
    consumes:
      - application/json
    produces:
      - application/json
    security:
      delete_auth:
        - 'write:delete'
        - 'read:delete'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      handover_token:
        type: object
        properties:
          handover_token:
            type: integer
            items:
              $ref: '#/definitions/handover_token'
      id:
        type: integer
        properties:
          id:
            type: integer
            items:
              $ref: '#/definitions/id'
    responses:
      200:
        description: handover_token of the reports that need deleting
        schema:
          $ref: '#/definitions/handover_token'
        examples:
          id: 15ce20fd-68cd-11e8-8117-005056ab00f0
    """
    try:
        app.logger.info('Retrieving handover data with token %s', handover_token)
        es = Elasticsearch([{'host': es_host, 'port': es_port}])
        es.delete_by_query(index=es_index, doc_type='report', body={
            "query": {"bool": {"must": [{"term": {"params.handover_token.keyword": str(handover_token)}}]}}})
        return jsonify(str(handover_token))
    except NotFoundError as e:
        raise HTTPRequestError('Error while looking for handover token: {} - {}:{}'.format(
            handover_token, e.error, e.info['error']['reason']), 404)


@app.errorhandler(TransportError)
def handle_elastisearch_error(e):
    app.logger.error(str(e))
    message = 'Elasticsearch Error [%s] %s: %s' % (e.status_code, e.error, e.info['error']['reason'])
    return jsonify(error=message), e.status_code


@app.errorhandler(HTTPRequestError)
def handle_bad_request_error(e):
    app.logger.error(str(e))
    return jsonify(error=str(e)), e.status_code


@app.errorhandler(OperationalError)
def handle_sqlalchemy_error(e):
    app.logger.error(str(e))
    return jsonify(error=str(e)), 500
