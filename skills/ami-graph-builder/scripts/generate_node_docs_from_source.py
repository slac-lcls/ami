#!/usr/bin/env python3
"""
AMI Node Documentation Generator (Source Parsing Version)

Parses AMI library Python source files directly using AST to extract:
- Node class definitions
- Terminal names from __init__ methods
- Parameters from uiTemplate class attributes
- Docstrings

No runtime imports required - pure static analysis.
"""

import ast
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import re


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
            "Monitor",  # Debug/monitoring display
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
            "Constant",  # Generate constant values
            "Identity",  # Pass-through node
            "Combinations",  # Combine data
            "PythonEditor",  # Custom Python processing
        ],
    },
    "ROI (Region Selection)": {
        "description": "Extract regions of interest from data",
        "keywords": ["region", "ROI", "extract", "select", "rectangle", "area"],
        "nodes": ["Roi2D", "Roi1D", "Roi0D"],
    },
    "Statistics & Analysis": {
        "description": "Compute statistics and analyze data",
        "keywords": ["statistics", "stats", "std", "mean", "median", "variance"],
        "nodes": [
            "Statistics",
            "RMS",  # Root mean square
        ],
    },
    "Filtering & Logic": {
        "description": "Filter and gate data based on conditions",
        "keywords": ["filter", "gate", "pick", "threshold", "condition"],
        "nodes": ["Filter", "Pick", "Gate", "Threshold"],
    },
    "Scan Analysis": {
        "description": "Analyze scans and control variables",
        "keywords": ["scan", "control", "step"],
        "nodes": ["ScanFilter", "ScanMask"],
    },
    "Accumulators & Buffers": {
        "description": "Accumulate or buffer data over time/events",
        "keywords": ["accumulate", "accumulator", "buffer", "rolling"],
        "nodes": [
            "RollingBuffer",
            "Accumulator",
            "ReduceByKey",  # Reduce/aggregate by key
        ],
    },
    "Export": {
        "description": "Export data to external systems (EPICS PVs, files, etc.)",
        "keywords": ["export", "server", "pv", "epics", "h5", "hdf5"],
        "nodes": [
            "PvServer",
            "ImageServer",
            "H5Output",
            "ZMQ",  # ZeroMQ network export
            "UDPMcast",  # UDP multicast export
            "Caput",  # EPICS caput
        ],
    },
    "Advanced Processing": {
        "description": "Advanced signal processing and transformations",
        "keywords": ["fft", "fourier", "correlate", "downsample"],
        "nodes": [
            "Fft",
            "Correlator",
            "DownsampleImage",
            # Scipy nodes
            "Linregress0D",
            "Linregress1D",
            "Rotate",
            "BlobFinder1D",
            "BlobFinder2D",
            "CurveFit",
            "PeakFit",
            # Psalg nodes (detector algorithms)
            "CFD",  # Constant fraction discriminator
            "WFPeaks",  # Waveform peak finding
            "Hexanode",  # Hexanode detector processing
            "HitFinder",  # Hit finding algorithm
            "XTCAVLasingOn",  # XTCAV lasing detection
            "PeakFinder1D",  # 1D peak finding
            "PeakFinderV4R3",  # Peak finder algorithm
            "EdgeFinder",  # Edge detection
            "Mask",  # Masking operations
            "Geometry",  # Geometry corrections
            "Mask3dFrom2d",  # 3D mask from 2D
            "TableFromArr3d",  # Table from 3D array
            "HSDPeakTest",  # HSD peak testing
        ],
    },
}


