#!/usr/bin/env python
import json
import logging
import re

from flasgger import Swagger
from flask import Flask, request, jsonify
from flask_cors import CORS

from ensembl_prodinf.utils import app_logging
from ensembl_prodinf import HiveInstance
from ensembl_prodinf.email_tasks import email_when_complete

logger = logging.getLogger(__name__)

app = Flask(__name__, instance_relative_config=True)
app.config['SWAGGER'] = {
    'title': 'Production healthchecks REST endpoints',
    'uiversion': 2
}
app.config.from_object('hc_config')
app.config.from_pyfile('hc_config.py', silent=True)
app.analysis = app.config["HIVE_ANALYSIS"]

app_logging.add_app_handler(app.logger, __name__)

logger.info(app.config)
swagger = Swagger(app)

hive = None


def get_hive():
    global hive
    if hive is None:
        hive = HiveInstance(app.config["HIVE_URI"])
    return hive


app.hc_list = None


def get_hc_list():
    if app.hc_list is None:
        with open(app.config["HC_LIST_FILE"], 'r') as f:
            app.hc_list = json.loads(f.read())
    return app.hc_list


app.hc_groups = None


def get_hc_groups():
    if app.hc_groups is None:
        with open(app.config["HC_GROUPS_FILE"], 'r') as f:
            app.hc_groups = json.loads(f.read())
    return app.hc_groups


cors = CORS(app)

# use re to support different charsets
json_pattern = re.compile("application/json")


@app.route('/', methods=['GET'])
def info():
    return jsonify(app.config['SWAGGER'])


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok"})


@app.route('/jobs', methods=['POST'])
def submit_job():
    """
    Endpoint to submit an healthcheck job
    This is using docstring for specifications
    ---
    tags:
      - jobs
    parameters:
      - in: body
        name: body
        description: healthcheck object
        required: false
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
        title: Healthcheck job
        description: A job to run multiple healthchecks or healthchecks groups on a given database URI.
        type: object
        required: 
          -db_uri
          -compara_uri
          -live_uri
          -production_uri
          -staging_uri
          -hc_names
          -data_files_path
        properties:
          db_uri:
            type: string
            example: 'mysql://user@server:port/saccharomyces_cerevisiae_core_91_4'
          compara_uri:
            type: string
            example: 'mysql://user:password@server:port/compara_master'
          live_uri:
            type: string
            example: 'mysql://user:password@server:port/'
          staging_uri:
            type: string
            example: 'mysql://user:password@server:port/'
          production_uri:
            type: string
            example: 'mysql://user:password@server:port/ensembl_production_xx'
          hc_names:
            type: array
            items:
              type: string
              example: 'org.ensembl.healthcheck.testcase.generic.StableID'
          hc_groups:
            type: array
            items:
              type: string
              example: ''
          data_files_path:
            type: string
            example: '/nfs/panda/ensembl/production/ensemblftp/data_files/'
          email:
            type: string
            example: 'undefined'
    responses:
      200:
        description: submit of an healthcheck job
        schema:
          $ref: '#/definitions/submit'
        examples:
          {db_uri: "mysql://user@server:port/saccharomyces_cerevisiae_core_91_4", staging_uri: "mysql://user@server:port/", live_uri: "mysql://user@server:port/", production_uri: "mysql://user@server:port/ensembl_production_91", compara_uri: "mysql://user@server:port/ensembl_compara_master", hc_names: ["org.ensembl.healthcheck.testcase.generic.StableID"]}
    """
    if json_pattern.match(request.headers['Content-Type']):
        logger.debug("Submitting HC " + str(request.json))
        job = get_hive().create_job(app.analysis, request.json)
        results = {"job_id": job.job_id};
        email = request.json.get('email')
        if email is not None and email != '':
            logger.debug("Submitting email request for  " + email)
            email_results = email_when_complete.delay(request.url_root + "jobs/" + str(job.job_id) + "?format=email",
                                                      email)
            results['email_task'] = email_results.id
        return jsonify(results), 201
    else:
        logger.error("Could not handle input of type " + request.headers['Content-Type'])
        raise ValueError("Could not handle input of type " + request.headers['Content-Type'])


