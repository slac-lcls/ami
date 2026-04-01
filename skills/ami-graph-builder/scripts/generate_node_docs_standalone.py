#!/usr/bin/env python3
"""
AMI Node Documentation Generator (Standalone Version)

Bypasses ami/__init__.py to avoid dependency issues.
Directly imports the library modules needed for documentation generation.
"""

import sys
import inspect
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add AMI to path
ami_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ami_root))

# Import library init directly, bypassing ami/__init__.py
import ami.flowchart.library as library_package

# Get LIBRARY from the library package
LIBRARY = library_package.LIBRARY

# Functional category definitions (optimized for agent semantic search)
FUNCTIONAL_CATEGORIES = {
    "Display & Visualization": {
        "description": "Nodes that visualize and display data (all self-displaying)",
        "keywords": [
            "plot",
            "graph",
            "chart",
            "visualize",
            "display",
            "show",
            "view",
            "histogram",
            "scatter",
            "image",
            "waveform",
        ],
        "nodes": [
            "ScatterPlot",
            "LinePlot",
            "Histogram",
            "ImageViewer",
            "WaveformPlot",
            "ScalarPlot",
        ],
    },
    "Data Processing": {
        "description": "Nodes that transform, bin, normalize, or compute on data",
        "keywords": [
            "bin",
            "binning",
            "normalize",
            "calculate",
            "compute",
            "project",
            "transform",
            "rebin",
            "downsample",
        ],
        "nodes": [
            "Binning",
            "Binning2D",
            "Calculator",
            "Normalizer",
            "Projection",
            "DownsampleImage",
        ],
    },
    "ROI (Region Selection)": {
        "description": "Nodes that select regions of interest from data",
        "keywords": [
            "roi",
            "region",
            "select",
            "mask",
            "crop",
            "area",
        ],
        "nodes": [
            "Roi0D",
            "Roi1D",
            "Roi2D",
        ],
    },
    "Statistics & Analysis": {
        "description": "Nodes that compute statistics and perform analysis",
        "keywords": [
            "statistics",
            "stats",
            "mean",
            "average",
            "std",
            "sum",
            "min",
            "max",
            "median",
            "analyze",
        ],
        "nodes": [
            "Statistics",
            "Mean",
            "Std",
            "Sum",
            "Average",
        ],
    },
    "Filtering & Logic": {
        "description": "Nodes that filter data based on conditions",
        "keywords": [
            "filter",
            "pick",
            "gate",
            "threshold",
            "select",
            "condition",
        ],
        "nodes": [
            "Filter",
            "Pick",
            "Gate",
            "Threshold",
        ],
    },
    "Scan Analysis": {
        "description": "Nodes for analyzing scans and control variables",
        "keywords": [
            "scan",
            "control",
            "step",
            "motor",
        ],
        "nodes": [
            "ScanPlot",
        ],
    },
    "Accumulators & Buffers": {
        "description": "Nodes that accumulate or buffer data over time",
        "keywords": [
            "accumulator",
            "accumulate",
            "buffer",
            "collect",
            "history",
        ],
        "nodes": [
            "Accumulator",
        ],
    },
    "Export": {
        "description": "Nodes that export data to external systems",
        "keywords": [
            "export",
            "output",
            "save",
            "server",
            "pv",
            "h5",
            "hdf5",
        ],
        "nodes": [
            "PvServer",
            "ImageServer",
            "H5Output",
        ],
    },
    "Advanced Processing": {
        "description": "Advanced signal processing and transformations",
        "keywords": [
            "fft",
            "correlator",
            "fourier",
            "frequency",
            "transform",
        ],
        "nodes": [
            "Fft",
            "Correlator",
        ],
    },
}


def categorize_node(node_name, node_class):
    """
    Categorize a node based on keywords and predefined lists.
    Returns category name or None if uncategorized.
    """
    # First check predefined node lists
    for category_name, category_info in FUNCTIONAL_CATEGORIES.items():
        if node_name in category_info["nodes"]:
            return category_name

    # Then check keywords
    node_name_lower = node_name.lower()
    for category_name, category_info in FUNCTIONAL_CATEGORIES.items():
        for keyword in category_info["keywords"]:
            if keyword.lower() in node_name_lower:
                return category_name

    return None


def extract_terminals(node_class):
    """
    Extract terminal information from a node class.
    Attempts instantiation with a dummy name to inspect terminals.
    """
    try:
        # Try to instantiate the node with a dummy name
        instance = node_class("_dummy_extract")

        terminals = {}
        if hasattr(instance, "terminals"):
            for term_name, term_obj in instance.terminals.items():
                term_info = {
                    "name": term_name,
                    "io": term_obj.isInput() and "input" or "output",
                    "optional": getattr(term_obj, "optional", False),
                    "multi": getattr(term_obj, "multi", False),
                }
                terminals[term_name] = term_info

        return terminals

    except Exception as e:
        # If instantiation fails, return empty dict
        return {}


