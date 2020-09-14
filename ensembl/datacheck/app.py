import os
import re
import time
from flask import Flask, json, jsonify, redirect, render_template, request, send_file
from flask_bootstrap import Bootstrap
from flask_cors import CORS
from flasgger import Swagger
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path

from ensembl.datacheck.config import DatacheckConfig
from ensembl.forms import DatacheckSubmissionForm
from ensembl.hive import HiveInstance
from ensembl.db_utils import get_databases_list, get_db_type
from ensembl.server_utils import assert_mysql_uri, assert_mysql_db_uri

# Go up two levels to get to root, where we will find the static and template files
app_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
static_path = os.path.join(app_path, 'static')
template_path = os.path.join(app_path, 'templates')

app = Flask(__name__, static_url_path='', static_folder=static_path, template_folder=template_path)

app.config.from_object(DatacheckConfig)

Bootstrap(app)

CORS(app)

Swagger(app, template_file='swagger.yml')

app.analysis = app.config['HIVE_ANALYSIS']
app.index = json.load(open(app.config['DATACHECK_INDEX']))
app.server_names = json.load(open(os.path.join(app_path, app.config['SERVER_NAMES_FILE'])))

app.names_list = []
app.groups_list = []
app.servers_list = []
app.servers_dict = {}


def get_names_list():
    if not app.names_list:
        for name, params in app.index.items():
            app.names_list.append(name)
        app.names_list.sort()
    return app.names_list


def get_groups_list():
    if not app.groups_list:
        groups_set = []
        for name, params in app.index.items():
            for group in params['groups']:
                groups_set.append(group)
        app.groups_list = sorted(set(groups_set))
    return app.groups_list


def get_servers_list():
    if not app.servers_list:
        app.servers_list = sorted(set(app.server_names))
    return app.servers_list


def get_servers_dict():
    if not app.servers_dict:
        app.servers_dict = app.server_names
    return app.servers_dict


hive = None


def get_hive():
    global hive
    if hive is None:
        hive = HiveInstance(app.config['HIVE_URI'])
    return hive


@app.route('/datacheck/', methods=['GET'])
def index():
    # Missing template
    # return render_template('ensembl/datacheck/index.html')
    return jsonify({'title': 'Datacheck REST endpoints', 'uiversion': 2})


@app.route('/datacheck/servers/list', methods=['GET'])
def servers_list():
    return jsonify(get_servers_list())


@app.route('/datacheck/servers/dict', methods=['GET'])
def servers_dict():
    return jsonify(get_servers_dict())


@app.route('/datacheck/databases/list', methods=['GET'])
def databases_list():
    db_uri = request.args.get('db_uri')
    query = request.args.get('query')
    return jsonify(get_databases_list(db_uri, query))


@app.route('/datacheck/names/', methods=['GET'])
@app.route('/datacheck/names/<string:name_param>', methods=['GET'])
def names(name_param=None):
    if name_param is None:
        index_names = app.index
    else:
        index_names = {}
        for name, params in app.index.items():
            if name == name_param:
                index_names.setdefault(name, []).append(params)

    if request.is_json:
        return jsonify(index_names)
    else:
        return render_template(
            'ensembl/datacheck/names.html',
            datachecks=index_names
        )


@app.route('/datacheck/names/list', methods=['GET'])
def names_list():
    return jsonify(get_names_list())


@app.route('/datacheck/groups/', methods=['GET'])
@app.route('/datacheck/groups/<string:group_param>', methods=['GET'])
def groups(group_param=None):
    index_groups = {}
    for name, params in app.index.items():
        for group in params['groups']:
            if group_param is None or group == group_param:
                index_groups.setdefault(group, []).append(params)

    if request.is_json:
        return jsonify(index_groups)
    else:
        return render_template(
            'ensembl/datacheck/groups.html',
            datachecks=index_groups
        )


@app.route('/datacheck/groups/list', methods=['GET'])
def groups_list():
    return jsonify(get_groups_list())


@app.route('/datacheck/types/', methods=['GET'])
@app.route('/datacheck/types/<string:type_param>', methods=['GET'])
def types(type_param=None):
    index_types = {}
    for name, params in app.index.items():
        if type_param is None or params['datacheck_type'] == type_param:
            index_types.setdefault(params['datacheck_type'], []).append(params)

    if request.is_json:
        return jsonify(index_types)
    else:
        return render_template(
            'ensembl/datacheck/types.html',
            datachecks=index_types
        )


@app.route('/datacheck/search/<string:keyword>', methods=['GET'])
def search(keyword):
    index_search = {}
    keyword_re = re.compile(keyword, re.IGNORECASE)

    for name, params in app.index.items():
        if keyword_re.search(name) or keyword_re.search(params['description']):
            index_search.setdefault(keyword, []).append(params)

    return jsonify(index_search)


