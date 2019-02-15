#!/usr/bin/env python
import json
import logging
import os
import re

import signal
import time
from flasgger import Swagger
from flask import Flask, request, jsonify
from flask_cors import CORS

from ensembl_prodinf.utils import app_logging
from ensembl_prodinf import HiveInstance
from ensembl_prodinf.db_utils import list_databases, get_database_sizes
from ensembl_prodinf.email_tasks import email_when_complete
from ensembl_prodinf.server_utils import get_status, get_load

logger = logging.getLogger(__name__)

app = Flask(__name__, instance_relative_config=True)
app.config.from_object('db_config')
app.config.from_pyfile('db_config.py', silent=True)
app.analysis = app.config["HIVE_ANALYSIS"]
app.config['SWAGGER'] = {
    'title': 'Database copy REST endpoints',
    'uiversion': 2
}

swagger = Swagger(app)
app.servers = None
app_logging.add_app_handler(app.logger, __name__)


def get_servers():
    if app.servers is None:
        with open(app.config["SERVER_URIS_FILE"], 'r') as f:
            app.servers = json.loads(f.read())
    return app.servers


hive = None


def get_hive():
    global hive
    if hive is None:
        hive = HiveInstance(app.config["HIVE_URI"])
    return hive


def is_running(pid):
    try:
        os.kill(pid, 0)
    except OSError as err:
        return False
    return True


cors = CORS(app)

# use re to support different charsets
json_pattern = re.compile("application/json")


@app.route('/', methods=['GET'])
def info():
    return jsonify(app.config['SWAGGER'])


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok"})


@app.route('/databases', methods=['GET'])
def list_databases_endpoint():
    """
    Endpoint to retrieve a list of databases from a server given as URI
    This is using docstring for specifications
    ---
    tags:
      - databases
    parameters:
      - in : query
        name: db_uri
        type: string
        required: true
        default: mysql://user@server:port/
        description: MySQL server db_uri
      - in : query
        name: query
        type: string
        required: true
        default: homo_sapiens
        description: query use to find databases
    operationId: databases
    consumes:
      - application/json
    produces:
      - application/json
    security:
      list_databases_auth:
        - 'write:list_databases'
        - 'read:list_databases'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      db_uri:
        type: db_uri
        properties:
          db_uri:
            type: string
            items:
              $ref: '#/definitions/db_uri'
      query:
        type: query
        properties:
          query:
            type: string
            items:
              $ref: '#/definitions/query'
      list_databases:
        type: object
        properties:
          list_databases:
            type: string
            items:
              $ref: '#/definitions/list_databases'
    responses:
      200:
        description: list_databases of a MySQL server
        schema:
          $ref: '#/definitions/list_databases'
        examples:
          ["homo_sapiens_cdna_91_38", "homo_sapiens_core_91_38","homo_sapiens_funcgen_91_38","homo_sapiens_otherfeatures_91_38","homo_sapiens_rnaseq_91_38","homo_sapiens_variation_91_38"]
    """
    db_uri = request.args.get('db_uri')
    query = request.args.get('query')
    logger.debug("Finding dbs matching " + query + " on " + db_uri)
    return jsonify(list_databases(db_uri, query))


@app.route('/databases/sizes', methods=['GET'])
def database_sizes_endpoint():
    """
    Endpoint to retrieve a list of databases and their size from a MySQL server given as URI
    This is using docstring for specifications
    ---
    tags:
      - databases
    parameters:
      - in : query
        name: db_uri
        type: string
        required: true
        default: mysql://user@server:port/
        description: MySQL server db_uri
      - in : query
        name: query
        type: string
        required: true
        default: homo_sapiens
        description: query use to find databases
      - in : query
        name: dir_name
        type: string
        required: false
        default: /instances
        description: Directory name where the database files are located on the MySQL server
    operationId: database_sizes
    consumes:
      - application/json
    produces:
      - application/json
    security:
      database_sizes_auth:
        - 'write:database_sizes'
        - 'read:database_sizes'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      db_uri:
        type: db_uri
        properties:
          db_uri:
            type: string
            items:
              $ref: '#/definitions/db_uri'
      query:
        type: query
        properties:
          query:
            type: string
            items:
              $ref: '#/definitions/query'
      dir_name:
        type: dir_name
        properties:
          dir_name:
            type: string
            items:
              $ref: '#/definitions/dir_name'
      database_sizes:
        type: object
        properties:
          database_sizes:
            type: string
            items:
              $ref: '#/definitions/database_sizes'
    responses:
      200:
        description: database_sizes of all the databases from a MySQL server
        schema:
          $ref: '#/definitions/database_sizes'
        examples:
          {  "mus_caroli_core_91_11": 4890, "ncbi_taxonomy": 362 }
    """
    db_uri = request.args.get('db_uri')
    query = request.args.get('query')
    dir_name = request.args.get('dir_name')
    if (dir_name is None):
        dir_name = '/instances'
    logger.debug("Finding sizes of dbs matching " + str(query) + " on " + db_uri)
    return jsonify(get_database_sizes(db_uri, query, dir_name))


