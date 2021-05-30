import os
import sys
import glob
import logging
import argparse
import tempfile
import collections
from ami import LogConfig, Defaults
from ami.comm import BasePort, Ports
from ami.client import flowchart, legacy


logger = logging.getLogger(__name__)


GraphMgrAddress = collections.namedtuple('GraphMgrAddress', ['name', 'comm', 'view', 'info'])


def run_client(graph_name, comm_addr, info_addr, view_addr, load,
               use_legacy=True, prometheus_dir=None, prometheus_port=None, hutch='', use_opengl=False,
               configure=False):
    graphmgr_addr = GraphMgrAddress(graph_name, comm_addr, view_addr, info_addr)
    if use_legacy:
        return legacy.run_client(graphmgr_addr, load)
    else:
        return flowchart.run_client(graphmgr_addr, load, prometheus_dir, prometheus_port, hutch, use_opengl,
                                    configure)


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
    )

    addr_group = parser.add_mutually_exclusive_group()

    addr_group.add_argument(
        '-p',
        '--port',
        type=int,
        default=BasePort,
        help='base port for ami (default: %d) reserves next 10 consecutive ports' % BasePort
    )

    addr_group.add_argument(
        '-i',
        '--ipc-dir',
        help='directory containing the ipc file descriptor for manager/client (GUI) communication'
    )

    addr_group.add_argument(
        '--ipc',
        action='store_true',
        help='attempt to search for ipc file descriptors for manager/client (GUI) communication'
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used (default: %s)' % Defaults.GraphName
    )

    parser.add_argument(
        '--prometheus-port',
        type=int,
        default=Ports.Prometheus,
        help='port for prometheus'
    )

    parser.add_argument(
        '--prometheus-dir',
        help='directory for prometheus configuration',
        default=None
    )

    parser.add_argument(
        '--hutch',
        help='hutch for prometheus label',
        default=''
    )

    parser.add_argument(
        '-l',
        '--load',
        help='saved AMII configuration to load'
    )

    guimode_parser = parser.add_mutually_exclusive_group()

    guimode_parser.add_argument(
        '--legacy-gui',
        dest='gui_mode',
        action='store_true',
        help="use the traditional AMI1-style GUI"
    )

    guimode_parser.add_argument(
        '--flowchart-gui',
        dest='gui_mode',
        action='store_false',
        help="use the new AMI2-style flowchart GUI"
    )

    parser.add_argument(
        '--log-level',
        default=LogConfig.Level,
        help='the logging level of the application (default %s)' % LogConfig.Level
    )

    parser.add_argument(
        '--log-file',
        help='an optional file to write the log output to'
    ),

    parser.add_argument(
        '--use-opengl',
        help='Use opengl for plots.',
        action='store_true'
    )

    args = parser.parse_args()

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    if args.ipc:
        ipc_comm_set = {os.path.dirname(ipc) for ipc in glob.glob(tempfile.gettempdir() + '/*/comm')}
        ipc_info_set = {os.path.dirname(ipc) for ipc in glob.glob(tempfile.gettempdir() + '/*/info')}
        ipc_list = list(ipc_comm_set.intersection(ipc_info_set))
        if ipc_list and ipc_list:
            if len(ipc_list) == 1:
                comm_addr = "ipc://%s/comm" % ipc_list[0]
                info_addr = "ipc://%s/info" % ipc_list[0]
                view_addr = "ipc://%s/view" % ipc_list[0]
            else:
                prompt = "Found %d ipc file descriptors:\n" % len(ipc_list)
                for i, ipc_name in enumerate(ipc_list):
                    prompt += " %d - %s\n" % (i, ipc_name)
                prompt += " %d - Quit\n\nPlease choose one: " % len(ipc_list)
                choice = input(prompt)
                try:
                    comm_addr = "ipc://%s/comm" % ipc_list[int(choice)]
                    info_addr = "ipc://%s/info" % ipc_list[int(choice)]
                    view_addr = "ipc://%s/view" % ipc_list[int(choice)]
                except ValueError:
                    logger.critical("Invalid option '%s' chosen!", choice)
                    return 1
                except IndexError:
                    logger.debug("Option chosen is outside range of ipc list - assume quit!")
                    return 0
        else:
            logger.critical("No manager ipc file descriptors found!")
            return 1
    elif args.ipc_dir is not None:
        comm_addr = "ipc://%s/comm" % args.ipc_dir
        info_addr = "ipc://%s/info" % args.ipc_dir
        view_addr = "ipc://%s/view" % args.ipc_dir
    else:
        comm_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Comm)
        info_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Info)
        view_addr = "tcp://%s:%d" % (args.host, args.port + Ports.View)

    try:
        return run_client(args.graph_name, comm_addr, info_addr, view_addr, args.load,
                          args.gui_mode, args.prometheus_dir, args.prometheus_port, args.hutch, args.use_opengl,
                          False)
    except KeyboardInterrupt:
        logger.info("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
