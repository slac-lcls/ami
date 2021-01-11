#!/usr/bin/env python
import tables
import argparse


parser = argparse.ArgumentParser(description='Trucncate hdf files.')
parser.add_argument('src', help='Source file.')
parser.add_argument('dst', help='Destination file.')
parser.add_argument('--start', dest='start', type=int, default=0, help='Start event number.')
parser.add_argument('stop', type=int, help="Stop event number.")


def shrink(src, dst, start, stop):
    src = tables.open_file(src, mode='r')
    dst = tables.open_file(dst, mode='w')

    for arr in src.walk_nodes("/", "Array"):
        path = arr._v_pathname
        path = path.split('/')
        name = path[-1]
        path = '/'.join(path[:-1])
        if not path:
            path = '/'
        dst.create_array(path, name, obj=arr[slice(start, stop)], createparents=True)

    print(f"Writing to {dst}")
    dst.flush()
    dst.close()
    src.close()


if __name__ == '__main__':
    args = parser.parse_args()
    shrink(args.src, args.dst, args.start, args.stop)