@app.route('/hosts/<host>', methods=['GET'])
def get_status_endpoint(host):
    """
    Endpoint to retrieve the status of a give MySQL host
    This is using docstring for specifications
    ---
    tags:
      - hosts
    parameters:
      - name: host
        in: path
        type: string
        required: true
        default: server_name
        description: MySQL server host name
      - name: dir_name
        in: query
        type: string
        description: database directory name on MySQL server
    operationId: hosts
    consumes:
      - application/json
    produces:
      - application/json
    security:
      status_auth:
        - 'write:status'
        - 'read:status'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      host:
        type: object
        properties:
          host:
            type: string
            items:
              $ref: '#/definitions/host'
      status:
        type: object
        properties:
          status:
            type: string
            items:
              $ref: '#/definitions/status'
      dir_name:
        type: dir_name
        properties:
          dir_name:
            type: string
            items:
              $ref: '#/definitions/dir_name'
    responses:
      200:
        description: Status of a MySQL server
        schema:
          $ref: '#/definitions/host'
        examples:
          dir: /instances 
          disk_available_g: 1504 
          disk_total_g: 6048 
          disk_used_g: 4258 
          disk_used_pct: 70.4 
          host: server_name 
          load_15m: 0.05 
          load_1m: 0.0 
          load_5m: 0.01 
          memory_available_m: 270 
          memory_total_m: 48394 
          memory_used_m: 23624 
          memory_used_pct: 48.8 
          n_cpus: 16
    """
    dir_name = request.args.get('dir_name')
    if (dir_name is None):
        dir_name = '/instances'
    logger.debug("Finding status of " + host + " (dir " + dir_name + ")")
    return jsonify(get_status(host=host, dir_name=dir_name))


@app.route('/hosts/<host>/load', methods=['GET'])
def get_load_endpoint(host):
    """
    Endpoint to retrieve the load of a given MySQL server
    This is using docstring for specifications
    ---
    tags:
      - hosts
    parameters:
      - name: host
        in: path
        type: string
        required: true
        default: server_name
        description: MySQL server host name
    operationId: hosts
    consumes:
      - application/json
    produces:
      - application/json
    security:
      load_auth:
        - 'write:load'
        - 'read:load'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      host:
        type: object
        properties:
          host:
            type: string
            items:
              $ref: '#/definitions/host'
      load:
        type: object
        properties:
          load:
            type: string
            items:
              $ref: '#/definitions/load'
    responses:
      200:
        description: Load of a MySQL server
        schema:
          $ref: '#/definitions/host'
        examples:
          load_15m: 0.05 
          load_1m: 0.05 
          load_5m: 0.03
    """
    logger.debug("Finding load of " + host)
    return jsonify(get_load(host=host))


@app.route('/servers/<user>', methods=['GET'])
def list_servers_endpoint(user):
    """
    Endpoint to list the mysql servers accesible by a given user
    This is using docstring for specifications
    ---
    tags:
      - servers
    parameters:
      - name: user
        in: path
        type: string
        required: true
        default: ensro
        description: MySQL server user name
      - in: query
        name: query
        type: string
        required: true
        default: server_name
        description: MySQL server host name used to filter down the list
    operationId: servers
    consumes:
      - application/json
    produces:
      - application/json
    security:
      list_servers_auth:
        - 'write:list_servers'
        - 'read:list_servers'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      user:
        type: object
        properties:
          user:
            type: string
            items:
              $ref: '#/definitions/user'
      query:
        type: object
        properties:
          query:
            type: string
            items:
              $ref: '#/definitions/query'
      list_servers:
        type: object
        properties:
          list_servers:
            type: string
            items:
              $ref: '#/definitions/list_servers'
    responses:
      200:
        description: list_servers of a MySQL server
        schema:
          $ref: '#/definitions/host'
        examples:
          ["mysql://user@server:port/"]
    """
    query = request.args.get('query')
    if query is None:
        raise ValueError("Query not specified")
    if user in get_servers():
        logger.debug("Finding servers matching " + query + " for " + user)
        user_urls = get_servers()[user] or []
        urls = filter(lambda x: query in x, user_urls)
        return jsonify(urls)
    else:
        raise ValueError("User " + user + " not found")


