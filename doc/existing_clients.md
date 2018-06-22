
## Existing AMI Clients

This page documents the existing clients from AMI-1.

### PS-Mon

<img src="clients/AMI1_screenshots/PS-Mon_001.png">

The initial UI lets the user choose from among several data sources
(Env, LineFit, Amitol, yag3).

It also provides session control
(Folder, Progress, Run, Throttle, Setup, Data, Find Plot).
TODO: explain session control.

All data is scalar.  There are no vector fields.


### Env (0-dimensional data)

<img src="clients/AMI1_screenshots/Env_1d_histogram_UI_002.png">

The Env data source supports one of six modes for displaying data
(1D histogram, v Time, Mean v Var, Mean v Scan, 2D histogram, Mean v Var2D).
All of these modes support "Normalize" and "Weight by" as shown.
Refer to these as "standard plot types".


<img src="clients/AMI1_screenshots/1dhistogram_003.png">

All of the modes produce a small x-y plot like this one for the 1D histogram.
Refer to these as "standard small plots".

<img src="clients/AMI1_screenshots/1d_vtime_1_004.png">

Here is a plot from the "v Time" mode, it is similar to the 1D histogram plot.

<img src="clients/AMI1_screenshots/Env_Filter_005.png">

We can apply a filter to the data source like this.

The next images show the different modes:

<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/Env_vtime_UI_006.png">
</th>
<th>
<img src="clients/AMI1_screenshots/Env_mean_v_var_UI_007.png">
</th>
<th>
<img src="clients/AMI1_screenshots/Env_mean_v_scan_UI_008.png">
</th>
<th>
<img src="clients/AMI1_screenshots/Env_2d_histogram_UI_009.png">
</th>
<th>
<img src="clients/AMI1_screenshots/Env_mean_v_var2D_UI_010.png">
</th>
</tr>
</table>

The only difference among these modes is the selection in the "Plot type" region.

### LineFit (two 0-dimensional data)

LineFit has 4 plotting modes.  Every mode selects source channels, fit method, and plot type.
The plots themselves look the same as for the Env modes.

<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/LineFit_vTime_UI_011.png">
</th>
<th>
<img src="clients/AMI1_screenshots/LineFit_meanVVar_UI_012.png">
</th>
<th>
<img src="clients/AMI1_screenshots/LineFit_meanVScan_013.png">
</th>
<th>
<img src="clients/AMI1_screenshots/LineFit_meanVVar2D_014.png">
</th>
</tr>
</table>


Each plot mode has different specifications.

### AmoITOF (1-dimensional data)

<img src="clients/AMI1_screenshots/AmoITOF-0_Acqiris-0_1_035.png">

This is a waveform display.


<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/AmoITOF-0_EdgeFinder_036.png">
</th>
<th>
<img src="clients/AMI1_screenshots/AmoITOF-0_Cursors_037.png">
</th>
<th>
<img src="clients/AMI1_screenshots/AmoITOF-0_CurveFit_038.png">
</th>
<th>
<img src="clients/AMI1_screenshots/AmoITOF-0_FFT_039.png">
</th>
</tr>
</table>

Options include Edges, Cursors, Waveform Fit, Waveform FFT.

### yag3 (2-dimensional data)


<img src="clients/AMI1_screenshots/yag3_016.png">

yag3 is an image sensor for e.g. a CSPAD detector.
It supports six analysis modes:
X/Y, rho/psi, contour projection, hit finder, blob finder, droplet.

<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_XY_image_projection_histogram_017.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_XY_image_projection_projection_018.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_XY_image_projection_function_019.png">
</th>
</tr>
</table>

X/Y selection offers three plot modes:
histogram, projection, function.
All modes offer a region-of-interest selection.
Function mode offers the standard plot types (1d histogram, etc) and normalize/weight by specification
as well as a range expression.


<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_rho_psi_projection_020.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_rho_psi_integral_021.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_rho_psi_contrast_022.png">
</th>
</tr>
</table>

rho/psi projection offers three plot modes:
projection, integral and contrast.
Integral and contrast provide the standard plot types with normalize and range expression.


<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_Contour_Projection_023.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_Contour_Projection_plot_024.png">
</th>
</tr>
</table>


Contour projection opens a plot like this.

<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_Contour_Projection_plot_Cursors_025.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_Contour_Projection_plot_peakfit_026.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_Contour_Projection_plot_Fit_027.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_Contour_Projection_plot_XTransform_028.png">
</th>
</tr>
</table>

The contour projection plot supports options for Cursors, Peak, Fit and X Transform.


<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_HitFinder_029.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_HitFinder_plot_030.png">
</th>
</tr>
</table>

Selecting "Hit Finder" brings up the PeakFinder plot.
Pressing "plot" brings up an image window.


<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_BlobFinder_031.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_BlobFinder_plot_032.png">
</th>
</tr>
</table>

Selecting "Blob Finder: brings up this window.
Selecting "plot" brings up the image window.

<table style="width:100%">
<tr>
<th>
<img src="clients/AMI1_screenshots/yag_Droplet_map_UI_033.png">
</th>
<th>
<img src="clients/AMI1_screenshots/yag_Droplet_plot_030.png">
</th>
</tr>
</table>


Selecting "Droplet" brings up the drop analysis window which has two modes, Map and Analysis.
In Map mode selecting "plot" brings up an image window.

<img src="clients/AMI1_screenshots/yag_Droplet_analysis_UI_034.png">

In Analysis mode selecting "plot" brings up a standard small plot.


