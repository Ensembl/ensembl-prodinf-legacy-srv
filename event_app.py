#!/usr/bin/env python
from flask import Flask, request, jsonify
from flask_cors import CORS
import re
import json
from flasgger import Swagger

from ensembl_prodinf import reporting
from ensembl_prodinf import HiveInstance
from ensembl_prodinf.event_tasks import process_result
import event_config
import app_logging

pool = reporting.get_pool(event_config.report_server)

logger = reporting.get_logger(pool, event_config.report_exchange, 'event_handler', None, {})

app = Flask(__name__, instance_relative_config=True)
print app.config
app.config.from_object('event_config')
app.config.from_pyfile('event_config.py')
swagger = Swagger(app)
app.logger.addHandler(app_logging.file_handler(__name__))
app.logger.addHandler(app_logging.default_handler())

class EventNotFoundError(Exception):
    """Exception showing event not found"""        

print event_config.event_lookup
event_lookup = json.loads(open(event_config.event_lookup).read())


def get_processes_for_event(event):
    event_type = event['type']
    if event_type not in event_lookup.keys():
        raise EventNotFoundError("Event type " + str(event_type) + " not known")
    return event_lookup[event_type]    


class ProcessNotFoundError(Exception):
    """Exception showing process not found"""


process_lookup = json.loads(open(event_config.process_lookup).read())


def get_analysis(process):
    if process not in process_lookup.keys():
        raise ProcessNotFoundError("Process " + str(process) + " not known")
    return process_lookup[process]['analysis']

hives = {}


def get_hive(process):    
    if process not in hives.keys():
        if process not in process_lookup.keys():
            raise ProcessNotFoundError("Process " + str(process) + " not known")
        hives[process] = HiveInstance(process_lookup[process]['hive_uri'])
    return hives[process]


cors = CORS(app)

# use re to support different charsets
json_pattern = re.compile("application/json")

@app.route('/jobs', methods=['POST'])
def submit_job():
    """
    Endpoint to submit an event to process
    ---
    tags:
      - jobs
    parameters:
      - in: body
        name: body
        description: event
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
    """
    if json_pattern.match(request.headers['Content-Type']):
        event = request.json
        results = {"processes":[], "event":event}
        # convert event to processes
        processes = get_processes_for_event(event)
        for process in processes:
            logger.debug("Submitting process " + str(process))
            hive = get_hive(process)
            analysis = get_analysis(process)
            job = hive.create_job(analysis, {'event':event})
            event_task = process_result.delay(event, process, job.job_id)
            results['processes'].append({
                "process":process,
                "job_id":job.job_id,
                "task":event_task.id
            })
        return jsonify(results);
    else:
        raise ValueError("Could not handle input of type " + request.headers['Content-Type'])


@app.route('/jobs/<string:process>/<int:job_id>', methods=['GET'])
def job(process, job_id):
    """
    Endpoint to retrieve a given job result for a process and job id
    ---
    tags:
      - jobs
    parameters:
      - name: process
        in: path
        type: string
        required: true
        default: 1
        description: process name
      - name: job_id
        in: path
        type: integer
        required: true
        default: 1
        description: id of the job
    operationId: jobs
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
        description: Result of an event job
        schema:
          $ref: '#/definitions/job_id'
    """    
    output_format = request.args.get('format')
    if output_format == 'email':
        email = request.args.get('email')
        if email is None:
            raise ValueError("Email not specified")
        return results_email(request.args.get('email'), process, job_id)
    elif output_format == None:
        return results(process, job_id)
    else:
        raise ValueError("Format "+output_format+" not known")
        
def results(process, job_id):    
    logger.info("Retrieving job from " + process + " with ID " + str(job_id))
    return jsonify(get_hive(process).get_result_for_job_id(job_id))


@app.route('/jobs/<string:process>/<int:job_id>', methods=['DELETE'])
def delete_job(process, job_id):
    """
    Endpoint to delete a given job result using job_id
    ---
    tags:
      - jobs
    parameters:
      - name: process
        in: path
        type: string
        required: true
        default: 1
        description: process name
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
    hive = get_hive(process)
    job = hive.get_job_by_id(job_id)
    hive.delete_job(job)
    return jsonify({"id":job_id, "process": process})

def results_email(email, process, job_id):
    logger.info("Retrieving job with ID " + str(job_id) + " for " + str(email))
    hive = get_hive(process)
    job = hive.get_job_by_id(job_id)
    results = hive.get_result_for_job_id(job_id)
    # TODO
    results['email'] = email
    return jsonify(results)

@app.route('/jobs/<string:process>', methods=['GET'])
def jobs(process):
    """
    Endpoint to retrieve all the jobs results from the database
    ---
    tags:
      - jobs
    parameters:
      - name: process
        in: path
        type: string
        required: true
        default: 1
        description: process name
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
    """ 
    logger.info("Retrieving jobs")
    return jsonify(get_hive(process).get_all_results(get_analysis(process)))


@app.route('/events')
def events():
    """
    Endpoint to retrieve all known event types
    ---
    tags:
      - events
    operationId: events
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
        description: Retrieve all the events
    """     
    return jsonify(event_lookup.keys()) 

@app.route('/processes')
def processes():
    """
    Endpoint to retrieve all known processes handled
    ---
    tags:
      - processes
    operationId: processes
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
        description: Retrieve all the processes
    """     
    return jsonify(process_lookup.keys()) 

@app.errorhandler(Exception)
def handle_error(e):
    code = 500
    if isinstance(e, ValueError):
        code = 400
    logger.exception(str(e))
    return jsonify(error=str(e)), code

if __name__ == "__main__":
    app.run(debug=True)
