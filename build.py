import glob
import os
import platform
import sys

from fabric.api import run, env, settings, put
from pybuilder.core import use_plugin, init, task, Author
import itertools

# plugins
use_plugin('python.distutils')
use_plugin('python.core')
use_plugin('python.install_dependencies')

#use_plugin('python.flake8')
#use_plugin('pybuilder_pytest')

# pybuilder_pytest runs even without a task
# pybuilder is currently broken on windows / py27 / sphinx plugin combination
if 'windows' not in platform.system().lower() or sys.version_info.major == 3:
    use_plugin('python.sphinx')
    default_task = ['install_dependencies',
 #p                   'analyze',
                    'sphinx_generate_documentation',
                    'publish']
else:
    default_task = ['install_dependencies',
#                    'analyze',
                    'sphinx_build',
                    'publish']

# project meta
name = 'visual_behavior'
version = '0.1.1'
summary = 'Prototype UI / Stage Hardware api'
description = __doc__
authors = (Author('Ross Hytnen', 'rossh@alleninstitute.org'),)
url = 'http://stash.corp.alleninstitute.org/scm/~rossh/visual_behavior'


@task(description='sphinx 27 workaround')
def sphinx_build():
    os.chdir('docs')
    os.system('make.bat html')
    os.chdir('..')

@task(description='deploy project to aibspi')
def deploy():
    """
    Pushes the most recent package and documentation to the aibspi server.

    """
    env.host_string = 'aibspi'
    env.user = 'aibspi'
    env.password = 'aibspi'

    local_path = 'dist/{}-{}/dist/*'.format(name, version)
    package_path = 'python_index/{}/'.format(name)
    with settings(warn_only=True):
        run('mkdir {}'.format(package_path))
    put(local_path, package_path)

    local_path = 'docs/_build/html/*'
    package_path = 'python_index/docs/{}-{}/'.format(name, version)
    with settings(warn_only=True):
        run('mkdir -p {}'.format(package_path))
    put(local_path, package_path)


@init(environments='deploy')
def initialize_deploy(logger):
    """
    Causes the deploy task to run after the default tasks.
    :param logger: PyBuilder Logger
    """
    deploy(logger)


@init
def initialize(project):
    project.set_property('verbose', True)

    # modules / di  st
    project.set_property('dir_source_main_python', 'src')
    project.set_property('dir_source_main_scripts', 'scripts')
    project.set_property('dir_dist', 'dist/{0}-{1}'.format(name, version))

    # testing
    project.set_property('dir_source_pytest_python', "tests")

    # documentation
    project.set_property('dir_docs', 'docs')
    project.set_property('sphinx_config_path', 'docs/')
    project.set_property('sphinx_source_dir', 'docs/')
    project.set_property('sphinx_output_dir', 'docs/_build/html')
    project.set_property('sphinx_builder', 'html')

    # linting
    project.set_property('flake8_break_build', False)
    project.set_property('flake8_include_scripts', True)
    project.set_property('flake8_include_test_sources', True)

    # dependencies
    project.build_depends_on_requirements('requirements_dev.txt')
    project.depends_on_requirements('requirements.txt')

    # entry points (typically the .py files in visual_behavior
    project.set_property('distutils_entry_points',
                         {'console_scripts': [
                             'stage_controller=stage_control:main']})

    resource_patterns = ['yaml', 'yml', 'png', 'jpeg', 'jpeg', 'ui', 'json', 'ico']
    for directory, subdirectory, files in os.walk('src/visual_behavior'):
        directory = directory.replace('src/visual_behavior\\', '').replace('\\', '/')
        for file, pattern in itertools.product(files, resource_patterns):
            if pattern in file.lower():
                project.include_file('visual_behavior', directory + '/' + file)
