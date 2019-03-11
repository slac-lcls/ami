import sys
import glob
import logging
import argparse
from ami import LogConfig
from ami.comm import Ports
from ami.client import flowchart, legacy


logger = logging.getLogger(__name__)


def run_client(addr, load, use_legacy=True):
    if use_legacy:
        return legacy.run_client(addr, load)
    else:
        return flowchart.run_client(addr, load)


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: 127.0.0.1)'
    )

    addr_group = parser.add_mutually_exclusive_group()

    addr_group.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='port for manager/client (GUI) communication (default: %d)' % Ports.Comm
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
    )

    args = parser.parse_args()

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    if args.ipc:
        ipc_list = glob.glob('/tmp/*/comm')
        if ipc_list:
            if len(ipc_list) == 1:
                addr = "ipc://%s" % ipc_list[0]
            else:
                prompt = "Found %d ipc file descriptors:\n" % len(ipc_list)
                for i, ipc_name in enumerate(ipc_list):
                    prompt += " %d - %s\n" % (i, ipc_name)
                prompt += " %d - Quit\n\nPlease choose one: " % len(ipc_list)
                choice = input(prompt)
                try:
                    addr = "ipc://%s" % ipc_list[int(choice)]
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
        addr = "ipc://%s/comm" % args.ipc_addr
    else:
        addr = "tcp://%s:%d" % (args.host, args.port)

    try:
        return run_client(addr, args.load, args.gui_mode)
    except KeyboardInterrupt:
        logger.info("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