@app.route('/jobs', methods=['POST'])
def submit():
    """
    Endpoint to submit a database copy job
    This is using docstring for specifications
    ---
    tags:
      - jobs
    parameters:
      - in: body
        name: body
        description: copy database job object
        requiered: false
        schema:
          $ref: '#/definitions/submit'
    operationId: jobs
    consumes:
      - application/json
    produces:
      - application/json
    security:
      submit_auth:
        - 'write:submit'
        - 'read:submit'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      submit:
        title: Database copy job
        description: A job to copy a database from a source MySQL server to a target MySQL server.
        type: object
        required: 
          -source_db_uri
          -target_db_uri
        properties:
          source_db_uri:
            type: string
            example: 'mysql://user@server:port/saccharomyces_cerevisiae_core_91_4'
          target_db_uri:
            type: string
            example: 'mysql://user:password@server:port/'
          only_tables:
            type: string
            example: 'undefined'
          skip_tables:
            type: string
            example: 'undefined'
          update:
            type: integer
            example: 0
          drop:
            type: integer
            example: 0
          email:
            type: string
            example: 'undefined'
    responses:
      200:
        description: submit of an healthcheck job
        schema:
          $ref: '#/definitions/submit'
        examples:
          {source_db_uri: "mysql://user@server:port/saccharomyces_cerevisiae_core_91_4", target_db_uri: "mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4", only_tables: undefined, skip_tables: undefined, update: undefined, drop: 1, email: undefined }
    """
    if json_pattern.match(request.headers['Content-Type']):
        logger.debug("Submitting Database copy " + str(request.json))
        job = get_hive().create_job(app.analysis, request.json)
        results = {"job_id": job.job_id};
        email = request.json.get('email')
        if email != None and email != '':
            logger.debug("Submitting email request for  " + email)
            email_results = email_when_complete.delay(request.url_root + "jobs/" + str(job.job_id) + "?format=email",
                                                      email)
            results['email_task'] = email_results.id
        return jsonify(results);
    else:
        logger.error("Could not handle input of type " + request.headers['Content-Type'])
        raise ValueError("Could not handle input of type " + request.headers['Content-Type'])


@app.route('/jobs/<int:job_id>', methods=['GET'])
def jobs(job_id):
    """
    Endpoint to retrieve a given job result using job_id
    This is using docstring for specifications
    ---
    tags:
      - jobs
    parameters:
      - name: job_id
        in: path
        type: integer
        required: true
        description: id of the job
      - name: format
        in: query
        type: string
        required: false
        description: optional output format (failures, email)
    operationId: jobs
    consumes:
      - application/json
    produces:
      - application/json
    security:
      results_auth:
        - 'write:results'
        - 'read:results'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      job_id:
        type: object
        properties:
          job_id:
            type: integer
            items:
              $ref: '#/definitions/job_id'
      result:
        type: object
        properties:
          result:
            type: string
            items:
              $ref: '#/definitions/result'
    responses:
      200:
        description: Result of an healthcheck job
        schema:
          $ref: '#/definitions/job_id'
        examples:
          id: 1 
          input: 
            drop: 1 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4 
            timestamp: 1515494114.263158
          output: 
            runtime: 31 seconds 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
          status: complete
    """
    fmt = request.args.get('format')
    if fmt == 'email':
        return job_email(request.args.get('email'), job_id)
    elif fmt == 'failures':
        return failure(job_id)
    elif fmt is None:
        logger.info("Retrieving job with ID " + str(job_id))
        return jsonify(get_hive().get_result_for_job_id(job_id))
    else:
        raise ValueError("Format " + str(fmt) + " not known")


def failure(job_id):
    logger.info("Retrieving failure for job with ID " + str(job_id))
    failure = get_hive().get_job_failure_msg_by_id(job_id)
    return jsonify({"msg": failure.msg})