class NodeSourceParser:
    """Parse node definitions from Python source files."""

    def __init__(self, library_dir):
        self.library_dir = Path(library_dir)
        self.nodes_by_category = defaultdict(list)
        self.uncategorized_nodes = []

    def _ast_to_string(self, node):
        """Fallback for Python < 3.9 that doesn't have ast.unparse()."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value_str = self._ast_to_string(node.value)
            return f"{value_str}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            value_str = self._ast_to_string(node.value)
            slice_str = self._ast_to_string(node.slice)
            return f"{value_str}[{slice_str}]"
        elif isinstance(node, ast.Tuple):
            elements = [self._ast_to_string(elt) for elt in node.elts]
            return ", ".join(elements)
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif hasattr(node, "s"):  # ast.Str in Python < 3.8
            return repr(node.s)  # type: ignore
        elif (
            hasattr(node, "value")
            and hasattr(node, "__class__")
            and node.__class__.__name__ == "Index"
        ):
            # ast.Index in Python < 3.9
            return self._ast_to_string(node.value)  # type: ignore
        else:
            # Fallback: just return a generic type name
            return str(type(node).__name__)

    def parse_all_modules(self):
        """Parse all Python module files in the library directory."""
        module_files = [
            "Display.py",
            "Numpy.py",
            "Operators.py",
            "Roi.py",
            "Accumulators.py",
            "Alert.py",
            "Export.py",
            "Validators.py",
            "Scipy.py",
            "Psalg.py",
            "FFTW.py",
        ]

        all_nodes = []
        for module_file in module_files:
            module_path = self.library_dir / module_file
            if not module_path.exists():
                print(f"  ⚠️  Skipping {module_file} (not found)")
                continue

            print(f"  Parsing {module_file}...")
            nodes = self.parse_module_file(module_path, module_file[:-3])
            all_nodes.extend(nodes)

        return all_nodes

    def parse_module_file(self, file_path, module_name):
        """Parse a single module file and extract node classes."""
        with open(file_path, "r") as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            print(f"    ✗ Syntax error in {file_path}: {e}")
            return []

        nodes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if this is a Node class (has nodeName attribute)
                node_info = self.extract_node_info(node, module_name)
                if node_info:
                    nodes.append(node_info)

                    # Categorize
                    category = self.find_category(node_info["name"])
                    if category:
                        self.nodes_by_category[category].append(node_info)
                    else:
                        self.uncategorized_nodes.append(node_info)

        return nodes

    def extract_node_info(self, class_node, module_name):
        """Extract information from a class AST node."""
        # Look for nodeName class attribute
        node_name = None
        ui_template = None
        terminals_info = {}
        allow_add_input = False
        allow_add_output = False
        docstring = ast.get_docstring(class_node)

        for item in class_node.body:
            # Check for nodeName = "..."
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "nodeName":
                        if isinstance(item.value, ast.Constant):
                            node_name = item.value.value
                        elif isinstance(item.value, ast.Str):  # Python < 3.8
                            node_name = item.value.s

            # Check for uiTemplate = [...]
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "uiTemplate":
                        ui_template = self.extract_ui_template(item.value)

            # Look for __init__ to extract terminals and dynamic capabilities
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                terminals_info, allow_add_input, allow_add_output = (
                    self.extract_terminals_and_capabilities_from_init(item)
                )

        if not node_name:
            return None  # Not a node class

        return {
            "name": node_name,
            "module": module_name,
            "docstring": docstring or "",
            "terminals": terminals_info,
            "parameters": ui_template or [],
            "allow_add_input": allow_add_input,
            "allow_add_output": allow_add_output,
        }

    def extract_ui_template(self, value_node):
        """Extract parameter info from uiTemplate list."""
        parameters = []

        if not isinstance(value_node, ast.List):
            return parameters

        for item in value_node.elts:
            if isinstance(item, ast.Tuple) and len(item.elts) >= 2:
                # Extract (name, type, [options])
                param_info = {}

                # Parameter name
                if isinstance(item.elts[0], ast.Constant):
                    param_info["name"] = item.elts[0].value
                elif isinstance(item.elts[0], ast.Str):
                    param_info["name"] = item.elts[0].s
                else:
                    continue

                # Parameter type
                if isinstance(item.elts[1], ast.Constant):
                    param_info["type"] = item.elts[1].value
                elif isinstance(item.elts[1], ast.Str):
                    param_info["type"] = item.elts[1].s
                else:
                    param_info["type"] = "unknown"

                parameters.append(param_info)

        return parameters

    def extract_terminals_and_capabilities_from_init(self, init_node):
        """Extract terminal names and dynamic capabilities from __init__ method."""
        terminals = {}
        allow_add_input = False
        allow_add_output = False

        # Look for super().__init__(..., terminals={...}, allowAddInput=..., allowAddOutput=...) calls
        for node in ast.walk(init_node):
            if isinstance(node, ast.Call):
                # Check if this is super().__init__()
                is_super_init = False
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__init__"
                ):
                    if isinstance(node.func.value, ast.Call):
                        if (
                            isinstance(node.func.value.func, ast.Name)
                            and node.func.value.func.id == "super"
                        ):
                            is_super_init = True

                if is_super_init:
                    # Look for terminals keyword argument
                    for keyword in node.keywords:
                        if keyword.arg == "terminals":
                            terminals = self.parse_terminals_dict(keyword.value)
                        elif keyword.arg == "allowAddInput":
                            if isinstance(keyword.value, ast.Constant):
                                allow_add_input = keyword.value.value
                            elif hasattr(
                                keyword.value, "value"
                            ):  # ast.NameConstant in Python 3.8
                                allow_add_input = keyword.value.value
                        elif keyword.arg == "allowAddOutput":
                            if isinstance(keyword.value, ast.Constant):
                                allow_add_output = keyword.value.value
                            elif hasattr(
                                keyword.value, "value"
                            ):  # ast.NameConstant in Python 3.8
                                allow_add_output = keyword.value.value

                # Also look for self.addTerminal('name', io='in'/'out')
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "addTerminal"
                ):
                    terminal_info = self.parse_add_terminal_call(node)
                    if terminal_info:
                        terminals[terminal_info["name"]] = terminal_info

        return terminals, allow_add_input, allow_add_output

    def parse_terminals_dict(self, dict_node):
        """Parse terminals={...} dictionary from AST."""
        terminals = {}

        if not isinstance(dict_node, ast.Dict):
            return terminals

        for key, value in zip(dict_node.keys, dict_node.values):
            # Extract terminal name from key
            term_name = None
            if isinstance(key, ast.Constant):
                term_name = key.value
            elif isinstance(key, ast.Str):
                term_name = key.s

            if not term_name:
                continue

            # Extract io type, ttype, and removable from value dict
            term_io = "unknown"
            term_type = None
            term_removable = False
            if isinstance(value, ast.Dict):
                for k, v in zip(value.keys, value.values):
                    key_name = None
                    if isinstance(k, ast.Constant):
                        key_name = k.value
                    elif isinstance(k, ast.Str):
                        key_name = k.s

                    if key_name == "io":
                        if isinstance(v, ast.Constant):
                            term_io = v.value
                        elif isinstance(v, ast.Str):
                            term_io = v.s
                    elif key_name == "ttype":
                        # Convert AST node to string representation
                        try:
                            term_type = ast.unparse(v)
                        except AttributeError:
                            # Python < 3.9 fallback
                            term_type = self._ast_to_string(v)
                    elif key_name == "removable":
                        if isinstance(v, ast.Constant):
                            term_removable = v.value
                        elif hasattr(v, "value"):  # ast.NameConstant in Python 3.8
                            term_removable = v.value  # type: ignore

            terminals[term_name] = {
                "name": term_name,
                "io": term_io,
                "type": term_type,
                "removable": term_removable,
            }

        return terminals

    def parse_add_terminal_call(self, call_node):
        """Parse addTerminal() call to extract terminal info."""
        if not call_node.args:
            return None

        terminal_info = {}

        # First arg is terminal name
        if isinstance(call_node.args[0], ast.Constant):
            terminal_info["name"] = call_node.args[0].value
        elif isinstance(call_node.args[0], ast.Str):
            terminal_info["name"] = call_node.args[0].s
        else:
            return None

        # Look for io, ttype, and removable keywords
        terminal_info["io"] = "unknown"
        terminal_info["type"] = None
        terminal_info["removable"] = False
        for keyword in call_node.keywords:
            if keyword.arg == "io":
                if isinstance(keyword.value, ast.Constant):
                    terminal_info["io"] = keyword.value.value
                elif isinstance(keyword.value, ast.Str):
                    terminal_info["io"] = keyword.value.s
            elif keyword.arg == "ttype":
                try:
                    terminal_info["type"] = ast.unparse(keyword.value)
                except AttributeError:
                    # Python < 3.9 fallback
                    terminal_info["type"] = self._ast_to_string(keyword.value)
            elif keyword.arg == "removable":
                if isinstance(keyword.value, ast.Constant):
                    terminal_info["removable"] = keyword.value.value
                elif hasattr(keyword.value, "value"):  # ast.NameConstant in Python 3.8
                    terminal_info["removable"] = keyword.value.value  # type: ignore

        return terminal_info

    def find_category(self, node_name):
        """Map node to functional category."""
        for category, config in FUNCTIONAL_CATEGORIES.items():
            if node_name in config["nodes"]:
                return category

        # Fallback: keyword matching
        node_lower = node_name.lower()
        for category, config in FUNCTIONAL_CATEGORIES.items():
            for keyword in config["keywords"]:
                if keyword.lower() in node_lower:
                    return category

        return None

    def format_type(self, type_str):
        """Format type string for display (abbreviate Union syntax)."""
        if not type_str:
            return None

        # Replace Union[A, B, C] with A|B|C for readability
        match = re.match(r"Union\[(.*)\]", type_str)
        if match:
            return match.group(1).replace(", ", "|")

        return type_str

    def generate_all_node_types_md(self, output_path):
        """Generate comprehensive node documentation."""
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
            if self.nodes_by_category[category_name]:
                anchor = (
                    category_name.lower()
                    .replace(" ", "-")
                    .replace("&", "")
                    .replace("(", "")
                    .replace(")", "")
                )
                lines.append(f"- [{category_name}](#{anchor})")
        if self.uncategorized_nodes:
            lines.append(f"- [Uncategorized Nodes](#uncategorized-nodes)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Generate each category
        for category_name, category_info in FUNCTIONAL_CATEGORIES.items():
            nodes = self.nodes_by_category[category_name]
            if not nodes:
                continue

            lines.append(f"## {category_name}")
            lines.append("")
            lines.append(f"**Description:** {category_info['description']}")
            lines.append("")

            for node_info in sorted(nodes, key=lambda x: x["name"]):
                lines.extend(self.format_node_doc(node_info))

        # Uncategorized
        if self.uncategorized_nodes:
            lines.append("## Uncategorized Nodes")
            lines.append("")
            for node_info in sorted(self.uncategorized_nodes, key=lambda x: x["name"]):
                lines.extend(self.format_node_doc(node_info))

        # Write file
        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        print(f"✓ Generated: {output_path}")

    def format_node_doc(self, node_info):
        """Format a single node's documentation."""
        lines = []
        lines.append(f"### {node_info['name']}")
        lines.append("")
        lines.append(f"**Module:** {node_info['module']}")
        lines.append("")

        if node_info["docstring"]:
            lines.append("**Description:**")
            lines.append("")
            lines.append(node_info["docstring"])
            lines.append("")

        # Terminals section with types and removable annotations
        if node_info["terminals"]:
            lines.append("**Terminals:**")
            lines.append("")

            inputs = {
                k: v for k, v in node_info["terminals"].items() if v.get("io") == "in"
            }
            outputs = {
                k: v for k, v in node_info["terminals"].items() if v.get("io") == "out"
            }

            if inputs:
                lines.append("*Inputs:*")
                for name, info in sorted(inputs.items()):
                    type_str = self.format_type(info.get("type"))
                    removable = info.get("removable", False)

                    # Format: `name` (type) *[optional, can remove]*
                    if type_str and removable:
                        lines.append(
                            f"- `{name}` ({type_str}) *[optional, can remove]*"
                        )
                    elif type_str:
                        lines.append(f"- `{name}` ({type_str})")
                    elif removable:
                        lines.append(f"- `{name}` *[optional, can remove]*")
                    else:
                        lines.append(f"- `{name}`")
                lines.append("")
            else:
                # Check if node allows adding inputs but has none initially
                if node_info.get("allow_add_input"):
                    lines.append("*Inputs:*")
                    lines.append("- (none initially)")
                    lines.append("")

            if outputs:
                lines.append("*Outputs:*")
                for name, info in sorted(outputs.items()):
                    type_str = self.format_type(info.get("type"))
                    removable = info.get("removable", False)

                    if type_str and removable:
                        lines.append(
                            f"- `{name}` ({type_str}) *[optional, can remove]*"
                        )
                    elif type_str:
                        lines.append(f"- `{name}` ({type_str})")
                    elif removable:
                        lines.append(f"- `{name}` *[optional, can remove]*")
                    else:
                        lines.append(f"- `{name}`")
                lines.append("")
            else:
                # Check if node allows adding outputs but has none initially
                if node_info.get("allow_add_output"):
                    lines.append("*Outputs:*")
                    lines.append("- (none initially)")
                    lines.append("")

        # Add Capabilities section for dynamic terminals
        capabilities = []
        if node_info.get("allow_add_input"):
            capabilities.append("✓ Can add/remove input terminals")
        if node_info.get("allow_add_output"):
            capabilities.append("✓ Can add/remove output terminals")

        if capabilities:
            lines.append("**Capabilities:**")
            lines.append("")
            for cap in capabilities:
                lines.append(f"- {cap}")
            lines.append("")

        if node_info["parameters"]:
            lines.append("**Parameters:**")
            lines.append("")
            for param in node_info["parameters"]:
                lines.append(f"- `{param['name']}` ({param['type']})")
            lines.append("")

        lines.append("---")
        lines.append("")
        return lines

    def generate_terminals_quick_ref_md(self, output_path):
        """Generate terminal quick reference table."""
        lines = []
        lines.append("# AMI Node Terminals Quick Reference")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(
            "Quick lookup table for node terminal names and connection patterns."
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Collect all nodes
        all_nodes = []
        for nodes in self.nodes_by_category.values():
            all_nodes.extend(nodes)
        all_nodes.extend(self.uncategorized_nodes)

        # Sort by name
        all_nodes.sort(key=lambda x: x["name"])

        lines.append("| Node | Inputs | Outputs |")
        lines.append("|------|--------|---------|")

        for node_info in all_nodes:
            terminals = node_info["terminals"]
            if not terminals:
                inputs_str = "-"
                outputs_str = "-"
            else:
                # Format inputs with types
                inputs = []
                for term_name, term_info in sorted(terminals.items()):
                    if term_info.get("io") == "in":
                        type_str = self.format_type(term_info.get("type"))
                        if type_str:
                            inputs.append(f"{term_name} ({type_str})")
                        else:
                            inputs.append(term_name)
                inputs_str = ", ".join(inputs) if inputs else "-"

                # Format outputs with types
                outputs = []
                for term_name, term_info in sorted(terminals.items()):
                    if term_info.get("io") == "out":
                        type_str = self.format_type(term_info.get("type"))
                        if type_str:
                            outputs.append(f"{term_name} ({type_str})")
                        else:
                            outputs.append(term_name)
                outputs_str = ", ".join(outputs) if outputs else "-"

            lines.append(f"| **{node_info['name']}** | {inputs_str} | {outputs_str} |")

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

        # Write file
        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        print(f"✓ Generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate AMI node documentation from source"
    )
    parser.add_argument(
        "--library-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent.parent
        / "ami"
        / "flowchart"
        / "library",
        help="Path to AMI flowchart library directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "references",
        help="Output directory for generated documentation",
    )
    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("AMI Node Documentation Generator (Source Parsing)")
    print("=" * 60)
    print(f"Library directory: {args.library_dir}")
    print(f"Output directory: {args.output_dir}")
    print("")

    # Parse all modules
    parser = NodeSourceParser(args.library_dir)
    print("Parsing AMI library modules...")
    all_nodes = parser.parse_all_modules()

    print("")
    print(f"✅ Parsed {len(all_nodes)} nodes")
    print(
        f"  - Categorized: {sum(len(nodes) for nodes in parser.nodes_by_category.values())}"
    )
    print(f"  - Uncategorized: {len(parser.uncategorized_nodes)}")
    print("")

    for category, nodes in parser.nodes_by_category.items():
        if nodes:
            print(f"  {category}: {len(nodes)} nodes")

    if parser.uncategorized_nodes:
        print("")
        print("⚠️  Uncategorized nodes:")
        for node in parser.uncategorized_nodes:
            print(f"  - {node['name']} ({node['module']})")

    print("")
    print("Generating documentation files...")
    parser.generate_all_node_types_md(args.output_dir / "all_node_types.md")
    parser.generate_terminals_quick_ref_md(args.output_dir / "terminals_quick_ref.md")
    print("")
    print("✅ Documentation generation complete!")


if __name__ == "__main__":
    main()