@app.route('/datacheck/jobs', methods=['POST'])
def job_submit(payload=None):
    # Most of the parameters that are in the payload can be pushed straight
    # through to the input_data for the hive submission. The parameter names
    # have been made to match up nicely. However, there are a few input
    # parameters that need to be derived from the payload ones.
    if payload is None:
        payload = request.json

    input_data = dict(payload)

    assert_mysql_uri(input_data['server_url'])

    # Determine db_type if necessary.
    # Convert all species-selection parameters to lists, as required by the hive pipeline
    dbname = input_data['dbname']
    if dbname is not None:
        db_uri = input_data['server_url'] + dbname
        assert_mysql_db_uri(db_uri)
        input_data['db_type'] = set_db_type(dbname, db_uri)
        input_data['dbname'] = dbname.split(',')
    elif input_data['species'] is not None:
        input_data['species'] = input_data['species'].split(',')
    elif input_data['division'] is not None:
        input_data['division'] = input_data['division'].split(',')

    # Hard-code this for the time being; need to handle memory usage better for unparallelised runs
    input_data['parallelize_datachecks'] = 1

    servers = get_servers_dict()
    server_name = servers[input_data['server_url']]['server_name']
    config_profile = servers[input_data['server_url']]['config_profile']
    db_category = input_data['db_type']
    if dbname is not None:
        if is_grch37(dbname):
            config_profile = 'grch37'
            if db_category != 'core':
                db_category = 'grch37'

    input_data['registry_file'] = set_registry_file(db_category, server_name)

    input_data['config_file'] = set_config_file(config_profile)

    job = get_hive().create_job(app.analysis, input_data)

    if request.is_json:
        results = {"job_id": job.job_id}
        return jsonify(results), 201
    else:
        return redirect('/datacheck/jobs/' + str(job.job_id))


@app.route('/datacheck/jobs', methods=['GET'])
def job_list():
    jobs = get_hive().get_all_results(app.analysis)

    # Handle case where submission is marked as complete,
    # but where output has not been created.
    for job in jobs:
        if 'output' not in job.keys():
            job['status'] = 'incomplete'
        elif job['output']['failed_total'] > 0:
            job['status'] = 'failed'

    # if request.is_json:
    return jsonify(jobs)
    # else:
    # Need to pass some data to the template...
    # return render_template('ensembl/datacheck/list.html')


@app.route('/datacheck/jobs/<int:job_id>', methods=['GET'])
def job_result(job_id):
    job = get_hive().get_result_for_job_id(job_id, progress=False)

    # Handle case where submission is marked as complete,
    # but where output has not been created.
    if 'output' not in job.keys():
        job['status'] = 'incomplete'
    elif job['output']['failed_total'] > 0:
        job['status'] = 'failed'
    elif job['output']['passed_total'] == 0:
        job['status'] = 'failed'

    # if request.is_json:
    return jsonify(job)
    # else:
    # Need to pass some data to the template...
    # return render_template('ensembl/datacheck/detail.html')


@app.route('/datacheck/download_datacheck_outputs/<int:job_id>')
def download_dc_outputs(job_id):
    job = get_hive().get_result_for_job_id(job_id, progress=False)
    if 'output' in job:
        base_path = Path(job['output']['output_dir'])
        paths = list(base_path.iterdir())
        if len(paths) > 1:
            data = BytesIO()
            with ZipFile(data, mode='w') as z:
                for f_path in paths:
                    z.write(str(f_path), f_path.name)
            data.seek(0)
            filename = 'Datacheck_output_job_%s.zip' % job_id
            return send_file(data, mimetype='application/zip',
                             attachment_filename=filename, as_attachment=True)
        else:
            for f_path in paths:
                return send_file(str(f_path), as_attachment=True)


@app.route('/datacheck/submit', methods=['GET'])
def display_form():
    form = DatacheckSubmissionForm(request.form)

    server_name_choices = [('', '')]
    server_name_dict = {}

    for i, j in get_servers_dict().items():
        server_name_dict[j['server_name']] = i

    for name in sorted(server_name_dict):
        server_name_choices.append((server_name_dict[name], name))

    form.server.server_name.choices = server_name_choices

    return render_template(
        'ensembl/datacheck/submit.html',
        form=form
    )


@app.route('/datacheck/submit', methods=['POST'])
def submit_form():
    # Here we convert the form fields into a 'payload' dictionary
    # that is the required input format for the hive submission.

    form = DatacheckSubmissionForm(request.form)

    payload = {
        'server_url': form.server.server_name.data,
        'dbname': None,
        'species': None,
        'division': None,
        'db_type': None,
        'datacheck_names': [],
        'datacheck_groups': [],
        'datacheck_types': [],
        'email': form.submitter.email.data,
        'tag': form.submitter.tag.data
    }

    if form.server.source.data == 'dbname':
        payload['dbname'] = form.server.dbname.data
    else:
        if form.server.source.data == 'species':
            payload['species'] = form.server.species.data
        elif form.server.source.data == 'division':
            payload['division'] = form.server.division.data

        payload['db_type'] = form.server.db_type.data

    if form.datacheck.datacheck_name.data != '':
        payload['datacheck_names'] = form.datacheck.datacheck_name.data.split(',')
    if form.datacheck.datacheck_group.data != '':
        payload['datacheck_groups'] = form.datacheck.datacheck_group.data.split(',')
    if form.datacheck.datacheck_type.data != '':
        payload['datacheck_types'] = form.datacheck.datacheck_type.data.split(',')

    return job_submit(payload)


@app.route('/datacheck/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'ok'})


def set_db_type(dbname, db_uri):
    p = re.compile('cdna|otherfeatures|rnaseq')
    m = p.search(dbname)
    if m is not None:
        db_type = m.group()
    else:
        db_type = get_db_type(db_uri)
    return db_type


def set_registry_file(db_category, server_name):
    return os.path.join(app.config['DATACHECK_REGISTRY_DIR'], db_category, '.'.join([server_name, 'pm']))


def set_config_file(config_profile):
    return os.path.join(app.config['DATACHECK_CONFIG_DIR'], '.'.join([config_profile, 'json']))


def is_grch37(dbname):
    p = re.compile('homo_sapiens.*_37')
    return p.match(dbname)