def job_email(email, job_id):
    logger.info("Retrieving job with ID " + str(job_id) + " for " + str(email))
    job = get_hive().get_job_by_id(job_id)
    results = get_hive().get_result_for_job_id(job_id)
    if results['status'] == 'complete':
        results['subject'] = 'Copy database from %s to %s successful' % (
        results['output']['source_db_uri'], results['output']['target_db_uri'])
        results['body'] = 'Copy from %s to %s is successful\n' % (
        results['output']['source_db_uri'], results['output']['target_db_uri'])
        results['body'] += 'Copy took %s' % (results['output']['runtime'])
    elif results['status'] == 'failed':
        failure = get_hive().get_job_failure_msg_by_id(job_id)
        results['subject'] = 'Copy database from %s to %s failed' % (
        results['input']['source_db_uri'], results['input']['target_db_uri'])
        results['body'] = 'Copy failed with following message:\n'
        results['body'] += '%s\n\n' % (failure.msg)
        results['body'] += 'Please see URL for more details: %s%s \n' % (results['input']['result_url'], job_id)
    results['output'] = None
    return jsonify(results)


@app.route('/jobs/<int:job_id>', methods=['DELETE'])
def delete(job_id):
    """
    Endpoint to delete a given job result using job_id
    This is using docstring for specifications
    ---
    tags:
      - jobs
    parameters:
      - name: job_id
        in: path
        type: integer
        required: true
        description: id of the job
      - name: kill
        in: query
        type: integer
        required: false
        default: 0
        description: set to 1 to kill the process
    operationId: jobs
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
      job_id:
        type: object
        properties:
          job_id:
            type: integer
            items:
              $ref: '#/definitions/job_id'
      id:
        type: integer
        properties:
          id:
            type: integer
            items:
              $ref: '#/definitions/id'
    responses:
      200:
        description: Job_id that has been deleted
        schema:
          $ref: '#/definitions/job_id'
        examples:
          id: 1
    """
    if 'kill' in request.args.keys() and request.args['kill'] == 1:
        kill_job(job_id)
    job = get_hive().get_job_by_id(job_id)
    hive.delete_job(job)
    return jsonify({"id": job_id})


def kill_job(job_id):
    job = get_hive().get_job_by_id(job_id)
    logger.debug("Getting worker_id for job_id " + str(job_id))
    worker = get_hive().get_worker_id(job.role_id)
    logger.debug("Getting process_id for worker_id " + str(worker.worker_id))
    process_id = get_hive().get_worker_process_id(worker.worker_id)
    logger.debug("Process_id is " + str(process_id.process_id))
    os.kill(int(process_id.process_id), signal.SIGTERM)
    time.sleep(5)
    # Check if the process that we killed is alive.
    if is_running(int(process_id.process_id)):
        logger.error("Wasn't able to kill the process: " + str(process_id.process_id))
        raise ValueError("Wasn't able to kill the process: " + str(process_id.process_id))
    else:
        return jsonify({"process_id": process_id.process_id})


@app.route('/jobs', methods=['GET'])
def list_jobs():
    """
    Endpoint to retrieve all the jobs results from the database
    This is using docstring for specifications
    ---
    tags:
      - jobs
    operationId: jobs
    consumes:
      - application/json
    produces:
      - application/json
    security:
      jobs_auth:
        - 'write:jobs'
        - 'read:jobs'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    responses:
      200:
        description: Retrieve all the jobs results from the database
        schema:
          $ref: '#/definitions/job_id'
        examples:
          id: 1 
          input: 
            drop: 1 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4 
            timestamp: 1515494114.263158  
          output: 
            runtime: 31 seconds 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4     
          status: complete
          id: 2 
          input: 
            drop: 1 
            email: john.doe@ebi.ac.uk 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4 
            timestamp: 1515494178.544427  
          output: 
            runtime: 31 seconds 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4  
          status: complete
          id: 3 
          input: 
            drop: 1 
            email: john.doe@ebi.ac.uk 
            source_db_uri: mysql://user@server:port/saccharomyces_cerevisiae_core_91_4 
            target_db_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4 
            timestamp: 1515602446.492586  
          progress: 
            complete: 0 
            total: 1
          status: failed
    """
    logger.info("Retrieving jobs")
    return jsonify(get_hive().get_all_results(app.analysis))


@app.errorhandler(Exception)
def handle_error(e):
    code = 500
    if isinstance(e, ValueError):
        code = 400
    logger.exception(str(e))
    return jsonify(error=str(e)), code


if __name__ == "__main__":
    app.run(debug=True)
