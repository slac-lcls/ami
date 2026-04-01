#!/usr/bin/env python3
"""
AMI Node Documentation Generator

Extracts node terminals, parameters, and metadata from AMI source code
and generates markdown documentation organized by functional categories
(optimized for AI agent semantic search).

Usage:
    python generate_node_docs.py [--output-dir ../references]

Output:
    - all_node_types.md: Comprehensive node documentation by function
    - terminals_quick_ref.md: Quick terminal lookup table

Organization: By functional category (Display, Processing, ROI, etc.)
This optimizes for AI agent semantic search rather than GUI module structure.
"""

import sys
import inspect
import ast
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add AMI to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ami.flowchart.library import LIBRARY

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
            "TimePlot",
            "ScalarPlot",
            "Histogram",
            "Histogram2D",
            "Binning",
            "Binning2D",
            "ImageViewer",
            "WaveformViewer",
            "MultiWaveformViewer",
            "ScalarViewer",
            "ObjectViewer",
        ],
    },
    "Data Processing": {
        "description": "Transform, compute, and manipulate data",
        "keywords": [
            "calculate",
            "compute",
            "process",
            "transform",
            "sum",
            "average",
            "mean",
            "project",
            "math",
            "split",
            "stack",
        ],
        "nodes": [
            "Sum",
            "Average",
            "Average0D",
            "Average1D",
            "Average2D",
            "Projection",
            "Split",
            "Stack1d",
            "Stack2d",
            "Take",
            "Polynomial",
            "Calculator",
            "LoadReference1D",
        ],
    },
    "ROI (Region Selection)": {
        "description": "Extract regions of interest from data",
        "keywords": ["region", "ROI", "extract", "select", "rectangle", "area"],
        "nodes": ["Roi2D", "Roi1D", "Roi0D"],
    },
    "Statistics & Analysis": {
        "description": "Statistical operations and data analysis",
        "keywords": [
            "statistics",
            "mean",
            "RMS",
            "regression",
            "fit",
            "correlation",
            "std",
            "variance",
        ],
        "nodes": [
            "TimeMeanRMS0D",
            "TimeMeanRMS1D",
            "TimeMeanRMS2D",
            "HistMeanRMS",
            "RMS",
            "Linregress0D",
            "Linregress1D",
            "CurveFit",
            "PeakFit",
        ],
    },
    "Filtering & Logic": {
        "description": "Boolean filtering and conditional logic",
        "keywords": [
            "filter",
            "condition",
            "boolean",
            "if",
            "threshold",
            "select",
            "where",
        ],
        "nodes": ["Filter"],
    },
    "Scan Analysis": {
        "description": "Analysis of scan/step data",
        "keywords": ["scan", "step", "vs", "sweep", "motor"],
        "nodes": ["MeanVsScan", "StatsVsScan", "MeanWaveformVsScan"],
    },
    "Accumulators & Buffers": {
        "description": "Event accumulation and buffering",
        "keywords": [
            "accumulate",
            "collect",
            "buffer",
            "pick",
            "store",
            "rolling",
            "history",
        ],
        "nodes": ["Accumulator", "Pick1", "PickN", "SumN", "RollingBuffer"],
    },
    "Export": {
        "description": "Export data to external systems",
        "keywords": ["export", "send", "publish", "PV", "ZMQ", "EPICS"],
        "nodes": ["PvExport", "ZMQ", "Caput", "Pvput"],
    },
    "Advanced Processing": {
        "description": "Specialized and advanced operations",
        "keywords": [
            "FFT",
            "fourier",
            "peak",
            "blob",
            "custom",
            "python",
            "transform",
            "frequency",
        ],
        "nodes": [
            "FFT",
            "IFFT",
            "FFT2",
            "IFFT2",
            "PeakFinder1D",
            "BlobFinder1D",
            "BlobFinder2D",
            "PythonEditor",
        ],
    },
}


