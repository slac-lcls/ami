#!/usr/bin/env python3
"""
Generate worker configuration for data sources from .fc file.

This script extracts source nodes from a .fc flowchart file and generates
a worker configuration file that can be used with ami-local to test
the flowchart with mock data (static or random).

Usage:
    ami-fc-to-source <fc_file> [options]

Examples:
    # Generate worker.json from .fc file (random source by default)
    ami-fc-to-source tests/graphs/ATM_crix_new.fc
    
    # Specify custom output file and event count
    ami-fc-to-source my_graph.fc -o my_worker.json -n 100
    
    # Generate for static source
    ami-fc-to-source my_graph.fc --source-type static
    
    # Then use with ami-local
    ami-local -n 3 random://worker.json -l my_graph.fc
"""

import json
import argparse
import sys
from pathlib import Path


def extract_sources_from_fc(fc_path):
    """
    Parse .fc file and extract source node configurations.
    
    Args:
        fc_path: Path to .fc file
        
    Returns:
        dict: Source configurations for worker.json
    """
    with open(fc_path, 'r') as f:
        data = json.load(f)
    
    sources = {}
    for node in data.get('nodes', []):
        if node.get('class') == 'SourceNode':
            name = node['name']
            terminals = node.get('state', {}).get('terminals', {})
            if 'Out' in terminals:
                ttype = terminals['Out'].get('ttype', '')
                sources[name] = map_amitypes_to_config(ttype)
    
    return sources


def map_amitypes_to_config(ttype):
    """
    Map amitypes type string to static source config.
    
    Args:
        ttype: String like "amitypes.Array2d" or "amitypes.array.Array2d"
        
    Returns:
        dict: Config for static data source
    """
    # Default config
    default = {"dtype": "Scalar", "range": [0, 100]}
    
    if not ttype:
        return default
    
    # Extract base type (handle both amitypes.Array2d and amitypes.array.Array2d)
    if 'Array2d' in ttype:
        return {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]}
    elif 'Array1d' in ttype:
        return {"dtype": "Waveform", "length": 1024}
    elif 'Array3d' in ttype:
        return {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [100, 512, 512]}
    elif 'int' in ttype.lower():
        return {"dtype": "Scalar", "range": [0, 100], "integer": True}
    elif 'float' in ttype.lower():
        return {"dtype": "Scalar", "range": [0.0, 100.0]}
    else:
        return default


def generate_worker_json(fc_path, num_events=100, repeat=True, interval=0.01, init_time=0.1, source_type='random'):
    """
    Generate worker configuration from .fc file.
    
    Args:
        fc_path: Path to .fc file
        num_events: Number of events to generate (default: 100)
        repeat: Whether to loop events (default: True)
        interval: Time between events in seconds (default: 0.01)
        init_time: Initial wait time in seconds (default: 0.1)
        source_type: Type of source - 'static' or 'random' (default: 'random')
        
    Returns:
        tuple: (source_type, worker_config_dict)
    """
    source_config = extract_sources_from_fc(fc_path)
    
    if not source_config:
        print(f"Warning: No source nodes found in {fc_path}", file=sys.stderr)
        print("The .fc file may not have any SourceNode entries.", file=sys.stderr)
    
    worker_json = {
        "interval": interval,
        "init_time": init_time,
        "bound": num_events,
        "repeat": repeat,
        "files": "data.xtc2",
        "config": source_config
    }
    
    return source_type, worker_json


def main():
    parser = argparse.ArgumentParser(
        description="Generate worker configuration for data sources from .fc file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate worker.json from .fc file (random source by default)
  %(prog)s tests/graphs/ATM_crix_new.fc
  
  # Custom output file and event count
  %(prog)s my_graph.fc -o my_worker.json -n 100
  
  # Generate for static source
  %(prog)s my_graph.fc --source-type static
  
  # Don't loop events (stop after bound)
  %(prog)s my_graph.fc --no-repeat
  
  # Then use with ami-local
  ami-local -n 3 random://worker.json -l my_graph.fc
        """
    )
    
    parser.add_argument(
        'fc_file',
        type=str,
        help='Path to .fc flowchart file'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='worker.json',
        help='Output worker.json file (default: worker.json)'
    )
    
    parser.add_argument(
        '-n', '--num-events',
        type=int,
        default=100,
        help='Number of events to generate (default: 100)'
    )
    
    parser.add_argument(
        '--no-repeat',
        action='store_true',
        help='Do not loop events (stop after bound)'
    )
    
    parser.add_argument(
        '--interval',
        type=float,
        default=0.01,
        help='Time between events in seconds (default: 0.01)'
    )
    
    parser.add_argument(
        '--init-time',
        type=float,
        default=0.1,
        help='Initial wait time in seconds (default: 0.1)'
    )
    
    parser.add_argument(
        '--show-sources',
        action='store_true',
        help='Show detected sources and exit'
    )
    
    parser.add_argument(
        '--source-type',
        type=str,
        choices=['static', 'random'],
        default='random',
        help='Type of source to generate for (default: random). '
             'static: constant values (all 1s), random: randomized values based on ranges'
    )
    
    args = parser.parse_args()
    
    # Check if .fc file exists
    fc_path = Path(args.fc_file)
    if not fc_path.exists():
        print(f"Error: File not found: {args.fc_file}", file=sys.stderr)
        sys.exit(1)
    
    # Extract sources
    source_config = extract_sources_from_fc(fc_path)
    
    if not source_config:
        print(f"Error: No source nodes found in {args.fc_file}", file=sys.stderr)
        print("Make sure your .fc file has SourceNode entries.", file=sys.stderr)
        sys.exit(1)
    
    # Show sources if requested
    if args.show_sources:
        print(f"Sources detected in {args.fc_file}:")
        for name, config in source_config.items():
            dtype = config.get('dtype', 'unknown')
            print(f"  {name:30s} -> {dtype}")
        sys.exit(0)
    
    # Generate worker.json
    source_type, worker_json = generate_worker_json(
        fc_path,
        num_events=args.num_events,
        repeat=not args.no_repeat,
        interval=args.interval,
        init_time=args.init_time,
        source_type=args.source_type
    )
    
    # Write output
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        json.dump(worker_json, f, indent=2)
    
    # Print summary
    print(f"✓ Generated {args.output} (for {source_type} source)")
    print(f"  Sources detected: {len(source_config)}")
    for name, config in source_config.items():
        dtype = config.get('dtype', 'unknown')
        print(f"    - {name:30s} ({dtype})")
    print(f"  Events: {args.num_events}")
    print(f"  Repeat: {not args.no_repeat}")
    print()
    print("To use with ami-local:")
    print(f"  ami-local -n 3 {source_type}://{args.output} -l {args.fc_file}")


if __name__ == '__main__':
    main()
