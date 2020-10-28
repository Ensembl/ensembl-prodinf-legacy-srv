#!/usr/bin/env python

import logging
import os
import re

from flasgger import Swagger
from flask import Flask, request, jsonify
from flask_cors import CORS

import app_logging
from ensembl_prodinf.hive import HiveInstance
from ensembl_prodinf.email_tasks import email_when_complete
from ensembl_prodinf.exceptions import HTTPRequestError


app = Flask(__name__, instance_relative_config=True)
app.config.from_object('metadata_config')
app.analysis = app.config["HIVE_ANALYSIS"]
app.logger.addHandler(app_logging.default_handler())
app.config['SWAGGER'] = {
    'title': 'Metadata App',
    'uiversion': 2
}

swagger = Swagger(app)

hive = None


def get_hive():
    global hive
    if hive is None:
        hive = HiveInstance(app.config["HIVE_URI"])
    return hive


cors = CORS(app)

# use re to support different charsets
json_pattern = re.compile("application/json")

@app.route('/', methods=['GET'])
def info():
    app.config['SWAGGER'] = {'title': 'Metadata updater REST endpoints', 'uiversion': 2}
    return jsonify(app.config['SWAGGER'])


@app.route('/jobs', methods=['POST'])
def submit_job():
    """
    Endpoint to submit a database to be processed and added to the metadata database
    This is using docstring for specifications
    ---
    tags:
      - jobs
    parameters:
      - in: body
        name: body
        description: copy database job object
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
        title: Database copy job
        description: A job to process a database and add it to the metadata database from a source MySQL server to a target MySQL server.
        type: object
        required:
          -metadata_uri
          -database_uri
          -update_type
          -comment
          -email
          -source
        properties:
          metadata_uri:
            type: string
            example: 'mysql://user:password@server:port/metadata_db'
          database_uri:
            type: string
            example: 'mysql://user:password@server:port/db'
          e_release:
            type: integer
            example: 91
          eg_release:
            type: integer
            example: 38
          release_date:
            type: string
            example: '2017-12-06'
          current_release:
            type: integer
            example: 1
          email:
            type: string
            example: 'undefined'
          update_type:
            type: string
            example: 'new_assembly'
          comment:
            type: string
            example: 'handover of new species'
          source:
            type: string
            example: 'joe.bloggs@ebi.ac.uk'
    responses:
      201:
        description: submit of a metadata job
        schema:
          $ref: '#/definitions/submit'
        examples:
          {metadata_uri : "mysql://user:pass@mysql-ens-general-dev-1:4484/ensembl_metadata_new_test", database_uri : "mysql://ensro@mysql-ensembl-mirror:4240/octodon_degus_otherfeatures_91_1", update_type : "new_assembly", source : "Handover", comment : "handover new Leopard database", email : "joe.bloggs@ebi.ac.uk"}
    """
    if json_pattern.match(request.headers['Content-Type']):
        request.json["metadata_uri"] = app.config["METADATA_URI"]
        app.logger.debug('Submitting metadata job %s', request.json)
        try:
            job = get_hive().create_job(app.analysis, request.json)
        except ValueError as e:
            raise HTTPRequestError(str(e), 404)
        results = {"job_id": job.job_id}
        email = request.json.get('email')
        email_notification = request.json.get('email_notification')
        if email != None and email != '' and email_notification != None:
            app.logger.debug('Submitting email request for %s', email)
            email_results = email_when_complete.delay(request.url_root + "jobs/" + str(job.job_id) + "?format=email",
                                                      email)
            results['email_task'] = email_results.id
        return jsonify(results), 201
    else:
        app.logger.error('Could not handle input of type %s', request.headers['Content-Type'])
        raise HTTPRequestError('Could not handle input of type %s' % request.headers['Content-Type'])


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
        description: Result of a metadata job
        schema:
          $ref: '#/definitions/job_id'
        examples:
          id: 1
          input:
            metadata_uri: mysql://user:password@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
            timestamp: 1515494114.263158
          output:
            runtime: 31 seconds
            metadata_uri: mysql://user:password@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
          status: complete
    """
    fmt = request.args.get('format')
    app.logger.debug('Format %s', fmt)
    if fmt == 'email':
        email = request.args.get('email')
        return job_email(email, job_id)
    elif fmt == 'failures':
        return failure(job_id)
    elif fmt is None:
        app.logger.info('Retrieving job with ID %s', job_id)
        try:
            job_result = get_hive().get_result_for_job_id(job_id, child=True)
        except ValueError as e:
            raise HTTPRequestError(str(e), 404)
        return jsonify(job_result)
    else:
        raise HTTPRequestError("Format " + fmt + " not valid")


def job_email(email, job_id):
    app.logger.info('Retrieving job with ID %s for %s', job_id, email)
    try:
        job = get_hive().get_job_by_id(job_id)
        results = get_hive().get_result_for_job_id(job_id, child=True)
        if results['status'] == 'complete':
            results['subject'] = 'Metadata load for database %s is successful' % (results['output']['database_uri'])
            results['body'] = "Metadata load for database %s is successful\n" % (results['output']['database_uri'])
            results['body'] += "Load took %s" % (results['output']['runtime'])
        elif results['status'] == 'failed':
            failure = get_hive().get_job_failure_msg_by_id(job_id, child=True)
            results['subject'] = 'Metadata load for %s failed' % (results['input']['database_uri'])
            results['body'] = 'Metadata load failed with following message:\n'
            results['body'] += '%s' % (failure.msg)
    except ValueError as e:
        raise HTTPRequestError(str(e), 404)
    results['output'] = None
    return jsonify(results)


def failure(job_id):
    """
    Endpoint to retrieve a given job failure using job_id
    This is using docstring for specifications
    ---
    tags:
      - failure
    parameters:
      - name: job_id
        in: path
        type: integer
        required: true
        default: 13
        description: id of the job
    operationId: failure
    consumes:
      - application/json
    produces:
      - application/json
    security:
      failure_auth:
        - 'write:failure'
        - 'read:failure'
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
      failure:
        type: object
        properties:
          failure:
            type: string
            items:
              $ref: '#/definitions/failure'
    responses:
      200:
        description: Retrieve failure of a given job using job_id
        schema:
          $ref: '#/definitions/job_id'
        examples:
          msg: 'Missing table meta in database'
    """
    app.logger.info('Retrieving failure for job with ID %s', job_id)
    try:
        failure = get_hive().get_job_failure_msg_by_id(job_id, child=True)
    except ValueError as e:
        raise HTTPRequestError(str(e), 404)
    return jsonify({"msg": failure.msg})


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
    try:
        job = get_hive().get_job_by_id(job_id)
        hive.delete_job(job, child=True)
    except ValueError as e:
        raise HTTPRequestError(str(e), 404)
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
            metadata_uri: mysql://user@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
            timestamp: 1515494114.263158
          output:
            runtime: 31 seconds
            metadata_uri: mysql://user@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
          status: complete
          id: 2
          input:
            email: john.doe@ebi.ac.uk
            metadata_uri: mysql://user@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
            timestamp: 1515494178.544427
          output:
            runtime: 31 seconds
            metadata_uri: mysql://user@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
          status: complete
          id: 3
          input:
            email: john.doe@ebi.ac.uk
            metadata_uri: mysql://user@server:port/ensembl_metadata
            database_uri: mysql://user:password@server:port/saccharomyces_cerevisiae_core_91_4
            timestamp: 1515602446.492586
          progress:
            complete: 0
            total: 1
          status: failed
    """
    app.logger.info('Retrieving jobs')
    return jsonify(get_hive().get_all_results(app.analysis, child=True))


@app.errorhandler(HTTPRequestError)
def handle_bad_request_error(e):
    app.logger.error(str(e))
    return jsonify(error=str(e)), e.status_code


if __name__ == "__main__":
    app.run(debug=True)