class NodeDocGenerator:
    """Extract and generate documentation from AMI node classes."""

    def __init__(self):
        self.nodes_by_category = defaultdict(list)
        self.uncategorized_nodes = []

    def extract_all_nodes(self):
        """Extract and categorize all nodes from LIBRARY."""
        all_nodes = []

        for node_name in sorted(LIBRARY.nodeList.keys()):
            try:
                node_class = LIBRARY.getNodeType(node_name)
                info = self.extract_node_info(node_class)
                all_nodes.append(info)

                # Categorize by function
                category = self.find_category(info["name"])
                if category:
                    self.nodes_by_category[category].append(info)
                else:
                    self.uncategorized_nodes.append(info)
            except Exception as e:
                print(f"Warning: Could not process node {node_name}: {e}")

        return all_nodes

    def find_category(self, node_name):
        """Map node to functional category."""
        for category, config in FUNCTIONAL_CATEGORIES.items():
            if node_name in config["nodes"]:
                return category
        return None

    def extract_node_info(self, node_class):
        """Extract comprehensive info from node class."""
        module_name = node_class.__module__.split(".")[-1]
        node_name = getattr(node_class, "nodeName", node_class.__name__)

        return {
            "name": node_name,
            "module": module_name,
            "docstring": inspect.getdoc(node_class) or f"{node_name} node",
            "terminals": self._extract_terminals(node_class),
            "parameters": self._extract_parameters(node_class),
        }

    def _extract_terminals(self, node_class):
        """Extract terminal definitions from __init__."""
        terminals = []

        try:
            # Try to instantiate with dummy name to inspect terminals
            # This is hacky but works for most nodes
            temp_instance = node_class("_temp_")
            if hasattr(temp_instance, "terminals"):
                for term_name, term_obj in temp_instance.terminals.items():
                    terminals.append(
                        {
                            "name": term_name,
                            "io": "in" if term_obj.isInput() else "out",
                            "optional": term_obj.isOptional()
                            if hasattr(term_obj, "isOptional")
                            else False,
                        }
                    )
        except Exception as e:
            # If instantiation fails, try parsing source
            try:
                source = inspect.getsource(node_class.__init__)
                # Look for terminals dict in super().__init__ call
                # This is a simplified parser - may not catch all cases
                if "terminals" in source:
                    # Extract basic terminal names from source
                    for line in source.split("\n"):
                        if "'" in line and (":" in line):
                            # Try to find terminal definitions
                            parts = line.strip().split("'")
                            if len(parts) >= 2 and parts[1] and parts[1][0].isupper():
                                # Looks like a terminal name
                                pass
            except:
                pass

        return terminals

    def _extract_parameters(self, node_class):
        """Extract parameters from uiTemplate."""
        if hasattr(node_class, "uiTemplate"):
            params = []
            for param in node_class.uiTemplate:
                if len(param) >= 2:
                    param_info = {
                        "name": param[0],
                        "type": param[1],
                    }
                    if len(param) >= 3 and isinstance(param[2], dict):
                        param_info["default"] = param[2].get(
                            "value", param[2].get("checked", "")
                        )
                        param_info["constraints"] = param[2]
                    params.append(param_info)
            return params
        return []

    def generate_all_node_types_md(self, output_path):
        """Generate comprehensive reference organized by function."""
        lines = []

        # Header
        lines.append("# AMI Node Types - Complete Reference")
        lines.append("")
        lines.append(f"**Auto-generated from source code**  ")
        lines.append(
            f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  "
        )
        lines.append(
            f"**Organization:** By function (optimized for AI semantic search)"
        )
        lines.append("")
        lines.append(
            "**Note to users:** The AMI GUI organizes nodes by module (Numpy, Display, Operators, etc.). "
            "This reference organizes by function for easier searching. Each node shows its source module for reference."
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Table of contents
        lines.append("## Table of Contents")
        lines.append("")
        for i, (category, config) in enumerate(FUNCTIONAL_CATEGORIES.items(), 1):
            anchor = (
                category.lower().replace(" ", "-").replace("(", "").replace(")", "")
            )
            lines.append(f"{i}. [{category}](#{anchor})")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Generate each category section
        for category, config in FUNCTIONAL_CATEGORIES.items():
            if category not in self.nodes_by_category:
                continue

            nodes = self.nodes_by_category[category]

            lines.append(f"## {category}")
            lines.append("")
            lines.append(f"**Purpose:** {config['description']}")
            lines.append("")
            lines.append(f"**Keywords:** {', '.join(config['keywords'])}")
            lines.append("")
            lines.append(f"**Nodes in this category:** {len(nodes)}")
            lines.append("")
            lines.append("---")
            lines.append("")

            # Generate each node in category
            for node_info in sorted(nodes, key=lambda x: x["name"]):
                self._format_node_section(lines, node_info)

            lines.append("---")
            lines.append("")

        # Uncategorized nodes (if any)
        if self.uncategorized_nodes:
            lines.append("## Other Nodes")
            lines.append("")
            lines.append("**Nodes not yet categorized:**")
            lines.append("")
            for node_info in sorted(self.uncategorized_nodes, key=lambda x: x["name"]):
                self._format_node_section(lines, node_info)

        # Write to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("\n".join(lines))
        print(f"✅ Generated: {output_file}")

    def _format_node_section(self, lines, node_info):
        """Format a single node's documentation."""
        lines.append(f"### {node_info['name']}")
        lines.append("")
        lines.append(f"**Module:** {node_info['module']}  ")
        lines.append(f"**Description:** {node_info['docstring']}")
        lines.append("")

        # Terminals
        if node_info["terminals"]:
            lines.append("**Terminals:**")
            lines.append("")
            lines.append("| Name | Direction | Notes |")
            lines.append("|------|-----------|-------|")
            for term in node_info["terminals"]:
                opt = " (optional)" if term.get("optional") else ""
                lines.append(f"| {term['name']} | {term['io']}put{opt} | - |")
            lines.append("")
        else:
            lines.append("**Terminals:** (Could not extract - see node source)")
            lines.append("")

        # Parameters
        if node_info["parameters"]:
            lines.append("**Parameters:**")
            lines.append("")
            lines.append("| Name | Type | Default | Description |")
            lines.append("|------|------|---------|-------------|")
            for param in node_info["parameters"]:
                default = str(param.get("default", ""))
                lines.append(f"| {param['name']} | {param['type']} | {default} | - |")
            lines.append("")

        lines.append("---")
        lines.append("")

    def generate_terminals_quick_ref_md(self, output_path):
        """Generate quick lookup table by function."""
        lines = []

        # Header
        lines.append("# Terminal Quick Reference")
        lines.append("")
        lines.append("**Fast lookup table for node terminal names.**  ")
        lines.append("**Organization:** By function (optimized for search)")
        lines.append("")
        lines.append(
            "For detailed information, see [all_node_types.md](all_node_types.md)."
        )
        lines.append("")
        lines.append(
            f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Generate table for each category
        for category, config in FUNCTIONAL_CATEGORIES.items():
            if category not in self.nodes_by_category:
                continue

            nodes = self.nodes_by_category[category]

            lines.append(f"## {category}")
            lines.append("")
            lines.append("| Node | Module | Inputs | Outputs | Notes |")
            lines.append("|------|--------|--------|---------|-------|")

            for node_info in sorted(nodes, key=lambda x: x["name"]):
                inputs = ", ".join(
                    [t["name"] for t in node_info["terminals"] if t["io"] == "in"]
                )
                outputs = ", ".join(
                    [t["name"] for t in node_info["terminals"] if t["io"] == "out"]
                )
                inputs = inputs if inputs else "-"
                outputs = outputs if outputs else "-"

                lines.append(
                    f"| {node_info['name']} | {node_info['module']} | {inputs} | {outputs} | - |"
                )

            lines.append("")

        # Legend
        lines.append("---")
        lines.append("")
        lines.append("**Legend:**")
        lines.append("- `[terminal]` - Optional (added via GUI)")
        lines.append("- `terminal*` - Conditional (see all_node_types.md)")
        lines.append("- `-` - No terminals in this direction")
        lines.append("")

        # Write to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("\n".join(lines))
        print(f"✅ Generated: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate AMI node documentation")
    parser.add_argument(
        "--output-dir",
        default="../references",
        help="Output directory for generated docs",
    )
    args = parser.parse_args()

    # Make output dir relative to script location
    script_dir = Path(__file__).parent
    output_dir = (script_dir / args.output_dir).resolve()

    print("AMI Node Documentation Generator")
    print("=" * 50)
    print(f"Output directory: {output_dir}")
    print("")

    # Generate documentation
    generator = NodeDocGenerator()
    print("Extracting node information from AMI library...")
    all_nodes = generator.extract_all_nodes()
    print(f"✅ Extracted {len(all_nodes)} nodes")
    print(
        f"  - Categorized: {sum(len(nodes) for nodes in generator.nodes_by_category.values())}"
    )
    print(f"  - Uncategorized: {len(generator.uncategorized_nodes)}")
    print("")

    print("Generating documentation files...")
    generator.generate_all_node_types_md(output_dir / "all_node_types.md")
    generator.generate_terminals_quick_ref_md(output_dir / "terminals_quick_ref.md")
    print("")
    print("✅ Documentation generation complete!")

    if generator.uncategorized_nodes:
        print("")
        print("⚠️  Uncategorized nodes found:")
        for node in generator.uncategorized_nodes:
            print(f"  - {node['name']} ({node['module']})")
        print("")
        print("Consider adding these to FUNCTIONAL_CATEGORIES in the script.")


if __name__ == "__main__":
    main()