def extract_parameters(node_class):
    """
    Extract parameter information from uiTemplate class attribute.
    """
    parameters = []

    if not hasattr(node_class, "uiTemplate"):
        return parameters

    ui_template = node_class.uiTemplate
    if not ui_template:
        return parameters

    # ui_template is a list of tuples: (param_name, param_type, [options])
    for item in ui_template:
        if len(item) >= 2:
            param_name = item[0]
            param_type = item[1]

            param_info = {
                "name": param_name,
                "type": param_type,
            }

            # Extract additional options if present
            if len(item) >= 3:
                options = item[2]
                if isinstance(options, dict):
                    param_info.update(options)

            parameters.append(param_info)

    return parameters


def get_node_module(node_class):
    """Get the module name where the node class is defined."""
    module = inspect.getmodule(node_class)
    if module:
        module_name = module.__name__
        # Extract just the last part (e.g., "Display" from "ami.flowchart.library.Display")
        if "." in module_name:
            return module_name.split(".")[-1]
        return module_name
    return "Unknown"


def generate_all_node_types_md(categorized_nodes, uncategorized_nodes, output_path):
    """Generate the all_node_types.md file organized by functional category."""

    lines = []
    lines.append("# AMI Node Types Reference")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(
        "**Organization:** By functional category (optimized for AI agent semantic search)"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of contents
    lines.append("## Table of Contents")
    lines.append("")
    for category_name in FUNCTIONAL_CATEGORIES.keys():
        anchor = (
            category_name.lower()
            .replace(" ", "-")
            .replace("&", "")
            .replace("(", "")
            .replace(")", "")
        )
        lines.append(f"- [{category_name}](#{anchor})")
    if uncategorized_nodes:
        lines.append(f"- [Uncategorized Nodes](#uncategorized-nodes)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Generate documentation for each category
    for category_name, category_info in FUNCTIONAL_CATEGORIES.items():
        nodes = categorized_nodes.get(category_name, [])

        if not nodes:
            continue  # Skip empty categories

        lines.append(f"## {category_name}")
        lines.append("")
        lines.append(f"**Description:** {category_info['description']}")
        lines.append("")

        for node_name, node_class, module_name, terminals, parameters in nodes:
            lines.append(f"### {node_name}")
            lines.append("")
            lines.append(f"**Module:** {module_name}")
            lines.append("")

            # Docstring
            docstring = inspect.getdoc(node_class)
            if docstring:
                lines.append(f"**Description:**")
                lines.append("")
                lines.append(docstring)
                lines.append("")

            # Terminals
            if terminals:
                lines.append("**Terminals:**")
                lines.append("")

                # Group by input/output
                inputs = {k: v for k, v in terminals.items() if v["io"] == "input"}
                outputs = {k: v for k, v in terminals.items() if v["io"] == "output"}

                if inputs:
                    lines.append("*Inputs:*")
                    for term_name, term_info in inputs.items():
                        optional_str = (
                            " (optional)" if term_info.get("optional") else ""
                        )
                        multi_str = " (multi)" if term_info.get("multi") else ""
                        lines.append(f"- `{term_name}`{optional_str}{multi_str}")
                    lines.append("")

                if outputs:
                    lines.append("*Outputs:*")
                    for term_name, term_info in outputs.items():
                        optional_str = (
                            " (optional)" if term_info.get("optional") else ""
                        )
                        multi_str = " (multi)" if term_info.get("multi") else ""
                        lines.append(f"- `{term_name}`{optional_str}{multi_str}")
                    lines.append("")

            # Parameters
            if parameters:
                lines.append("**Parameters:**")
                lines.append("")
                for param in parameters:
                    param_name = param["name"]
                    param_type = param["type"]
                    lines.append(f"- `{param_name}` ({param_type})")

                    # Add additional parameter info
                    for key, value in param.items():
                        if key not in ["name", "type"]:
                            lines.append(f"  - {key}: {value}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Uncategorized nodes
    if uncategorized_nodes:
        lines.append(f"## Uncategorized Nodes")
        lines.append("")
        lines.append("Nodes that don't fit into the defined functional categories.")
        lines.append("")

        for (
            node_name,
            node_class,
            module_name,
            terminals,
            parameters,
        ) in uncategorized_nodes:
            lines.append(f"### {node_name}")
            lines.append("")
            lines.append(f"**Module:** {module_name}")
            lines.append("")

            # Docstring
            docstring = inspect.getdoc(node_class)
            if docstring:
                lines.append(f"**Description:**")
                lines.append("")
                lines.append(docstring)
                lines.append("")

            # Terminals
            if terminals:
                lines.append("**Terminals:**")
                lines.append("")

                inputs = {k: v for k, v in terminals.items() if v["io"] == "input"}
                outputs = {k: v for k, v in terminals.items() if v["io"] == "output"}

                if inputs:
                    lines.append("*Inputs:*")
                    for term_name in inputs.keys():
                        lines.append(f"- `{term_name}`")
                    lines.append("")

                if outputs:
                    lines.append("*Outputs:*")
                    for term_name in outputs.keys():
                        lines.append(f"- `{term_name}`")
                    lines.append("")

            # Parameters
            if parameters:
                lines.append("**Parameters:**")
                lines.append("")
                for param in parameters:
                    lines.append(f"- `{param['name']}` ({param['type']})")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Write to file
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"✓ Generated: {output_path}")


def generate_terminals_quick_ref_md(
    categorized_nodes, uncategorized_nodes, output_path
):
    """Generate the terminals_quick_ref.md file."""

    lines = []
    lines.append("# AMI Node Terminals Quick Reference")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("Quick lookup table for node terminal names and connection patterns.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Build flat list of all nodes
    all_nodes = []
    for nodes in categorized_nodes.values():
        all_nodes.extend(nodes)
    all_nodes.extend(uncategorized_nodes)

    # Sort by node name
    all_nodes.sort(key=lambda x: x[0])

    lines.append("| Node | Input Terminals | Output Terminals |")
    lines.append("|------|-----------------|------------------|")

    for node_name, node_class, module_name, terminals, parameters in all_nodes:
        if not terminals:
            inputs_str = "-"
            outputs_str = "-"
        else:
            inputs = [k for k, v in terminals.items() if v["io"] == "input"]
            outputs = [k for k, v in terminals.items() if v["io"] == "output"]

            inputs_str = ", ".join(f"`{t}`" for t in inputs) if inputs else "-"
            outputs_str = ", ".join(f"`{t}`" for t in outputs) if outputs else "-"

        lines.append(f"| **{node_name}** | {inputs_str} | {outputs_str} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Common Terminal Patterns")
    lines.append("")
    lines.append("### Display Nodes")
    lines.append("- **ScatterPlot**: Inputs: `X`, `Y` (NEVER use `In` or `In.1`)")
    lines.append("- **LinePlot**: Inputs: `X`, `Y` for single trace")
    lines.append("- **Histogram**: Input: `Bins` (binned data from Binning node)")
    lines.append("- **ScalarPlot**: Input: `Y` (scalar values)")
    lines.append("")
    lines.append("### Processing Nodes")
    lines.append(
        "- **Binning**: Input: `Bins` (data to bin); Output: `Out` (NEVER use `XBins`)"
    )
    lines.append("- **Binning2D**: Inputs: `XBins`, `YBins` (2D binning)")
    lines.append("- **Calculator**: Input: `In`; Output: `Out`")
    lines.append("")
    lines.append("### ROI Nodes")
    lines.append("- **Roi0D**: Input: `In`; Output: `Out` (single value)")
    lines.append("- **Roi1D**: Input: `In`; Output: `Out` (1D region)")
    lines.append("- **Roi2D**: Input: `In`; Output: `Out` (2D region)")
    lines.append("")

    # Write to file
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"✓ Generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate AMI node documentation")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "references",
        help="Output directory for generated documentation",
    )
    args = parser.parse_args()

    # Create output directory if it doesn't exist
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Extracting node information from AMI library...")

    # Categorize nodes
    categorized_nodes = defaultdict(list)
    uncategorized_nodes = []

    for node_name, node_class in LIBRARY.items():
        # Skip base classes and non-node classes
        if node_name.startswith("_"):
            continue

        # Get module name
        module_name = get_node_module(node_class)

        # Extract terminals and parameters
        terminals = extract_terminals(node_class)
        parameters = extract_parameters(node_class)

        # Categorize
        category = categorize_node(node_name, node_class)

        node_info = (node_name, node_class, module_name, terminals, parameters)

        if category:
            categorized_nodes[category].append(node_info)
        else:
            uncategorized_nodes.append(node_info)

    # Print statistics
    print(f"\nStatistics:")
    print(f"  Total nodes: {len(LIBRARY)}")
    print(f"  Categorized: {sum(len(nodes) for nodes in categorized_nodes.values())}")
    print(f"  Uncategorized: {len(uncategorized_nodes)}")
    print()

    for category_name, nodes in categorized_nodes.items():
        print(f"  {category_name}: {len(nodes)} nodes")

    if uncategorized_nodes:
        print(f"\nUncategorized nodes:")
        for node_name, _, module_name, _, _ in uncategorized_nodes:
            print(f"  - {node_name} ({module_name})")

    print("\nGenerating documentation files...")

    # Generate documentation files
    all_types_path = args.output_dir / "all_node_types.md"
    terminals_ref_path = args.output_dir / "terminals_quick_ref.md"

    generate_all_node_types_md(categorized_nodes, uncategorized_nodes, all_types_path)
    generate_terminals_quick_ref_md(
        categorized_nodes, uncategorized_nodes, terminals_ref_path
    )

    print("\n✓ Documentation generation complete!")


if __name__ == "__main__":
    main()