@app.route('/jobs/<int:job_id>', methods=['GET'])
def job_result(job_id):
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
        default: 1
        description: id of the job
      - name: format
        in: query
        type: string
        required: false
        description: optional parameter (email, failures)
      - name: email
        in: query
        type: string
        required: false
        description: Email address to use in report       
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
             compara_uri: mysql://user@server:port/ensembl_compara_master
             data_files_path: /nfs/panda/ensembl/production/ensemblftp/data_files/
             db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
             hc_names: ['org.ensembl.healthcheck.testcase.eg_core.GeneSource']
             live_uri: mysql://user@server:port/
             production_uri: mysql://user@server:port/ensembl_production_91
             staging_uri: mysql://user@server:port/
             timestamp: 1515494166.015124
          output:
             db_name: ailuropoda_melanoleuca_core_91_1
             db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
             results:
                org.ensembl.healthcheck.testcase.eg_core.GeneSource:
                    messages: ['PROBLEM: Found 23262 genes with source Ensembl which should be replaced with an appropriate GOA compatible name for the original source']
                    status: failed
             status: failed
          status: complete
    """
    fmt = request.args.get('format')
    logger.debug("Format " + str(fmt))
    if fmt == 'email':
        email = request.args.get('email')
        return job_email(email, job_id)
    elif fmt == 'failures':
        return job_failures(job_id)
    elif fmt is None:
        logger.info("Retrieving job with ID " + str(job_id))
        return jsonify(get_hive().get_result_for_job_id(job_id))
    else:
        raise Exception("Format " + fmt + " not valid")


def job_email(email, job_id):
    logger.info("Retrieving job with ID " + str(job_id) + " for " + str(email))
    job = get_hive().get_job_by_id(job_id)
    results = get_hive().get_result_for_job_id(job_id)
    if results['status'] == 'complete':
        results['subject'] = 'Healthchecks for %s - %s' % (results['output']['db_name'], results['output']['status'])
        results['body'] = 'Please see URL for more details: %s%s\n\n' % (results['input']['result_url'], job_id)
        results['body'] += "Results for %s:\n" % (results['output']['db_uri'])
        for (test, result) in results['output']['results'].iteritems():
            results['body'] += "* %s : %s\n" % (test, result['status'])
            if result['messages'] != None:
                for msg in result['messages']:
                    results['body'] += "** %s\n" % (msg)
    elif results['status'] == 'failed':
        failures = get_hive().get_jobs_failure_msg(job_id)
        results['subject'] = 'Healthcheck job failed'
        results['body'] = 'Please see URL for more details: %s%s\n\n' % (results['input']['result_url'], job_id)
        results['body'] += 'Healthcheck job failed with following message:\n'
        for (jobid, msg) in failures.iteritems():
            results['body'] += "* Job ID %s : %s\n" % (jobid, msg)
    results['output'] = None
    return jsonify(results)


def job_failures(job_id):
    logger.info("Retrieving failure for job with ID " + str(job_id))
    return jsonify(get_hive().get_jobs_failure_msg(job_id))


@app.route('/jobs/<int:job_id>', methods=['DELETE'])
def delete_job(job_id):
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
        default: 1
        description: id of the job
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
    hive = get_hive()
    job = get_hive().get_job_by_id(job_id)
    hive.delete_job(job)
    return jsonify({"id": job_id})


@app.route('/jobs', methods=['GET'])
def jobs():
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
            compara_uri: mysql://user@server:port/ensembl_compara_master
            data_files_path: /nfs/panda/ensembl/production/ensemblftp/data_files/
            db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
            hc_names: ['org.ensembl.healthcheck.testcase.eg_core.GeneSource']
            live_uri: mysql://user@server:port/
            production_uri: mysql://user@server:port/ensembl_production_91
            staging_uri: mysql://user@server:port/
            timestamp: 1515494166.015124
          output: 
            db_name: ailuropoda_melanoleuca_core_91_1
            db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
            results:
            org.ensembl.healthcheck.testcase.eg_core.GeneSource:
                messages: ['PROBLEM: Found 23262 genes with source Ensembl which should be replaced with an appropriate GOA compatible name for the original source']
                status: failed
            status: failed
          status: complete
          id: 4 
          input: 
            compara_uri: mysql://user@server:port/ensembl_compara_master
            data_files_path: /nfs/panda/ensembl/production/ensemblftp/data_files/
            db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
            email: john.doe@ebi.ac.uk
            hc_names: ['org.ensembl.healthcheck.testcase.eg_core.GeneSource']
            live_uri: mysql://user@server:port/
            production_uri: mysql://user@server:port/ensembl_production_91
            staging_uri: mysql://user@server:port/
            timestamp: 1515494256.239413
          output: 
            db_name: ailuropoda_melanoleuca_core_91_1
            db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
            results:
              org.ensembl.healthcheck.testcase.eg_core.GeneSource:
                messages: ['PROBLEM: Found 23262 genes with source Ensembl which should be replaced with an appropriate GOA compatible name for the original source']
                status: failed
              status: failed
          status: complete
          body: 'Results for mysql://user@server:port/ailuropoda_melanoleuca_core_91_1: * org.ensembl.healthcheck.testcase.eg_core.GeneSource : failed ** PROBLEM: Found 23262 genes with source Ensembl which should be replaced with an appropriate GOA compatible name for the original source'
          id: 4
          input:
            compara_uri: mysql://user@server:port/ensembl_compara_master 
            data_files_path: /nfs/panda/ensembl/production/ensemblftp/data_files/ 
            db_uri: mysql://user@server:port/ailuropoda_melanoleuca_core_91_1
            email: john.doe@ebi.ac.uk
            hc_names: ['org.ensembl.healthcheck.testcase.eg_core.GeneSource']
            live_uri: mysql://user@server:port/
            production_uri: mysql://user@server:port/ensembl_production_91
            staging_uri: mysql://user@server:port/
            timestamp: 1515494256.239413 
          output: null
          status: complete
          subject: 'Healthchecks for ailuropoda_melanoleuca_core_91_1 - failed'
    """
    logger.info("Retrieving jobs")
    return jsonify(get_hive().get_all_results(app.analysis))


