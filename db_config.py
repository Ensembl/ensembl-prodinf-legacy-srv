import os
from ensembl_prodinf.config import load_config_yaml, parse_debug_var


config_file_path = os.environ.get('DBCOPY_CONFIG_PATH')
file_config = load_config_yaml(config_file_path)

debug_var = os.environ.get("DEBUG", file_config.get('debug', 'False'))

DEBUG = parse_debug_var(debug_var)

HIVE_ANALYSIS = os.environ.get("HIVE_ANALYSIS",
                               file_config.get('hive_analysis', 'copy_database'))

HIVE_URI = os.environ.get("HIVE_URI",
                          file_config.get('hive_uri'))

SERVER_URIS_FILE = os.environ.get("SERVER_URIS_FILE",
                                  file_config.get('server_uris_file', './server_uris.json'))

BLACKLISTED_STATUS_HOSTS = file_config.get('blacklisted_status_hosts', [])

DB_COPY_URI = os.environ.get("DB_COPY_URI",
                             file_config.get('db_copy_uri'))

DB_COPY_ADMIN = os.environ.get("DB_COPY_ADMIN",
                               file_config.get('db_copy_admin'))
