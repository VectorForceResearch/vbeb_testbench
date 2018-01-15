from aibsmw import ZROHost, RemoteObjectService
from visual_behavior import nidaqio, source_project_configuration, init_log
import argparse
import logging


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', help='port to run the remote service on', type=int)
    args = parser.parse_args()

    init_log(override_local=False)
    config = source_project_configuration('visual_behavior_v1.yml', override_local=False)

    port = args.port or config.nidaq.port
    host = ZROHost(nidaqio.NIDAQio())
    host.add_service(RemoteObjectService, service_host=('*', port))

    logging.info(f'Starting NIDAQ Remote Object service on port {port}')
    host.start()


if __name__ == '__main__':
    main()