@app.route('/healthchecks/tests', methods=['GET'])
def list_healthchecks_tests_endpoint():
    """
    Endpoint to return a list of hc matching a user query
    This is using docstring for specifications
    ---
    tags:
      - healthchecks
    parameters:
      - in: query
        name: query
        type: string
        required: true
        default: test_name
        description: test name name used to filter down the list
    operationId: healthchecks_tests
    consumes:
      - application/json
    produces:
      - application/json
    security:
      healthchecks_tests_auth:
        - 'write:healthchecks_tests'
        - 'read:healthchecks_tests'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      query:
        type: object
        properties:
          query:
            type: string
            items:
              $ref: '#/definitions/query'
      test_name:
        type: object
        properties:
          test_name:
            type: string
            items:
              $ref: '#/definitions/test_name'
    responses:
      200:
        description: list healthchecks tests
        schema:
          $ref: '#/definitions/host'
        examples:
          ["org.ensembl.healthcheck.testcase.eg_core.MultiDbCompareNames"]
    """
    query = request.args.get('query')
    if query is None:
        return jsonify(get_hc_list())
    logger.debug("Finding healthchecks tests matching " + query)
    hc_list = filter(lambda x: str(query).lower() in x.lower(), get_hc_list())
    return jsonify(hc_list)


@app.route('/healthchecks/groups', methods=['GET'])
def list_healthchecks_groups_endpoint():
    """
    Endpoint to return a list of hc matching a user query
    This is using docstring for specifications
    ---
    tags:
      - healthchecks
    parameters:
      - in: query
        name: query
        type: string
        required: true
        default: group_name
        description: group name used to filter down the list
    operationId: healthchecks_groups
    consumes:
      - application/json
    produces:
      - application/json
    security:
      healthchecks_groups_auth:
        - 'write:healthchecks_groups'
        - 'read:healthchecks_groups'
    schemes: ['http', 'https']
    deprecated: false
    externalDocs:
      description: Project repository
      url: http://github.com/rochacbruno/flasgger
    definitions:
      query:
        type: object
        properties:
          query:
            type: string
            items:
              $ref: '#/definitions/query'
      group_name:
        type: object
        properties:
          group_name:
            type: string
            items:
              $ref: '#/definitions/group_name'
    responses:
      200:
        description: list healthcheck groups
        schema:
          $ref: '#/definitions/host'
        examples:
          ["org.ensembl.healthcheck.testcase.eg_core.MultiDbCompareNames"]
    """
    query = request.args.get('query')
    if query is None:
        return jsonify(get_hc_groups())
    logger.debug("Finding healthchecks groups matching " + query)
    hc_groups = filter(lambda x: str(query).lower() in x.lower(), get_hc_groups())
    return jsonify(hc_groups)


@app.route('/healthchecks', methods=['GET'])
def healthchecks_endpoint():
    return jsonify({"tests": request.url + "/tests", "groups": request.url + "/groups"})


@app.errorhandler(Exception)
def handle_error(e):
    code = 500
    if isinstance(e, ValueError):
        code = 400
    logger.exception(str(e))
    return jsonify(error=str(e)), code


if __name__ == "__main__":
    app.run(debug=True)
