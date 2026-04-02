# AMI Node Terminals Quick Reference

**Generated:** 2026-04-01 20:59:09

Quick lookup table for node terminal names and connection patterns.

---

| Node | Inputs | Outputs |
|------|--------|---------|

---

## Common Terminal Patterns

### Display Nodes
- **ScatterPlot**: Inputs: `X`, `Y` (NEVER use `In` or `In.1`)
- **LinePlot**: Inputs: `X`, `Y` for single trace
- **Histogram**: Input: `Bins` (binned data from Binning node)
- **ScalarPlot**: Input: `Y` (scalar values)

### Processing Nodes
- **Binning**: Input: `Bins` (data to bin); Output: `Out` (NEVER use `XBins`)
- **Binning2D**: Inputs: `XBins`, `YBins` (2D binning)
- **Calculator**: Input: `In`; Output: `Out`

### ROI Nodes
- **Roi0D**: Input: `In`; Output: `Out` (single value)
- **Roi1D**: Input: `In`; Output: `Out` (1D region)
- **Roi2D**: Input: `In`; Output: `Out` (2D region)
