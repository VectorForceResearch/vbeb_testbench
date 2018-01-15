# -*- coding: utf-8 -*-

import datetime
import logging.config
import os
import shutil
import sys
from collections import namedtuple

import yaml

__author__ = """Ross Hytnen"""
__email__ = 'rossh@alleninstitute.org'
__version__ = '0.2.1'

if sys.version_info.major == 2:
    class FileNotFoundError(Exception):
        pass

from .exceptions import InitializationError, InvalidCoordinatesError
from .stage import Stage, PhidgetStage, MockStage

def init_log(log_config_file=None, override_local=False):
    """
    Standard log initialization boiler plate that attempts to find a configuration file
    from the log_config_file variable, then the LOG_CONFIG_FILE environment variable. If
    neither file exists, it sets a basic DEBUG  console logger as the default.

    If the log is initialized at the __main__ level, all modules using logging downstream
    will pick up this configuration.

    :param log_config_file: The filename of a yaml based log configuration file.
    :param override_local: If True (default) cloud configurations that are different are downloaded and cached locally.
    """
    if log_config_file is None:
        log_config_file = 'log_config_v1.yml'

    config = source_project_configuration(log_config_file, override_local=override_local, as_dict=True)
    if config is None:
        logging.basicConfig(level=logging.DEBUG)
        logging.info('could not find {}.  Using default configuration.'.format(log_config_file))
        return

    config['handlers']['file_handler']['filename'] = sys.argv[0] + '.log'
    config['handlers']['debug_file_handler']['filename'] = sys.argv[0] + '_debug.log'
    logging.config.dictConfig(config)


def parse_config(configuration_file):
    """
    FileExists and YAML checking boilerplate
    :param configuration_file:
    :return:
    """
    try:
        with open(configuration_file) as f:
            return yaml.safe_load(f)
    except FileNotFoundError as err:
        logging.info('configuration not found: {}: {}'.format(configuration_file, err))
        return None


def cache_remote_config(configuration_file):
    """
    Creates a back up of the local configuration and copies the remote configuration into the project path
    :param configuration_file:
    :return:
    """
    local_path = '{}/resources/{}'.format(__path__[0], configuration_file)
    remote_path = '{}/{}'.format(os.getenv("MPE_CONFIGURATION_PATH", "//allen/aibs/mpe/Rigs/configuration"),
                                 configuration_file)

    logging.info('caching remote configuration')
    if os.path.exists(local_path):
        timestamp = datetime.datetime.strftime(datetime.datetime.now(), '%y%m%d-%H%M%S')
        backup_file = '{}.{}.bck'.format(local_path, timestamp)
        logging.info('Copying previous configuration to {}'.format(backup_file))
        shutil.copyfile(local_path, backup_file)

    shutil.copyfile(remote_path, local_path)


def source_project_configuration(configuration_file, override_local=True, as_dict=False):
    """
    Find a project configuration file on the network, compare it to the local configuration and cache it.
    :param configuration_file:  Name of the configuration file
    :param override_local:  Default==True.  If true, overwrite the local configuration with the remote configuration /
    if the remote configuration is newer.  The old local configuration is copied to <configuration_file.yml.old>
    :param as_dict If true (default=false), configuration will return a dictionary instead of namedtuple.  This can be
    useful when a y aml configuration contains keywords like 'class' that would break namedtuple
    :return: A dict corresponding to the programs configuration file

    """
    local_path = '{}/resources/{}'.format(__path__[0], configuration_file)
    remote_path = '{}/{}'.format(os.getenv("MPE_CONFIGURATION_PATH", "//allen/aibs/mpe/Rigs/configuration"),
                                 configuration_file)

    local_config = parse_config(local_path)
    remote_config = parse_config(remote_path)

    if not local_config and not remote_config:
        raise FileNotFoundError('no valid configurations found.')

    if not remote_config or not override_local:
        logging.info('using local configuration: {}'.format(local_path))
        return dict_to_namedtuple(local_config) if not as_dict else local_config

    logging.info('using remote configuration: {}'.format(remote_path))
    if not local_config:
        cache_remote_config(configuration_file)
        return dict_to_namedtuple(remote_config) if not as_dict else remote_config

    local_modify_time = os.path.getmtime(local_path)
    remote_modify_time = os.path.getmtime(remote_path)
    if remote_modify_time > local_modify_time:
        cache_remote_config(configuration_file)

    return dict_to_namedtuple(remote_config) if not as_dict else remote_config


def dict_to_namedtuple(dictionary):
    for key, value in dictionary.items():
        if isinstance(value, dict):
            dictionary[key] = dict_to_namedtuple(value)
    return namedtuple('dotDict', dictionary.keys())(**dictionary)
