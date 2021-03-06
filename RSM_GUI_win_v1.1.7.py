#!/usr/bin/python
# -*- coding: utf-8 -*-
import numpy as np
import scipy.ndimage
from scipy import stats
from scipy.fftpack import fft, fftfreq, fftshift
import os, sys
import gc
from os import listdir
from os.path import isfile,join
import gtk
import matplotlib as mpl
import matplotlib.pyplot as plt
#mpl.use('GtkAgg')
from matplotlib.figure import Figure
#from matplotlib.axes import Subplot
from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg as FigureCanvas
from matplotlib.backends.backend_gtkagg import NavigationToolbar2GTKAgg as NavigationToolbar
from matplotlib.cm import jet#, gist_rainbow # colormap
from matplotlib.widgets import Cursor
#from matplotlib.patches import Rectangle
from matplotlib import path
#import matplotlib.patches as patches
from matplotlib.ticker import MaxNLocator
import xrayutilities as xu
from lmfit import Parameters, minimize
import h5py as h5
from lib import mca_spec as SP

__version__ = "1.1.7"
__date__ = "05/11/2014"
__author__ = "Thanh-Tra NGUYEN"
__email__ = "thanhtra0104@gmail.com"

#mpl.rcParams['font.size'] = 18.0
#mpl.rcParams['axes.labelsize'] = 'large'
mpl.rcParams['legend.fancybox'] = True
mpl.rcParams['legend.handletextpad'] = 0.5
mpl.rcParams['legend.fontsize'] = 'medium'
mpl.rcParams['figure.subplot.bottom'] = 0.13
mpl.rcParams['figure.subplot.top'] = 0.93
mpl.rcParams['figure.subplot.left'] = 0.14
mpl.rcParams['figure.subplot.right'] = 0.915
mpl.rcParams['savefig.dpi'] = 300

def Fourier(X,vect):  
	N  = vect.size   #number of data points
	T  = X[1] - X[0] #sample spacing
	TF = fft(vect)
	
	xf = fftfreq(N,T)
	xf = fftshift(xf)
	yplot = fftshift(TF)
	yplot = np.abs(yplot)
	yplot = yplot[N/2:]
	xf    = xf[N/2:]
	return xf, yplot/yplot.max()

def flat_data(data,dynlow, dynhigh, log):
	""" Returns data where maximum superior than 10^dynhigh will be replaced by 10^dynhigh, inferior than 10^dynlow will be replaced by 10^dynlow"""
	if log:
		mi = 10**dynlow
		ma = 10**dynhigh
		data=np.minimum(np.maximum(data,mi),ma)
		data=np.log10(data)
	else:
		mi = dynlow
		ma = dynhigh
		data=np.minimum(np.maximum(data,mi),ma)
	return data
	
def psdVoigt(parameters,x):
	"""Define pseudovoigt function"""
	y0 = parameters['y0'].value
	xc = parameters['xc'].value
	A  = parameters['A'].value
	w  = parameters['w'].value
	mu = parameters['mu'].value

	y  = y0 + A * ( mu * (2/np.pi) * (w / (4*(x-xc)**2 + w**2)) + (1 - mu) * (np.sqrt(4*np.log(2)) / (np.sqrt(np.pi) * w)) * np.exp(-(4*np.log(2)/w**2)*(x-xc)**2) )

	return y

def objective(pars,y,x):
	#we will minimize this function
	err =  y - psdVoigt(pars,x)
	return err
def init(data_x,data_y,xc,arbitrary=False):
	""" param = [y0, xc, A, w, mu]
	Je veux que Xc soit la position que l'utilisateur pointe sur l'image pour tracer les profiles"""
	param = Parameters()
	#idA=np.where(data_x - xc < 1e-4)[0]
	if arbitrary:
		A  = data_y.max()
	else:
		idA=np.where(data_x==xc)[0][0]
		A  = data_y[idA]
	y0 = 1.0
	w  = 0.5
	mu = 0.5
	param.add('y0', value=y0)
	param.add('xc', value=xc)
	param.add('A', value=A)
	param.add('w', value=w)
	param.add('mu', value=mu, min=0., max=1.)
	return param

def fit(data_x,data_y,xc, arbitrary=False):
	""" return: fitted data y, fitted parameters """
	param_init = init(data_x,data_y,xc,arbitrary)
	if data_x[0] > data_x[-1]:
		data_x = data_x[::-1]
	result = minimize(objective, param_init, args=(data_y,data_x))

	x = np.linspace(data_x.min(),data_x.max(),data_x.shape[0])
	y = psdVoigt(param_init,x)

	return param_init, y

class PopUpFringes(object):
	def __init__(self, xdata, xlabel, ylabel, title):
		self.popupwin=gtk.Window()
		self.popupwin.set_size_request(600,550)
		self.popupwin.set_position(gtk.WIN_POS_CENTER)
		self.popupwin.set_border_width(10)
		self.xdata = xdata
		vbox = gtk.VBox()
		self.fig=Figure(dpi=100)
		self.ax  = self.fig.add_subplot(111)
		self.canvas  = FigureCanvas(self.fig)
		self.main_figure_navBar = NavigationToolbar(self.canvas, self)
		self.cursor = Cursor(self.ax, color='k', linewidth=1, useblit=True)
		self.ax.set_xlabel(xlabel, fontsize = 18)
		self.ax.set_ylabel(ylabel, fontsize = 18)
		self.ax.set_title(title, fontsize = 18)
		
		xi = np.arange(len(self.xdata))		
		slope, intercept, r_value, p_value, std_err = stats.linregress(self.xdata,xi)
		fitline = slope*self.xdata+intercept
		
		self.ax.plot(self.xdata, fitline, 'r-',self.xdata,xi, 'bo')
		self.ax.axis([self.xdata.min(),self.xdata.max(),xi.min()-1, xi.max()+1])
		
		self.ax.text(0.3, 0.9,'Slope = %.4f +- %.4f' % (slope, std_err),
								horizontalalignment='center',
								verticalalignment='center',
								transform = self.ax.transAxes,
								color='red')
		vbox.pack_start(self.main_figure_navBar, False, False, 0)
		vbox.pack_start(self.canvas, True, True, 2)
		self.popupwin.add(vbox)
		self.popupwin.connect("destroy", self.dest)
		self.popupwin.show_all()
	
	def dest(self,widget):
		self.popupwin.destroy()
	
class PopUpImage(object):
	def __init__(self, xdata, ydata, xlabel, ylabel, title):
		self.popupwin=gtk.Window()
		self.popupwin.set_size_request(600,550)
		self.popupwin.set_position(gtk.WIN_POS_CENTER)
		self.popupwin.set_border_width(10)
		self.xdata = xdata
		self.ydata = ydata
		vbox = gtk.VBox()
		self.fig=Figure(dpi=100)
		self.ax  = self.fig.add_subplot(111)
		self.canvas  = FigureCanvas(self.fig)
		self.main_figure_navBar = NavigationToolbar(self.canvas, self)
		self.cursor = Cursor(self.ax, color='k', linewidth=1, useblit=True)
		self.canvas.mpl_connect("button_press_event",self.on_press)
		self.ax.set_xlabel(xlabel, fontsize = 18)
		self.ax.set_ylabel(ylabel, fontsize = 18)
		self.ax.set_title(title, fontsize = 18)
		self.ax.plot(self.xdata, self.ydata, 'b-', lw=2)
		
		self.textes = []
		self.plots  = []
		vbox.pack_start(self.main_figure_navBar, False, False, 0)
		vbox.pack_start(self.canvas, True, True, 2)
		self.popupwin.add(vbox)
		self.popupwin.connect("destroy", self.dest)
		self.popupwin.show_all()
	
	def dest(self,widget):
		self.popupwin.destroy()
	
	def on_press(self, event):
		if event.inaxes == self.ax and event.button==3:
			self.clear_notes()
			xc = event.xdata
			#***** Find the closest x value *****
			residuel = self.xdata - xc
			residuel = np.abs(residuel)
			j = np.argmin(residuel)
			#y = self.ydata[i-1:i+1]
			#yc= y.max()
			#j = np.where(self.ydata == yc)
			#j = j[0][0]
			xc= self.xdata[j]
			x_fit = self.xdata[j-3:j+3]
			y_fit = self.ydata[j-3:j+3]
			fitted_param, fitted_data = fit(x_fit, y_fit, xc, True)
			x_fit = np.linspace(x_fit.min(), x_fit.max(), 200)
			y_fit = psdVoigt(fitted_param, x_fit)
			period = fitted_param['xc'].value
			std_err= fitted_param['xc'].stderr
			
			p = self.ax.plot(x_fit, y_fit,'r-')
			p2 = self.ax.axvline(period,color='green',lw=2)
			
			txt=self.ax.text(0.05, 0.9, 'Period = %.4f +- %.4f (nm)'%(period, std_err), transform = self.ax.transAxes, color='red')
			self.textes.append(txt)
			self.plots.append(p[0])
			self.plots.append(p2)
		elif event.inaxes == self.ax and event.button==2:
			dif = np.diff(self.ydata)
			dif = dif/dif.max()
			p3=self.ax.plot(dif,'r-')
			self.plots.append(p3[0])
		self.canvas.draw()
	
	def clear_notes(self):
		if len(self.textes)>0:
			for t in self.textes:
				t.remove()
		if len(self.plots)>0:
			for p in self.plots:
				p.remove()
		self.textes = []
		self.plots  = []
		
class MyMainWindow(gtk.Window):

	def __init__(self):
		super(MyMainWindow, self).__init__()
		self.set_title("MCA Reciprocal space map processing. Version %s - last update on: %s"%(__version__,__date__))
		self.set_size_request(1200,900)
		self.set_position(gtk.WIN_POS_CENTER)
		self.set_border_width(10)

		self.toolbar = gtk.Toolbar()
		self.toolbar.set_style(gtk.TOOLBAR_ICONS)

		self.refreshtb = gtk.ToolButton(gtk.STOCK_REFRESH)
		self.opentb = gtk.ToolButton(gtk.STOCK_OPEN)
		self.sep = gtk.SeparatorToolItem()
		self.aspecttb = gtk.ToolButton(gtk.STOCK_PAGE_SETUP)
		self.quittb = gtk.ToolButton(gtk.STOCK_QUIT)

		self.toolbar.insert(self.opentb, 0)
		self.toolbar.insert(self.refreshtb, 1)
		self.toolbar.insert(self.aspecttb, 2)
		self.toolbar.insert(self.sep, 3)
		self.toolbar.insert(self.quittb, 4)

		self.tooltips = gtk.Tooltips()
		self.tooltips.set_tip(self.refreshtb,"Reload data files")
		self.tooltips.set_tip(self.opentb,"Open a folder containing HDF5 (*.h5) data files")
		self.tooltips.set_tip(self.aspecttb,"Change the graph's aspect ratio")
		self.tooltips.set_tip(self.quittb,"Quit the program")
		self.opentb.connect("clicked", self.choose_folder)
		self.refreshtb.connect("clicked",self.folder_update)
		self.aspecttb.connect("clicked",self.change_aspect_ratio)
		self.quittb.connect("clicked", gtk.main_quit)
		self.graph_aspect = False #Flag to change the aspect ratio of the graph, False = Auto, True = equal
		############################# BOXES ###############################################
		vbox = gtk.VBox()
		vbox.pack_start(self.toolbar,False,False,0)
		hbox=gtk.HBox()

		######################### TREE VIEW #############################################
		self.sw = gtk.ScrolledWindow()
		self.sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
		self.sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

		hbox.pack_start(self.sw, False, False, 0)
		self.store=[]
		self.list_store = gtk.ListStore(str)
		self.treeView = gtk.TreeView(self.list_store)
		self.treeView.connect("row-activated",self.on_changed_rsm)

		rendererText = gtk.CellRendererText()
		self.TVcolumn = gtk.TreeViewColumn("RSM data files", rendererText, text=0)
		self.TVcolumn.set_sort_column_id(0)
		self.treeView.append_column(self.TVcolumn)

		self.sw.add(self.treeView)

		self.GUI_current_folder = self.DATA_current_folder = os.getcwd()
		
		#******************************************************************
		#                    Notebooks
		#******************************************************************
		self.notebook = gtk.Notebook()
		self.page_GUI = gtk.HBox()
		self.page_conversion = gtk.VBox()
		self.page_XRDML = gtk.VBox()
		######################################FIGURES####################33
		#self.page_single_figure = gtk.HBox()
		self.midle_panel = gtk.VBox()
		self.rsm = ""
		self.rsm_choosen = ""
		self.my_notes = []
		self.lines = []
		self.points=[]
		self.polygons=[]
		self.fig=Figure(dpi=100)
		## Draw line for arbitrary profiles
		self.arb_lines_X = []
		self.arb_lines_Y = []
		self.arb_line_points = 0
		#self.ax  = self.fig.add_subplot(111)
		self.ax  = self.fig.add_axes([0.1,0.2,0.7,0.7])
		self.fig.subplots_adjust(left=0.1,bottom=0.20, top=0.90)
		
		self.vmin = 0
		self.vmax = 1000
		self.vmax_range = self.vmax
		
		self.canvas  = FigureCanvas(self.fig)
		Fig_hbox = gtk.HBox()
		self.Export_HQ_Image_btn = gtk.Button("Save HQ image")
		self.Export_HQ_Image_btn.connect("clicked", self.Export_HQ_Image)
		self.main_figure_navBar = NavigationToolbar(self.canvas, self)
		self.cursor = Cursor(self.ax, color='k', linewidth=1, useblit=True)
		#Global color bar
		self.cax = self.fig.add_axes([0.85, 0.20, 0.03, 0.70])#left,bottom,width,height
		
		#self.canvas.mpl_connect("motion_notify_event",self.on_motion)
		self.canvas.mpl_connect("button_press_event",self.on_press)
		#self.canvas.mpl_connect("button_release_event",self.on_release)
		self.mouse_moved = False #If click without move: donot zoom the image
		
		Fig_hbox.pack_start(self.Export_HQ_Image_btn, False, False, 0)
		Fig_hbox.pack_start(self.main_figure_navBar, True,True, 0)
		self.midle_panel.pack_start(Fig_hbox, False,False, 0)
		self.midle_panel.pack_start(self.canvas, True,True, 2)

		self.page_GUI.pack_start(self.midle_panel, True,True, 0)
		#hbox.pack_start(self.midle_panel, True,True, 0)

		########################################## RIGHT PANEL ###################

		self.right_panel = gtk.VBox(False,0)
		self.linear_scale_btn = gtk.ToggleButton("Linear scale")
		self.linear_scale_btn.set_usize(30,0)
		self.linear_scale_btn.connect("toggled",self.log_update)
		self.log_scale=0

		#self.wavelength_txt = gtk.Label("Energy (eV)")
		##self.wavelength_txt.set_alignment(1,0.5)
		#self.wavelength_field = gtk.Entry()
		#self.wavelength_field.set_text("8333")
		#self.wavelength_field.set_usize(30,0)
		#self.lattice_const_txt = gtk.Label("Lattice constant (nm)")
		#self.lattice_const_txt.set_alignment(1,0.5)
		#self.lattice_const = gtk.Entry()
		#self.lattice_const.set_text("0.5431")
		#self.lattice_const.set_usize(30,0)
		self.int_range_txt = gtk.Label("Integration range")
		self.int_range_txt.set_alignment(1,0.5)
		self.int_range = gtk.Entry()
		self.int_range.set_text("0.05")
		self.int_range.set_usize(30,0)
		self.fitting_range_txt = gtk.Label("Fitting range")
		self.fitting_range_txt.set_alignment(1,0.5)
		self.fitting_range = gtk.Entry()
		self.fitting_range.set_text("0.1")
		self.fitting_range.set_usize(30,0)
		# ********** Set the default values for configuration *************
		
		self.plotXYprofiles_btn = gtk.RadioButton(None,"Plot X,Y profiles")
		self.plotXYprofiles_btn.set_active(False)
		self.arbitrary_profiles_btn = gtk.RadioButton(self.plotXYprofiles_btn,"Arbitrary profiles")
		self.rectangle_profiles_btn = gtk.RadioButton(self.plotXYprofiles_btn,"ROI projection")

		self.option_table = gtk.Table(4,3,False)#Pack the options
		self.option_table.attach(self.linear_scale_btn, 0,1,0,1)
		self.option_table.attach(self.plotXYprofiles_btn,0,1,1,2)
		self.option_table.attach(self.arbitrary_profiles_btn,0,1,2,3)
		self.option_table.attach(self.rectangle_profiles_btn,0,1,3,4)
		# self.option_table.attach(self.wavelength_txt,1,2,0,1)
		# self.option_table.attach(self.wavelength_field,2,3,0,1)
		# self.option_table.attach(self.lattice_const_txt,1,2,1,2)
		# self.option_table.attach(self.lattice_const, 2,3,1,2)
		self.option_table.attach(self.int_range_txt, 1,2,0,1)
		self.option_table.attach(self.int_range, 2,3,0,1)
		self.option_table.attach(self.fitting_range_txt, 1,2,1,2)
		self.option_table.attach(self.fitting_range, 2,3,1,2)

		### Options for profile plots
		self.profiles_log_btn = gtk.ToggleButton("Y-Log")
		self.profiles_log_btn.connect("toggled",self.profiles_update)
		self.profiles_export_data_btn = gtk.Button("Export data")
		self.profiles_export_data_btn.connect("clicked",self.profiles_export)

		self.profiles_option_box = gtk.HBox(False,0)
		self.profiles_option_box.pack_start(self.profiles_log_btn, False, False, 0)
		self.profiles_option_box.pack_start(self.profiles_export_data_btn, False, False, 0)

		### Figure of profiles plot
		self.profiles_fringes = []
		self.fig_profiles = Figure()
		self.profiles_ax1 = self.fig_profiles.add_subplot(211)
		self.profiles_ax1.set_title("Qz profile", size=14)
		self.profiles_ax2 = self.fig_profiles.add_subplot(212)
		self.profiles_ax2.set_title("Qx profile", size=14)
		self.profiles_canvas = FigureCanvas(self.fig_profiles)
		self.profiles_canvas.set_size_request(450,50)
		self.profiles_canvas.mpl_connect("button_press_event",self.profile_press)
		self.profiles_navBar = NavigationToolbar(self.profiles_canvas, self)
		self.cursor_pro1 = Cursor(self.profiles_ax1, color='k', linewidth=1, useblit=True)
		self.cursor_pro2 = Cursor(self.profiles_ax2, color='k', linewidth=1, useblit=True)

		#### Results of fitted curves
		self.fit_results_table = gtk.Table(7,3, False)
		title = gtk.Label("Fitted results:")
		self.chi_title = gtk.Label("Qz profile")
		self.tth_title = gtk.Label("Qx profile")
		y0 = gtk.Label("y0:")
		xc = gtk.Label("xc:")
		A = gtk.Label("A:")
		w = gtk.Label("FWHM:")
		mu = gtk.Label("mu:")
		y0.set_alignment(0,0.5)
		xc.set_alignment(0,0.5)
		A.set_alignment(0,0.5)
		w.set_alignment(0,0.5)
		mu.set_alignment(0,0.5)

		self.Qz_fitted_y0 = gtk.Label()
		self.Qz_fitted_xc = gtk.Label()
		self.Qz_fitted_A = gtk.Label()
		self.Qz_fitted_w = gtk.Label()
		self.Qz_fitted_mu = gtk.Label()

		self.Qx_fitted_y0 = gtk.Label()
		self.Qx_fitted_xc = gtk.Label()
		self.Qx_fitted_A = gtk.Label()
		self.Qx_fitted_w = gtk.Label()
		self.Qx_fitted_mu = gtk.Label()

		self.fit_results_table.attach(title,0,3,0,1)
		self.fit_results_table.attach(self.chi_title,1,2,1,2)
		self.fit_results_table.attach(self.tth_title,2,3,1,2)
		self.fit_results_table.attach(y0,0,1,2,3)
		self.fit_results_table.attach(xc,0,1,3,4)
		self.fit_results_table.attach(A,0,1,4,5)
		self.fit_results_table.attach(w,0,1,5,6)
		self.fit_results_table.attach(mu,0,1,6,7)

		self.fit_results_table.attach(self.Qz_fitted_y0,1,2,2,3)
		self.fit_results_table.attach(self.Qz_fitted_xc,1,2,3,4)
		self.fit_results_table.attach(self.Qz_fitted_A,1,2,4,5)
		self.fit_results_table.attach(self.Qz_fitted_w,1,2,5,6)
		self.fit_results_table.attach(self.Qz_fitted_mu,1,2,6,7)

		self.fit_results_table.attach(self.Qx_fitted_y0,2,3,2,3)
		self.fit_results_table.attach(self.Qx_fitted_xc,2,3,3,4)
		self.fit_results_table.attach(self.Qx_fitted_A,2,3,4,5)
		self.fit_results_table.attach(self.Qx_fitted_w,2,3,5,6)
		self.fit_results_table.attach(self.Qx_fitted_mu,2,3,6,7)

		#### PACK the right panel
		self.right_panel.pack_start(self.option_table, False, False, 0)
		self.right_panel.pack_start(self.profiles_option_box,False,False,0)
		self.right_panel.pack_start(self.profiles_navBar,False,False,0)
		self.right_panel.pack_start(self.profiles_canvas,True,True,0)
		self.right_panel.pack_start(self.fit_results_table, False, False, 0)
		
		self.page_GUI.pack_end(self.right_panel,False, False,5)
		#********************************************************************
		#          Conversion data SPEC to HDF page
		#********************************************************************
		self.conv_box = gtk.VBox()
		self.box1 = gtk.HBox()
		self.det_frame = gtk.Frame()
		self.det_frame.set_label("Detector Vantec")
		self.det_frame.set_label_align(0.5,0.5)
		self.exp_frame = gtk.Frame()
		self.exp_frame.set_label("Experiment parameters")
		self.exp_frame.set_label_align(0.5,0.5)
		self.conv_frame = gtk.Frame()
		self.conv_frame.set_label("Data conversion: SPEC-HDF5")
		self.conv_frame.set_label_align(0.5,0.5)
		#self.conv_frame.set_alignment(0.5,0.5)
		#********************************************************************
		#           Detector parameters
		#********************************************************************
		self.det_table = gtk.Table(6,2,False)
		
		self.t1 = gtk.Label("Detector size (mm)")
		self.t2 = gtk.Label("Number of channels")
		self.t3 = gtk.Label("Center channel")
		self.t4 = gtk.Label("Channels/Degree")
		self.t5 = gtk.Label("ROI (from-to)")
		self.t6 = gtk.Label("Orientation")
		self.t1.set_alignment(0,0.5)
		self.t2.set_alignment(0,0.5)
		self.t3.set_alignment(0,0.5)
		self.t4.set_alignment(0,0.5)
		self.t5.set_alignment(0,0.5)
		self.t6.set_alignment(0,0.5)
		
		self.t1_entry = gtk.Entry()
		self.t1_entry.set_text("50")
		self.t2_entry = gtk.Entry()
		self.t2_entry.set_text("2048")
		self.t3_entry = gtk.Entry()
		self.t3_entry.set_text("819.87")
		self.t4_entry = gtk.Entry()
		self.t4_entry.set_text("211.012")
		self.small_box = gtk.HBox()
		self.t5_label = gtk.Label("-")
		self.t5_entry1 = gtk.Entry()
		self.t5_entry1.set_text("40")
		self.t5_entry2 = gtk.Entry()
		self.t5_entry2.set_text("1300")
		self.small_box.pack_start(self.t5_entry1,True, True,0)
		self.small_box.pack_start(self.t5_label,True, True,0)
		self.small_box.pack_start(self.t5_entry2,True, True,0)
		
		self.t6_entry = gtk.combo_box_new_text()
		self.t6_entry.append_text("Up (zero on the bottom)")
		self.t6_entry.append_text("Down (zero on the top)")
		self.t6_entry.set_active(1)
		
		self.det_table.attach(self.t1, 0,1,0,1)
		self.det_table.attach(self.t2, 0,1,1,2)
		self.det_table.attach(self.t3, 0,1,2,3)
		self.det_table.attach(self.t4, 0,1,3,4)
		self.det_table.attach(self.t5, 0,1,4,5)
		self.det_table.attach(self.t6, 0,1,5,6)
		
		self.det_table.attach(self.t1_entry, 1,2,0,1)
		self.det_table.attach(self.t2_entry, 1,2,1,2)
		self.det_table.attach(self.t3_entry, 1,2,2,3)
		self.det_table.attach(self.t4_entry, 1,2,3,4)
		self.det_table.attach(self.small_box, 1,2,4,5)
		self.det_table.attach(self.t6_entry, 1,2,5,6)
		
		self.det_table_align = gtk.Alignment()
		self.det_table_align.set_padding(15,10,10,10)
		self.det_table_align.set(0.5, 0.5, 1.0, 1.0)
		self.det_table_align.add(self.det_table)
		self.det_frame.add(self.det_table_align)
		#********************************************************************
		#           Experiment parameters
		#********************************************************************
		self.exp_table = gtk.Table(6,2,False)
		
		self.e1 = gtk.Label("Substrate material:")
		self.e1_other  = gtk.Label("If other:")
		self.e2 = gtk.Label("Energy (eV)")
		self.e3 = gtk.Label("Attenuation coefficient file")
		self.e4 = gtk.Label("Foil colunm name (in SPEC file)")
		self.e5 = gtk.Label("Monitor colunm name (in SPEC file)")
		self.e6 = gtk.Label("Reference monitor (for normalization)")
		
		self.e1.set_alignment(0,0.5)
		self.e1_other.set_alignment(1,0.5)
		self.e2.set_alignment(0,0.5)
		self.e3.set_alignment(0,0.5)
		self.e4.set_alignment(0,0.5)
		self.e5.set_alignment(0,0.5)
		self.e6.set_alignment(0,0.5)
		
		#self.e1_entry = gtk.Label("Si for now")
		self.e1_entry = gtk.combo_box_new_text()
		self.e1_entry.append_text("-- other")
		self.e1_entry.append_text("Si")
		self.e1_entry.append_text("Ge")
		self.e1_entry.append_text("GaAs")
		self.e1_entry.append_text("GaP")
		self.e1_entry.append_text("GaSb")
		self.e1_entry.append_text("InAs")
		self.e1_entry.append_text("InP")
		self.e1_entry.append_text("InSb")
		self.e1_entry.set_active(1)
		self.e1_entry_other = gtk.Entry()
		self.e1_entry_other.set_text("")
		
		self.e2_entry = gtk.Entry()
		self.e2_entry.set_text("8333")
		self.e3_box = gtk.HBox()
		self.e3_path =gtk.Entry()
		self.e3_browse = gtk.Button("Browse")
		self.e3_browse.connect("clicked", self.select_file, self.e3_path, "A")
		self.e3_box.pack_start(self.e3_path, False, False, 0)
		self.e3_box.pack_start(self.e3_browse, False, False, 0)
		self.e4_entry = gtk.Entry()
		self.e4_entry.set_text("pfoil")
		self.e5_entry = gtk.Entry()
		self.e5_entry.set_text("vct3")
		self.e6_entry = gtk.Entry()
		self.e6_entry.set_text("1e6")
		
		substrate_box1 = gtk.HBox()
		substrate_box2 = gtk.HBox()
		substrate_box1.pack_start(self.e1, False, False, 0)
		substrate_box1.pack_start(self.e1_entry, False, False, 0)
		substrate_box2.pack_start(self.e1_other, False, False, 0)
		substrate_box2.pack_start(self.e1_entry_other, False, False, 0)
		self.exp_table.attach(substrate_box1, 0,1,0,1)
		self.exp_table.attach(self.e2, 0,1,1,2)
		self.exp_table.attach(self.e3, 0,1,2,3)
		self.exp_table.attach(self.e4, 0,1,3,4)
		self.exp_table.attach(self.e5, 0,1,4,5)
		self.exp_table.attach(self.e6, 0,1,5,6)
		
		self.exp_table.attach(substrate_box2, 1,2,0,1)
		self.exp_table.attach(self.e2_entry, 1,2,1,2)
		self.exp_table.attach(self.e3_box, 1,2,2,3)
		self.exp_table.attach(self.e4_entry, 1,2,3,4)
		self.exp_table.attach(self.e5_entry, 1,2,4,5)
		self.exp_table.attach(self.e6_entry, 1,2,5,6)
		
		self.exp_table_align = gtk.Alignment()
		self.exp_table_align.set_padding(15,10,10,10)
		self.exp_table_align.set(0.5, 0.5, 1.0, 1.0)
		self.exp_table_align.add(self.exp_table)
		self.exp_frame.add(self.exp_table_align)
		#********************************************************************
		#           Data conversion information
		#********************************************************************
		self.conv_table = gtk.Table(6,3,False)
		
		self.c1 = gtk.Label("Spec file")
		self.c2 = gtk.Label("MCA file")
		self.c3 = gtk.Label("Destination folder")
		self.c4 = gtk.Label("Scan number (from-to)")
		self.c5 = gtk.Label("Description for each RSM (optional-separate by comma)")
		self.c6 = gtk.Label("Problem of foil delay (foil[n]-->data[n+1])")
		
		self.c1.set_alignment(0,0.5)
		self.c2.set_alignment(0,0.5)
		self.c3.set_alignment(0,0.5)
		self.c4.set_alignment(0,0.5)
		self.c5.set_alignment(0,0.5)
		self.c6.set_alignment(0,0.5)
		
		self.c1_entry1 = gtk.Entry()
		self.c2_entry1 = gtk.Entry()
		self.c3_entry1 = gtk.Entry()
		self.c4_entry1 = gtk.Entry()
		self.c5_entry1 = gtk.Entry()
		self.c5_entry1.set_text("")
		self.c6_entry = gtk.CheckButton()
		
		self.c1_entry2 = gtk.Button("Browse SPEC")
		self.c2_entry2 = gtk.Button("Browse MCA")
		self.c3_entry2 = gtk.Button("Browse Folder")
		self.c4_entry2 = gtk.Entry()
		
		self.c1_entry2.connect("clicked", self.select_file, self.c1_entry1, "S")
		self.c2_entry2.connect("clicked", self.select_file, self.c2_entry1, "M")
		self.c3_entry2.connect("clicked", self.select_folder, self.c3_entry1, "D")
		
		self.conv_table.attach(self.c1, 0,1,0,1)
		self.conv_table.attach(self.c2, 0,1,1,2)
		self.conv_table.attach(self.c3, 0,1,2,3)
		self.conv_table.attach(self.c4, 0,1,3,4)
		self.conv_table.attach(self.c5, 0,1,4,5)
		self.conv_table.attach(self.c6, 0,1,5,6)
		
		self.conv_table.attach(self.c1_entry1, 1,2,0,1)
		self.conv_table.attach(self.c2_entry1, 1,2,1,2)
		self.conv_table.attach(self.c3_entry1, 1,2,2,3)
		self.conv_table.attach(self.c4_entry1, 1,2,3,4)
		self.conv_table.attach(self.c5_entry1, 1,3,4,5)
		self.conv_table.attach(self.c6_entry, 1,2,5,6)
		
		self.conv_table.attach(self.c1_entry2, 2,3,0,1)
		self.conv_table.attach(self.c2_entry2, 2,3,1,2)
		self.conv_table.attach(self.c3_entry2, 2,3,2,3)
		self.conv_table.attach(self.c4_entry2, 2,3,3,4)
		
		self.conv_table_align = gtk.Alignment()
		self.conv_table_align.set_padding(15,10,10,10)
		self.conv_table_align.set(0.5, 0.5, 1.0, 1.0)
		self.conv_table_align.add(self.conv_table)
		self.conv_frame.add(self.conv_table_align)
		#********************************************************************
		#           The RUN button
		#********************************************************************
		self.run_conversion = gtk.Button("Execute")
		self.run_conversion.connect("clicked", self.spec2HDF)
		self.run_conversion.set_size_request(50,30)
		self.show_info = gtk.Label()
		#********************************************************************
		#           Pack the frames
		#********************************************************************
		self.box1.pack_start(self.det_frame,padding=15)
		self.box1.pack_end(self.exp_frame, padding =15)
		self.conv_box.pack_start(self.box1,padding=15)
		self.conv_box.pack_start(self.conv_frame,padding=5)
		self.conv_box.pack_start(self.run_conversion, False,False,10)
		self.conv_box.pack_start(self.show_info, False,False,10)
		self.page_conversion.pack_start(self.conv_box,False, False,20)
		#********************************************************************
		#          Conversion XRDML data to HDF
		#********************************************************************
		self.XRDML_conv_box = gtk.VBox()
		self.Instrument_table = gtk.Table(1,4,True)
		self.Inst_txt = gtk.Label("Instrument:")
		self.Inst_txt.set_alignment(0,0.5)
		self.Instrument = gtk.combo_box_new_text()
		self.Instrument.append_text("Bruker")
		self.Instrument.append_text("PANalytical")
		self.Instrument.set_active(0)
		self.Instrument_table.attach(self.Inst_txt,0,1,0,1)
		self.Instrument_table.attach(self.Instrument, 1,2,0,1)
		self.Instrument.connect("changed",self.Change_Lab_Instrument)
		self.choosen_instrument = self.Instrument.get_active_text()
		
		self.XRDML_table = gtk.Table(7,4,True)
		self.XRDML_tooltip = gtk.Tooltips()
		
		self.XRDML_substrate_txt  = gtk.Label("Substrate material:")
		self.XRDML_substrate_other_txt  = gtk.Label("If other:")
		self.XRDML_substrate_inplane_txt= gtk.Label("In-plane direction (i.e. 1 1 0) - optional")
		self.XRDML_substrate_outplane_txt= gtk.Label("Out-of-plane direction (i.e. 0 0 1)-optional")
		self.XRDML_reflection_txt = gtk.Label("Reflection (H K L) - optional:")
		self.XRDML_energy_txt = gtk.Label("Energy (eV) - optional:")
		self.XRDML_description_txt = gtk.Label("Description of the sample:")
		self.XRDML_xrdml_file_txt  = gtk.Label("Select RAW file:")
		self.XRDML_destination_txt = gtk.Label("Select a destination folder:")
		
		self.XRDML_tooltip.set_tip(self.XRDML_substrate_txt, "Substrate material")
		self.XRDML_tooltip.set_tip(self.XRDML_substrate_other_txt, "The substrate material, i.e. Al, SiO2, CdTe, GaN,...")
		self.XRDML_tooltip.set_tip(self.XRDML_substrate_inplane_txt, "The substrate in-plane an out-of-plane direction - for calculation of the orientation matrix.")
		self.XRDML_tooltip.set_tip(self.XRDML_reflection_txt, "H K L, separate by space, i.e. 2 2 4 (0 0 0 for a XRR map). This is used for offset correction.")
		self.XRDML_tooltip.set_tip(self.XRDML_energy_txt, "If empty, the default Cu K_alpha_1 will be used.")
		self.XRDML_tooltip.set_tip(self.XRDML_description_txt, "Description of the sample, this will be the name of the converted file. If empty, it will be named 'RSM.h5'")
		self.XRDML_tooltip.set_tip(self.XRDML_xrdml_file_txt, "Select the data file recorded by the chosen equipment")
		self.XRDML_tooltip.set_tip(self.XRDML_destination_txt, "Select a destination folder to store the converted file.")
		
		self.XRDML_substrate_txt.set_alignment(0,0.5)
		self.XRDML_substrate_other_txt.set_alignment(1,0.5)
		self.XRDML_substrate_inplane_txt.set_alignment(0,0.5)
		self.XRDML_substrate_outplane_txt.set_alignment(1,0.5)
		self.XRDML_reflection_txt.set_alignment(0,0.5)
		self.XRDML_energy_txt.set_alignment(0,0.5)
		self.XRDML_description_txt.set_alignment(0,0.5)
		self.XRDML_xrdml_file_txt.set_alignment(0,0.5)
		self.XRDML_destination_txt.set_alignment(0,0.5)
		
		self.XRDML_substrate = gtk.combo_box_new_text()
		self.XRDML_substrate.append_text("-- other")
		self.XRDML_substrate.append_text("Si")
		self.XRDML_substrate.append_text("Ge")
		self.XRDML_substrate.append_text("GaAs")
		self.XRDML_substrate.append_text("GaP")
		self.XRDML_substrate.append_text("GaSb")
		self.XRDML_substrate.append_text("InAs")
		self.XRDML_substrate.append_text("InP")
		self.XRDML_substrate.append_text("InSb")
		self.XRDML_substrate.set_active(0)
		
		self.XRDML_substrate_other = gtk.Entry()
		self.XRDML_substrate_other.set_text("")
		self.XRDML_substrate_inplane = gtk.Entry()
		self.XRDML_substrate_inplane.set_text("")
		self.XRDML_substrate_outplane = gtk.Entry()
		self.XRDML_substrate_outplane.set_text("")
		
		self.XRDML_reflection = gtk.Entry()
		self.XRDML_reflection.set_text("")
		self.XRDML_energy = gtk.Entry()
		self.XRDML_energy.set_text("")
		self.XRDML_description = gtk.Entry()
		self.XRDML_description.set_text("")
		self.XRDML_xrdml_file_path = gtk.Entry()
		self.XRDML_destination_path = gtk.Entry()
		self.XRDML_xrdml_file_browse = gtk.Button("Browse RAW file")
		self.XRDML_destination_browse= gtk.Button("Browse destination folder")
		
		self.XRDML_xrdml_file_browse.connect("clicked", self.select_file, self.XRDML_xrdml_file_path, "S")
		self.XRDML_destination_browse.connect("clicked", self.select_folder, self.XRDML_destination_path, "D")
		
		self.XRDML_table.attach(self.XRDML_substrate_txt, 0,1,0,1)
		self.XRDML_table.attach(self.XRDML_substrate, 1,2,0,1)
		self.XRDML_table.attach(self.XRDML_substrate_other_txt, 2,3,0,1)
		self.XRDML_table.attach(self.XRDML_substrate_other, 3,4,0,1)
		
		self.XRDML_table.attach(self.XRDML_substrate_inplane_txt, 0,1,1,2)
		self.XRDML_table.attach(self.XRDML_substrate_inplane, 1,2,1,2)
		self.XRDML_table.attach(self.XRDML_substrate_outplane_txt, 2,3,1,2)
		self.XRDML_table.attach(self.XRDML_substrate_outplane, 3,4,1,2)
		
		self.XRDML_table.attach(self.XRDML_reflection_txt, 0,1,2,3)
		self.XRDML_table.attach(self.XRDML_reflection, 1,2,2,3)
		self.XRDML_table.attach(self.XRDML_energy_txt,0,1,3,4)
		self.XRDML_table.attach(self.XRDML_energy, 1,2,3,4)
		self.XRDML_table.attach(self.XRDML_description_txt, 0,1,4,5)
		self.XRDML_table.attach(self.XRDML_description, 1,2,4,5)
		self.XRDML_table.attach(self.XRDML_xrdml_file_txt, 0,1,5,6)
		self.XRDML_table.attach(self.XRDML_xrdml_file_path, 1,2,5,6)
		self.XRDML_table.attach(self.XRDML_xrdml_file_browse, 2,3,5,6)
		self.XRDML_table.attach(self.XRDML_destination_txt, 0,1,6,7)
		self.XRDML_table.attach(self.XRDML_destination_path, 1,2,6,7)
		self.XRDML_table.attach(self.XRDML_destination_browse, 2,3,6,7)
		#********************************************************************
		#           The RUN button
		#********************************************************************
		self.XRDML_run = gtk.Button("Execute")
		self.XRDML_run.connect("clicked", self.Convert_Lab_Source)
		self.XRDML_run.set_size_request(50,30)
		self.XRDML_show_info = gtk.Label()
		#********************************************************************
		#           Pack the XRDML options
		#********************************************************************
		self.XRDML_conv_box.pack_start(self.Instrument_table, False, False,5)
		self.XRDML_conv_box.pack_start(self.XRDML_table, False, False, 10)
		self.XRDML_conv_box.pack_start(self.XRDML_run, False, False, 5)
		self.XRDML_conv_box.pack_start(self.XRDML_show_info, False,False,10)
		
		self.page_XRDML.pack_start(self.XRDML_conv_box,False, False,20)
		#********************************************************************
		#          Pack the notebook
		#********************************************************************
		self.notebook.append_page(self.page_GUI, gtk.Label("RSM GUI"))
		self.notebook.append_page(self.page_conversion, gtk.Label("ESRF-MCA spec file (Vantec)"))
		self.notebook.append_page(self.page_XRDML, gtk.Label("Lab instruments"))
		
		hbox.pack_start(self.notebook)
		vbox.pack_start(hbox,True,True,0)

		############################### Sliders ######################################
		#sld_box = gtk.Fixed()
		sld_box = gtk.HBox(False,2)

		self.vmin_txt = gtk.Label("Vmin")
		self.vmin_txt.set_alignment(0,0.5)
		#self.vmin_txt.set_justify(gtk.JUSTIFY_CENTER)
		self.vmax_txt = gtk.Label("Vmax")
		self.vmax_txt.set_alignment(0,0.5)
		#self.vmax_txt.set_justify(gtk.JUSTIFY_CENTER)
		self.sld_vmin = gtk.HScale()
		self.sld_vmax = gtk.HScale()

		self.sld_vmin.set_size_request(200,25)
		self.sld_vmax.set_size_request(200,25)
		self.sld_vmin.set_range(0,self.vmax)
		self.sld_vmax.set_range(0,self.vmax)
		self.sld_vmax.set_value(self.vmax)
		self.sld_vmin.set_value(0)
		self.sld_vmin.connect('value-changed',self.scale_update)
		self.sld_vmax.connect('value-changed',self.scale_update)

		vmax_spin_adj         = gtk.Adjustment(self.vmax, 0, self.vmax_range, 0.5, 10.0, 0.0)
		self.vmax_spin_btn    = gtk.SpinButton(vmax_spin_adj,1,1)
		self.vmax_spin_btn.set_numeric(True)
		self.vmax_spin_btn.set_wrap(True)
		self.vmax_spin_btn.set_size_request(80,-1)
		#self.vmax_spin_btn.set_alignment(0,0.5)
		self.vmax_spin_btn.connect('value-changed',self.scale_update_spin)
		
		vmin_spin_adj         = gtk.Adjustment(self.vmin, 0, self.vmax_range, 0.5, 10.0, 0.0)
		self.vmin_spin_btn    = gtk.SpinButton(vmin_spin_adj,1,1)
		self.vmin_spin_btn.set_numeric(True)
		self.vmin_spin_btn.set_wrap(True)
		self.vmin_spin_btn.set_size_request(80,-1)
		#self.vmax_spin_btn.set_alignment(0,0.5)
		self.vmin_spin_btn.connect('value-changed',self.scale_update_spin)
		sld_box.pack_start(self.vmin_txt,False,False,0)
		sld_box.pack_start(self.sld_vmin,False,False,0)
		sld_box.pack_start(self.vmin_spin_btn,False,False,0)
		sld_box.pack_start(self.vmax_txt,False,False,0)
		sld_box.pack_start(self.sld_vmax,False,False,0)
		sld_box.pack_start(self.vmax_spin_btn,False,False,0)
		#sld_box.pack_start(self.slider_reset_btn,False,False,0)

		vbox.pack_start(sld_box,False,False,3)
		self.add(vbox)
		self.connect("destroy", gtk.main_quit)
		self.show_all()

#########################################################################################################################
	def format_coord(self, x, y):
		#***** Add intensity information into the navigation toolbar *******************************
		numrows, numcols = (self.gridder.data.T).shape
		col,row = xu.analysis.line_cuts.getindex(x, y, self.gridder.xaxis, self.gridder.yaxis)

		if col>=0 and col<numcols and row>=0 and row<numrows:
			z = self.gridder.data.T[row,col]
			return 'x=%1.4f, y=%1.4f, z=%1.4f'%(x, y, z)
		else:
			return 'x=%1.4f, y=%1.4f'%(x, y)
			
	def pro_format_coord(self,x,y):
		return 'x=%.4f, y=%.1f'%(x,y)
		
	def init_image(self,log=False):
		self.ax.cla()
		self.cax.cla()
		#print "Initialize image ..."
		#
		#self.clevels = np.linspace(self.vmin, self.vmax, 100)
		if log:
			self.img = self.ax.pcolormesh(self.gridder.xaxis, self.gridder.yaxis, np.log10(self.gridder.data.T),vmin=self.vmin, vmax=self.vmax)
			#self.img = self.ax.contour(self.gridder.xaxis, self.gridder.yaxis, np.log10(self.gridder.data.T), self.clevels, vmin=self.vmin, vmax=self.vmax)
		else:
			self.img = self.ax.pcolormesh(self.gridder.xaxis, self.gridder.yaxis, self.gridder.data.T,vmin=self.vmin, vmax=self.vmax)
			#self.img = self.ax.contour(self.gridder.xaxis, self.gridder.yaxis, self.gridder.data.T, self.clevels, vmin=self.vmin, vmax=self.vmax)
		
		self.img.cmap.set_under(alpha=0)
		self.ax.axis([self.gridder.xaxis.min(), self.gridder.xaxis.max(), self.gridder.yaxis.min(), self.gridder.yaxis.max()])
		#self.ax.set_aspect('equal')
		xlabel = r'$Q_x (nm^{-1})$'
		ylabel = r'$Q_z (nm^{-1})$'
		self.ax.set_xlabel(xlabel)
		self.ax.set_ylabel(ylabel)
		self.ax.yaxis.label.set_size(20)
		self.ax.xaxis.label.set_size(20)
		self.ax.set_title(self.rsm_description,fontsize=20)
		self.ax.format_coord = self.format_coord
		
		self.cb  = self.fig.colorbar(self.img, cax = self.cax, format="%.1f")#format=fm
		
		if self.log_scale==1:
			self.cb.set_label(r'$Log_{10}\ (Intensity)\ [arb.\ units]$',fontsize=20)
		else:
			self.cb.set_label(r'$Intensity\ (Counts\ per\ second)$', fontsize=20)
		
		self.cb.locator = MaxNLocator(nbins=6)
		#self.cursor = Cursor(self.ax, color='k', linewidth=1, useblit=True)
		#print "Image is initialized."
	def change_aspect_ratio(self,w):
		self.graph_aspect = not (self.graph_aspect)
		if self.graph_aspect == True:
			self.ax.set_aspect('equal')
		else:
			self.ax.set_aspect('auto')
		self.canvas.draw()
		
	
	def on_changed_rsm(self,widget,row,col):
		#print "************Change RSM*************"
		gc.collect() #Clear unused variables to gain memory
		#************** Remind the structure of these HDF5 files: 
		# ************* file=[scan_id={'eta'=[data], '2theta'=[data], 'intensity'=[data], 'description'='RSM 004 ...'}]
		self.clear_notes()
		#self.init_image()
		model = widget.get_model()
		self.rsm_choosen = model[row][0]
		
		self.rsm = join(self.GUI_current_folder,self.rsm_choosen)#file path
		self.rsm_info = h5.File(self.rsm,'r')#HDF5 object that collects all information of this scan
		#self.ax.set_title(self.rsm_choosen,fontsize=20)
		### Data Loading ##
		groups = self.rsm_info.keys()
		scan = groups[0]
		self.scan = self.rsm_info[scan]
		self.data = self.scan.get('intensity').value
		self.Qx  = self.scan.get('Qx').value
		self.Qy  = self.scan.get('Qy').value
		self.Qz  = self.scan.get('Qz').value
		self.rsm_description = self.scan.get('description').value
		self.rsm_info.close()
		#print "Data are successfully loaded."
		self.gridder = xu.Gridder2D(self.data.shape[0],self.data.shape[1])
		#print "Gridder is calculated."
#		MM  = self.data.max()
#		M = np.log10(MM)
#		data = flat_data(self.data,0,M)
		self.gridder(self.Qx, self.Qz, self.data)
		self.data = self.gridder.data.T
		
		self.vmin=self.data.min()
		self.vmax=self.data.max()
		#print "Starting scale_plot()"
		self.scale_plot()
		
		#self.slider_update()

	def scale_plot(self):
		#print "Scale_plot() is called."
		data = self.data.copy()
		#self.init_image()
		if self.linear_scale_btn.get_active():
			self.linear_scale_btn.set_label("--> Linear scale")
			data = np.log10(data)
			#print data.max()
			self.init_image(log=True)
			actual_vmin = self.sld_vmin.get_value()
			actual_vmax = self.sld_vmax.get_value()
			self.vmax = np.log10(actual_vmax) if self.log_scale == 0 else actual_vmax
			if actual_vmin == 0:
				self.vmin=0
			elif actual_vmin >0:
				self.vmin = np.log10(actual_vmin) if self.log_scale == 0 else actual_vmin
			self.vmax_range = data.max()
			self.log_scale = 1
			#log=True

		else:
			self.linear_scale_btn.set_label("--> Log scale")
			self.init_image(log=False)
			#print "Calculating min max and update slider..."
			actual_vmin = self.sld_vmin.get_value()
			actual_vmax = self.sld_vmax.get_value()
			#print "Actual vmax: ",actual_vmax
			if self.log_scale == 1:
				self.vmax = np.power(10.,actual_vmax)
			else:
				self.vmax = actual_vmax
			self.vmax_range = data.max()
			if actual_vmin ==0:
				self.vmin = 0
			elif actual_vmin>0:
				if self.log_scale == 0:
					self.vmin = actual_vmin
				elif self.log_scale == 1:
					self.vmin = np.power(10,actual_vmin)
			self.log_scale = 0
			#log=False
			#print "Min max are calculated."
		
		self.sld_vmax.set_range(-6,self.vmax_range)
		self.sld_vmin.set_range(-6,self.vmax_range)
		#self.init_image(log)
		self.slider_update()
		
	def log_update(self,widget):
		self.scale_plot()
		if self.log_scale==1:
			self.cb.set_label(r'$Log_{10}\ (Counts\ per\ second)\ [arb.\ units]$',fontsize=18)
		else:
			self.cb.set_label(r'$Intensity\ (Counts\ per\ second)$', fontsize=18)
		#self.slider_update()

	def scale_update(self,widget):
		#print "Scale_update() is called."
		self.vmin = self.sld_vmin.get_value()
		self.vmax = self.sld_vmax.get_value()
		self.vmin_spin_btn.set_value(self.vmin)
		self.vmax_spin_btn.set_value(self.vmax)
		self.slider_update()

	def scale_update_spin(self,widget):
		#print "Spin_update() is called"
		self.vmin = self.vmin_spin_btn.get_value()
		self.vmax = self.vmax_spin_btn.get_value()
		self.slider_update()

	def slider_update(self):
		#print "slider_update() is called"
		#self.img.set_clim(self.vmin, self.vmax)
		self.sld_vmax.set_value(self.vmax)
		self.sld_vmin.set_value(self.vmin)
		if self.linear_scale_btn.get_active():
			self.vmin_spin_btn.set_adjustment(gtk.Adjustment(self.vmin, 0, self.vmax_range, 0.1, 1.0, 0))
			self.vmax_spin_btn.set_adjustment(gtk.Adjustment(self.vmax, 0, self.vmax_range, 0.1, 1.0, 0))
		else:
			self.vmin_spin_btn.set_adjustment(gtk.Adjustment(self.vmin, 0, self.vmax_range, 10, 100, 0))
			self.vmax_spin_btn.set_adjustment(gtk.Adjustment(self.vmax, 0, self.vmax_range, 10, 100, 0))

		#self.vmax_spin_btn.update()
		self.img.set_clim(self.vmin, self.vmax)
		self.ax.relim()
		self.canvas.draw()
		#print "slider_update() stoped."

	def choose_folder(self, w):
		dialog = gtk.FileChooserDialog(title="Select a data folder",action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER, buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		dialog.set_current_folder(self.GUI_current_folder)
		response=dialog.run()

		if response==gtk.RESPONSE_OK:
			folder=dialog.get_filename()
			folder = folder.decode('utf8')
			folder_basename = folder.split("/")[-1]
			#print folder_basename
			self.store= [i for i in listdir(folder) if isfile(join(folder,i)) and i.endswith(".data") or i.endswith(".h5")]
			self.GUI_current_folder = folder
			#print store
			if len(self.store)>0:
				self.list_store.clear()
				for i in self.store:
					self.list_store.append([i])
				self.TVcolumn.set_title(folder_basename)
			else:
				pass
		else:
			pass
		dialog.destroy()

	def folder_update(self, w):
		folder = self.GUI_current_folder
		if folder is not os.getcwd():
			store= [i for i in listdir(folder) if isfile(join(folder,i)) and i.endswith(".data") or i.endswith(".h5")]
			self.store=[]
			self.list_store.clear()
			for i in store:
				self.list_store.append([i])
				self.store.append(i)

	def arbitrary_line_cut(self, x, y):
		#**** num: integer - number of points to be extracted
		#**** convert Q coordinates to pixel coordinates
		x0, y0 = xu.analysis.line_cuts.getindex(x[0], y[0], self.gridder.xaxis, self.gridder.yaxis)
		x1, y1 = xu.analysis.line_cuts.getindex(x[1], y[1], self.gridder.xaxis, self.gridder.yaxis)
		num = int(np.hypot(x1-x0, y1-y0)) #number of points that will be plotted 
		xi, yi = np.linspace(x0, x1, num), np.linspace(y0, y1, num)
		profiles_data_X = profiles_data_Y = scipy.ndimage.map_coordinates(self.gridder.data, np.vstack((xi,yi)))
		coor_X_export,coor_Y_export = np.linspace(x[0], x[1], num), np.linspace(y[0], y[1], num)
		#coor_X_export = np.sort(coor_X_export)
		#coor_Y_export = np.sort(coor_Y_export)
		return coor_X_export,coor_Y_export, profiles_data_X, profiles_data_Y
		
	def boundary_rectangles(self, x, y):
		""" 
		IN : x[0,1], y[0,1]: positions of the line cut (arbitrary direction)
		OUT: ROI rectangle: the rectangle in which the data will be taken
			 Bound rectangle: the limit values for Qx, Qz line cuts (min, max)
		"""
		x = np.asarray(x)
		y = np.asarray(y)
		alpha = np.arctan(abs((y[1]-y[0])/(x[1]-x[0]))) # inclined angle of the ROI w.r.t the horizontal line. Attention to the sign of alpha
		#print np.degrees(alpha)
		T  = self.largueur_int/2.
		if np.degrees(alpha)>55.0:
			inc_x = 1
			inc_y = 0
		else:
			inc_x = 0
			inc_y = 1
		y1 = y + T*inc_y
		y2 = y - T*inc_y
		x1 = x + T*inc_x
		x2 = x - T*inc_x
		#These positions are in reciprocal space units. The boundary order will be: 1-2-2-1
		roi_rect = [[y1[0],x1[0]],[y2[0],x2[0]],[y2[1],x2[1]],[y1[1],x1[1]],[y1[0],x1[0]]]
		roi_rect = path.Path(roi_rect)
		#***************** Get the corresponding index of these points ***************************
		i1,j1 = xu.analysis.line_cuts.getindex(x1[0], y1[0], self.gridder.xaxis, self.gridder.yaxis)
		i2,j2 = xu.analysis.line_cuts.getindex(x2[0], y2[0], self.gridder.xaxis, self.gridder.yaxis)
		i3,j3 = xu.analysis.line_cuts.getindex(x2[1], y2[1], self.gridder.xaxis, self.gridder.yaxis)
		i4,j4 = xu.analysis.line_cuts.getindex(x1[1], y1[1], self.gridder.xaxis, self.gridder.yaxis)
		roi_box = [[j1,i1],[j2,i2],[j3,i3],[j4,i4],[j1,i1]]
		roi_box = path.Path(roi_box)
		#******* Calculate the limit boundary rectangle
		y_tmp = np.vstack((y1, y2))
		x_tmp = np.vstack((x1, x2))
		y_min = y_tmp.min()
		y_max = y_tmp.max()
		x_min = x_tmp.min()
		x_max = x_tmp.max()
		bound_rect = [x_min, x_max, y_min, y_max]
		bound_rect = np.asarray(bound_rect)
		contours = roi_rect.vertices
		p=self.ax.plot(contours[:,1], contours[:,0], linewidth=1.5, color='white')
		self.polygons.append(p[0])
		self.canvas.draw()
		return roi_box, bound_rect
		
	def extract_roi_data(self, roi_box, bound_rect):
		#***** Extraction of the ROI defined by the ROI box ******************
		qx_min = bound_rect[0]
		qx_max = bound_rect[1]
		qz_min = bound_rect[2]
		qz_max = bound_rect[3]
		#***** Getting index of the boundary points in order to calculate the length of the extracted array
		ixmin, izmin = xu.analysis.line_cuts.getindex(qx_min, qz_min, self.gridder.xaxis, self.gridder.yaxis)
		ixmax, izmax = xu.analysis.line_cuts.getindex(qx_max, qz_max, self.gridder.xaxis, self.gridder.yaxis)
		x_steps = ixmax - ixmin +1
		z_steps = izmax - izmin +1
		
		qx_coor = np.linspace(qx_min, qx_max, x_steps)
		qz_coor = np.linspace(qz_min, qz_max, z_steps)
		
		ROI = np.zeros(shape=(x_steps))
		#****** Extract Qx line cuts ************************
		for zi in range(izmin, izmax+1):
			qx_int = self.gridder.data[ixmin:ixmax+1,zi]
			#****** if the point is inside the ROI box: point = 0
			inpoints = []
			for i in range(ixmin,ixmax+1):
				inpoint= roi_box.contains_point([zi,i])
				inpoints.append(inpoint)
			for b in range(len(inpoints)):
				if inpoints[b]==False:
					qx_int[b] = 0
			ROI = np.vstack((ROI, qx_int))
		
		ROI = np.delete(ROI, 0, 0) #Delete the first line which contains zeros
		#****** Sum them up! Return Qx, Qz projection zones and Qx,Qz intensity
		qx_ROI  = ROI.sum(axis=0)/ROI.shape[0]
		qz_ROI  = ROI.sum(axis=1)/ROI.shape[1]
		
		return qx_coor, qx_ROI, qz_coor, qz_ROI
		
		
	def plot_profiles(self, x, y, cross_line=True):
		if cross_line:
			"""Drawing lines where I want to plot profiles"""
			# ******** if this is not an arbitrary profile, x and y are not lists but just one individual point
			x=x[0]
			y=y[0]
			hline = self.ax.axhline(y, color='k', ls='--', lw=1)
			self.lines.append(hline)
			vline = self.ax.axvline(x, color='k', ls='--', lw=1)
			self.lines.append(vline)
			"""Getting data to be plotted"""
			self.coor_X_export, self.profiles_data_X = xu.analysis.line_cuts.get_qx_scan(self.gridder.xaxis, self.gridder.yaxis, self.gridder.data, y, qrange=self.largueur_int)
			self.coor_Y_export, self.profiles_data_Y = xu.analysis.line_cuts.get_qz_scan(self.gridder.xaxis, self.gridder.yaxis, self.gridder.data, x, qrange=self.largueur_int)
			xc = x
			yc = y
			""" Fitting information """
			ix,iy = xu.analysis.line_cuts.getindex(x, y, self.gridder.xaxis, self.gridder.yaxis)
			ix_left,iy = xu.analysis.line_cuts.getindex(x-self.fitting_width, y, self.gridder.xaxis, self.gridder.yaxis)
			qx_2_fit = self.coor_X_export[ix_left:ix*2-ix_left+1]
			qx_int_2_fit = self.profiles_data_X[ix_left:2*ix-ix_left+1]
			X_fitted_params, X_fitted_data = fit(qx_2_fit, qx_int_2_fit,xc, cross_line)
			####################axX.plot(qx_2_fit, qx_fit_data, color='red',linewidth=2)
			ix,iy_down = xu.analysis.line_cuts.getindex(x, y-self.fitting_width, self.gridder.xaxis, self.gridder.yaxis)
			qz_2_fit = self.coor_Y_export[iy_down:iy*2-iy_down+1]
			qz_int_2_fit = self.profiles_data_Y[iy_down:iy*2-iy_down+1]
			Y_fitted_params, Y_fitted_data = fit(qz_2_fit, qz_int_2_fit,yc, cross_line)
			####################axY.plot(qz_2_fit, qz_fit_data, color='red',linewidth=2)
		
		else:
			
			#**** extract arbitrary line cut
			#**** extract one single line cut:
			if not self.rectangle_profiles_btn.get_active():
				self.coor_X_export, self.coor_Y_export, self.profiles_data_X, self.profiles_data_Y = self.arbitrary_line_cut(x,y)
			else:
				roi_box,bound_rect = self.boundary_rectangles(x,y)
				self.coor_X_export, self.profiles_data_X, self.coor_Y_export, self.profiles_data_Y = self.extract_roi_data(roi_box, bound_rect)
				
			tmpX = np.sort(self.coor_X_export)
			tmpY = np.sort(self.coor_Y_export)
			xc = tmpX[self.profiles_data_X.argmax()]
			yc = tmpY[self.profiles_data_Y.argmax()]
			""" Fitting information """
			X_fitted_params, X_fitted_data = fit(self.coor_X_export, self.profiles_data_X, xc, not cross_line)
			Y_fitted_params, Y_fitted_data = fit(self.coor_Y_export, self.profiles_data_Y, yc, not cross_line)
			qx_2_fit = self.coor_X_export
			qz_2_fit = self.coor_Y_export
		""" Plotting profiles """
		self.profiles_ax1.cla()
		self.profiles_ax2.cla()
		self.profiles_ax1.format_coord = self.pro_format_coord
		self.profiles_ax2.format_coord = self.pro_format_coord
		#self.cursor_pro1 = Cursor(self.profiles_ax1, color='k', linewidth=1, useblit=True)
		#self.cursor_pro2 = Cursor(self.profiles_ax2, color='k', linewidth=1, useblit=True)
		
		self.profiles_ax1.plot(self.coor_Y_export, self.profiles_data_Y, color='blue', lw=3)
		self.profiles_ax1.plot(qz_2_fit, Y_fitted_data, color='red', lw=1.5, alpha=0.8)
		self.profiles_ax2.plot(self.coor_X_export, self.profiles_data_X, color='blue', lw=3)
		self.profiles_ax2.plot(qx_2_fit, X_fitted_data, color='red', lw=1.5, alpha=0.8)
		self.profiles_ax1.set_title("Qz profile", size=14)
		self.profiles_ax2.set_title("Qx profile", size=14)
		
		self.profiles_canvas.draw()
		# Show the fitted results
		self.Qz_fitted_y0.set_text("%.4f"%Y_fitted_params['y0'].value)
		self.Qz_fitted_xc.set_text("%.4f"%Y_fitted_params['xc'].value)
		self.Qz_fitted_A.set_text("%.4f"%Y_fitted_params['A'].value)
		self.Qz_fitted_w.set_text("%.4f"%Y_fitted_params['w'].value)
		self.Qz_fitted_mu.set_text("%.4f"%Y_fitted_params['mu'].value)
		
		self.Qx_fitted_y0.set_text("%.4f"%X_fitted_params['y0'].value)
		self.Qx_fitted_xc.set_text("%.4f"%X_fitted_params['xc'].value)
		self.Qx_fitted_A.set_text("%.4f"%X_fitted_params['A'].value)
		self.Qx_fitted_w.set_text("%.4f"%X_fitted_params['w'].value)
		self.Qx_fitted_mu.set_text("%.4f"%X_fitted_params['mu'].value)
		
		self.profiles_refresh()
		self.canvas.draw()

	def draw_pointed(self, x, y, finished=False):
		#if len(self.lines)>0:
		#	self.clear_notes()
		p=self.ax.plot(x,y,'ro')
		self.points.append(p[0])
		if finished:
			l=self.ax.plot(self.arb_lines_X, self.arb_lines_Y, '--',linewidth=1.5, color='white')
			self.lines.append(l[0])
		self.canvas.draw()
	
	def profiles_refresh(self):
		""" """
		if self.profiles_log_btn.get_active():
			self.profiles_ax1.set_yscale('log')
			self.profiles_ax2.set_yscale('log')

		else:
			self.profiles_ax1.set_yscale('linear')
			self.profiles_ax2.set_yscale('linear')

		self.profiles_canvas.draw()
		#return
		
	def profiles_update(self, widget):
		self.profiles_refresh()
		
	def profiles_export(self,widget):
		""" Export X,Y profiles data in the same folder as the EDF image """
		proX_fname = self.rsm.split(".")[0]+"_Qx_profile.dat"
		proY_fname = self.rsm.split(".")[0]+"_Qz_profile.dat"
		proX_export= np.vstack([self.coor_X_export, self.profiles_data_X])
		proX_export=proX_export.T
		proY_export= np.vstack([self.coor_Y_export, self.profiles_data_Y])
		proY_export=proY_export.T
		try:
			np.savetxt(proX_fname, proX_export)
			np.savetxt(proY_fname, proY_export)
			self.popup_info('info','Data are successfully exported!')

		except:
			self.popup_info('error','ERROR! Data not exported!')

	def on_press(self, event):
		#********************  Plot X,Y cross profiles ***************************************************
		if (event.inaxes == self.ax) and (event.button==3) and self.plotXYprofiles_btn.get_active():
			x = event.xdata
			y = event.ydata
			xx=[]
			yy=[]
			xx.append(x)
			yy.append(y)
			self.clear_notes()
			
			try:
				self.largueur_int = float(self.int_range.get_text())
				self.fitting_width = float(self.fitting_range.get_text())
				self.plot_profiles(xx,yy,cross_line=True)
			except:
				self.popup_info("error","Please check that you have entered all the parameters correctly !")
			
		#********************  Plot arbitrary profiles ***************************************************
		elif (event.inaxes == self.ax) and (event.button==1) and (self.arbitrary_profiles_btn.get_active() or self.rectangle_profiles_btn.get_active()):
			#self.clear_notes()
			try:
				self.largueur_int = float(self.int_range.get_text())
				self.fitting_width = float(self.fitting_range.get_text())
			except:
				self.popup_info("error","Please check that you have entered all the parameters correctly !")
			
			self.arb_line_points +=1
			#print "Number of points clicked: ",self.arb_line_points
			if self.arb_line_points>2:
				self.clear_notes()
				self.arb_line_points=1
			
			x = event.xdata
			y = event.ydata
			self.arb_lines_X.append(x)
			self.arb_lines_Y.append(y)
			if len(self.arb_lines_X)<2:
				finished=False
			elif len(self.arb_lines_X)==2:
				finished = True
			
			self.draw_pointed(x,y,finished)#If finished clicking, connect the two points by a line
			if finished:
				self.plot_profiles(self.arb_lines_X, self.arb_lines_Y, cross_line=False)
				self.arb_lines_X=[]
				self.arb_lines_Y=[]
			#self.canvas.draw()

		#********************  Clear cross lines in the main image ****************************************
		elif event.button==2:
			self.clear_notes()
		
	def profile_press(self, event):
		""" Calculate thickness fringes """
		if event.inaxes == self.profiles_ax1:
			draw_fringes = True
			ax = self.profiles_ax1
			X_data = self.coor_Y_export
			Y_data = self.profiles_data_Y
			xlabel = r'$Q_z (nm^{-1})$'
			title = "Linear regression of Qz fringes"
			title_FFT = "Fast Fourier Transform of Qz profiles"
			xlabel_FFT= "Period (nm)"
		elif event.inaxes == self.profiles_ax2:
			draw_fringes = True
			ax = self.profiles_ax2
			X_data = self.coor_X_export
			Y_data = self.profiles_data_X
			xlabel = r'$Q_x (nm^{-1})$'
			title = "Linear regression of Qx fringes"
			title_FFT = "Fast Fourier Transform of Qx profiles"
			xlabel_FFT= "Period (nm)"
		else:
			draw_fringes = False
			
		if draw_fringes and (event.button==1):
			if len(self.profiles_fringes)>0:
				self.profiles_fringes = np.asarray(self.profiles_fringes)
				self.profiles_fringes = np.sort(self.profiles_fringes)
				fringes_popup = PopUpFringes(self.profiles_fringes, xlabel, "Fringes order", title)
				self.profiles_fringes=[]
				self.clear_notes()
		elif draw_fringes and (event.button == 3):
			vline=ax.axvline(event.xdata, linewidth=2, color="green")
			self.lines.append(vline)
			self.profiles_fringes.append(event.xdata)
		
		elif draw_fringes and event.button == 2:
			XF,YF = Fourier(X_data, Y_data)
			popup_window=PopUpImage(XF, YF, xlabel_FFT, "Normalized intensity", title_FFT)
			
		self.profiles_canvas.draw()
		
		#plt.clf()
		
	def clear_notes(self):
		"""
		print "Number of notes: ",len(self.my_notes)
		print "Number of lines: ",len(self.lines)
		print "Number of points: ",len(self.points)
		print "Number of polygons: ",len(self.polygons)
		"""
		if len(self.my_notes)>0:
			for txt in self.my_notes:
				txt.remove()
				
		if len(self.lines)>0:
			for line in self.lines:
				line.remove()
				
		if len(self.points)>0:
			for p in self.points:
				p.remove()
		if len(self.polygons)>0:
			for p in self.polygons:
				p.remove()
		self.canvas.draw()
		self.my_notes = []
		#self.profiles_notes = []
		self.lines=[]
		self.points=[]
		self.polygons=[]
		self.arb_lines_X=[]
		self.arb_lines_Y=[]
		self.arb_line_points = 0


	def on_motion(self,event):
		print "Mouse moved !"
		if event.inaxes == self.ax and self.arbitrary_profiles_btn.get_active() and self.arb_line_points==1:
			x = event.xdata
			y = event.ydata
			self.clear_notes()
			line = self.ax.plot([self.arb_lines_X[0], x], [self.arb_lines_Y[0],y], 'ro-')
			self.lines.append(line)
			self.canvas.draw()


	def on_release(self, event):
		if event.inaxes == self.ax:
			if self.mouse_moved==True:
				self.mouse_moved = False

	def popup_info(self,info_type,text):
		""" info_type = WARNING, INFO, QUESTION, ERROR """
		if info_type.upper() == "WARNING":
			mess_type = gtk.MESSAGE_WARNING
		elif info_type.upper() == "INFO":
			mess_type = gtk.MESSAGE_INFO
		elif info_type.upper() == "ERROR":
			mess_type = gtk.MESSAGE_ERROR
		elif info_type.upper() == "QUESTION":
			mess_type = gtk.MESSAGE_QUESTION

		self.warning=gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT, mess_type, gtk.BUTTONS_CLOSE,text)
		self.warning.run()
		self.warning.destroy()
		
	#********************************************************************
	#           Functions for the Spec-HDF5 data conversion
	#********************************************************************
	def select_file(self,widget,path,label):
		dialog = gtk.FileChooserDialog("Select file",None,gtk.FILE_CHOOSER_ACTION_OPEN,(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		dialog.set_current_folder(self.DATA_current_folder)
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			file_choosen = dialog.get_filename()
			path.set_text(file_choosen)
			self.DATA_current_folder = os.path.dirname(file_choosen)
			if label == "A":
				self.attenuation_file = file_choosen.decode('utf8')
			elif label == "S":
				self.spec_file = file_choosen.decode('utf8')
			elif label == "M":
				self.mca_file = file_choosen.decode('utf8')
		else:
			pass
		dialog.destroy()
		
	def select_folder(self, widget, path, label):
		dialog = gtk.FileChooserDialog(title="Select folder",action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER, buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		dialog.set_current_folder(self.DATA_current_folder)
		response=dialog.run()
		if response==gtk.RESPONSE_OK:
			folder=dialog.get_filename()
			path.set_text(folder)
			self.DATA_current_folder = folder.decode('utf8')
			if label == "D":
				self.des_folder = folder.decode('utf8')
		else:
			pass
		dialog.destroy()
	
	def HKL2Q(self,H,K,L,a):
		""" Q// est dans la direction [110], Qz // [001]"""
		Qx = H*np.sqrt(2.)/a
		Qy = K*np.sqrt(2.)/a
		Qz = L/a
		return [Qx, Qy, Qz]
	
	def loadAmap(self,scanid,specfile,mapData,retard):
		try:
			psdSize     = float(self.t1_entry.get_text())
			Nchannels   = int(self.t2_entry.get_text())
			psdMin      = int(self.t5_entry1.get_text())
			psdMax      = int(self.t5_entry2.get_text())
			psd0        = float(self.t3_entry.get_text())
			pixelSize   = psdSize/Nchannels
			pixelPerDeg = float(self.t4_entry.get_text())
			distance    = pixelSize * pixelPerDeg / np.tan(np.radians(1.0)) # sample-detector distance in mm	
			psdor       = self.t6_entry.get_active()       #psd orientation (up, down, in, out)
			if psdor == 0:
				psdor = 'z+'
			elif psdor == 1:
				psdor = 'z-'
			else:
				psdor = 'unknown'
			energy      = float(self.e2_entry.get_text())
			filter_data = self.attenuation_file
			monitor_col = self.e5_entry.get_text()
			foil_col    = self.e4_entry.get_text()
			monitor_ref = float(self.e6_entry.get_text())
			#****************** Calculation ************************
			headers, scan_kappa = SP.ReadSpec(specfile,scanid)
			Eta = scan_kappa['Eta']
			print Eta.shape
			tth = headers['P'][0]
			omega = headers['P'][1]
			tth = float(tth)
			omega = float(omega)
			
			print "Del: %.2f, Eta: %.2f"%(tth,omega)
			#Si = xu.materials.Si
			hxrd = xu.HXRD(self.substrate.Q(self.in_plane), self.substrate.Q(self.out_of_plane), en = energy)
			hxrd.Ang2Q.init_linear(psdor,psd0, Nchannels, distance=distance, pixelwidth=pixelSize, chpdeg=pixelPerDeg)
			HKL = hxrd.Ang2HKL(omega, tth)
			HKL = np.asarray(HKL)
			HKL = HKL.astype(int)
			print "HKL = ",HKL
			
			H=K=L=np.zeros(shape=(0,Nchannels))
			for i in range(len(Eta)):
				om=Eta[i]
				q=hxrd.Ang2HKL(om,tth,mat=self.substrate,dettype='linear')
				H = np.vstack((H,q[0]))
				K = np.vstack((K,q[1]))
				L = np.vstack((L,q[2]))
			
			filtre_foil = scan_kappa[foil_col]
			filtre = filtre_foil.copy()
			monitor= scan_kappa[monitor_col]
			
			foil_data = np.loadtxt(filter_data)
			
			for f in xrange(foil_data.shape[0]):
				coef = filtre_foil == f
				filtre[coef] = foil_data[f,1]
			#print filtre
			mapData = mapData + 1e-6
			
			if retard:
				for i in range(len(filtre)-1):
					mapData[i+1] = mapData[i+1]*filtre[i]
			else:
				for i in range(len(filtre)):
					mapData[i] = mapData[i]*filtre[i]
			
			for i in range(len(monitor)):
				mapData[i] = mapData[i]*monitor_ref/monitor[i]
			
			mapData = mapData[:,psdMin:psdMax]
			H = H[:,psdMin:psdMax]
			K = K[:,psdMin:psdMax]
			L = L[:,psdMin:psdMax]
			
			########## Correction d'offset ###############
			x,y=np.unravel_index(np.argmax(mapData),mapData.shape)
			H_sub = H[x,y]
			K_sub = K[x,y]
			L_sub = L[x,y]
			H_offset = HKL[0] - H_sub
			K_offset = HKL[1] - K_sub
			L_offset = HKL[2] - L_sub
			
			H = H + H_offset
			K = K + K_offset
			L = L + L_offset
			a = self.substrate._geta1()[0] #in Angstrom
			a = a/10.
			Q = self.HKL2Q(H, K, L, a)
			return Q,mapData
		except:
			self.popup_info("warning", "Please make sure that you have correctly entered the all parameters.")
			return None,None
	
	def gtk_waiting(self):
		while gtk.events_pending():
			gtk.main_iteration()
	def Change_Lab_Instrument(self, widget):
		self.choosen_instrument = self.Instrument.get_active_text()
		print "I choose ",self.choosen_instrument
		if self.choosen_instrument == "Bruker":
			self.XRDML_xrdml_file_txt.set_text("Select RAW file: ")
			self.XRDML_xrdml_file_browse.set_label("Browse RAW file")
		elif self.choosen_instrument == "PANalytical":
			self.XRDML_xrdml_file_txt.set_text("Select XRDML file: ")
			self.XRDML_xrdml_file_browse.set_label("Browse XRDML file")
			
	def Convert_Lab_Source(self, widget):
		print "Instrument chosen: ",self.choosen_instrument
		energy     = self.XRDML_energy.get_text()
		if energy == "":
			energy = 8048
		else:
			energy = float(energy)
		
		self.lam = xu.lam2en(energy)/10
		HKL = self.XRDML_reflection.get_text()
		if HKL == "":
			self.offset_correction = False
		else:
			self.offset_correction = True
			HKL = HKL.split()
			HKL = np.asarray([int(i) for i in HKL])
		self.HKL = HKL
		substrate = self.XRDML_substrate.get_active_text()
		if substrate == "-- other":
			substrate = self.XRDML_substrate_other.get_text()
		command = "self.substrate = xu.materials."+substrate
		exec(command)
		in_plane = self.XRDML_substrate_inplane.get_text()
		out_of_plane = self.XRDML_substrate_outplane.get_text()
		if in_plane != "" and out_of_plane != "":
			in_plane = in_plane.split()
			self.in_plane = np.asarray([int(i) for i in in_plane])
			out_of_plane = out_of_plane.split()
			self.out_of_plane = np.asarray([int(i) for i in out_of_plane])
			self.has_orientation_matrix = True
			self.experiment = xu.HXRD(self.substrate.Q(self.in_plane),self.substrate.Q(self.out_of_plane), en=energy)
		else:
			self.has_orientation_matrix = False
			self.experiment = xu.HXRD(self.substrate.Q(1,1,0),self.substrate.Q(0,0,1), en=energy)
			
		if self.choosen_instrument == "Bruker":
			self.Bruker2HDF()
		elif self.choosen_instrument == "PANalytical":
			self.XRDML2HDF()
	
	def XRDML2HDF(self):
		try:
			xrdml_file = self.spec_file
			
			a = self.substrate._geta1()[0] #in Angstrom
			a = a/10.
			
			description = self.XRDML_description.get_text()
			self.XRDML_show_info.set_text("Reading XRDML data ...")
			self.gtk_waiting()
			
			dataFile = xu.io.XRDMLFile(xrdml_file)
			scan = dataFile.scan
			omega_exp = scan['Omega']
			tth_exp   = scan['2Theta']
			data  = scan['detector']
			if self.has_orientation_matrix:
				omega,tth,psd = xu.io.getxrdml_map(xrdml_file)
				[qx,qy,qz] = self.experiment.Ang2Q(omega, tth)
				mapData = psd.reshape(data.shape)
				H = qy.reshape(data.shape)
				K = qy.reshape(data.shape)
				L = qz.reshape(data.shape)
			else:
				mapData = data
				psi = omega_exp - tth_exp/2.
				Qmod= 2.*np.sin(np.radians(tth_exp/2.))/self.lam
				Qx  = Qmod * np.sin(np.radians(psi))
				Qz  = Qmod * np.cos(np.radians(psi))
				H=K = Qx*a/np.sqrt(2.0)
				L   = Qz*a
			########## Correction d'offset ###############
			if self.offset_correction:
				x,y=np.unravel_index(np.argmax(mapData),mapData.shape)
				H_sub = H[x,y]
				K_sub = K[x,y]
				L_sub = L[x,y]
				H_offset = self.HKL[0] - H_sub
				K_offset = self.HKL[1] - K_sub
				L_offset = self.HKL[2] - L_sub
				
				H = H + H_offset
				K = K + K_offset
				L = L + L_offset
			
			Q = self.HKL2Q(H, K, L, a)
			self.XRDML_show_info.set_text("XRDML data are successfully loaded.")
			self.gtk_waiting()
			
			if description == "":
				no_description = True
				description = "XRDML_Map"
			else:
				no_description = False
			
			h5file = description+".h5"
			info = "\nSaving file: %s"%(h5file)
			self.XRDML_show_info.set_text(info)
			self.gtk_waiting()
			h5file     = join(self.des_folder,h5file)
			if os.path.isfile(h5file):
				del_file = "rm -f %s"%h5file
				os.system(del_file)
			h5file     = h5.File(h5file,"w")
			
			s = h5file.create_group(description)
			s.create_dataset('intensity', data=mapData, compression='gzip', compression_opts=9)
			s.create_dataset('Qx', data=Q[0], compression='gzip', compression_opts=9)
			s.create_dataset('Qy', data=Q[1], compression='gzip', compression_opts=9)
			s.create_dataset('Qz', data=Q[2], compression='gzip', compression_opts=9)
			s.create_dataset('description', data=description)
		
			h5file.close()
			
			self.popup_info("info","Data conversion completed!")
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			self.popup_info("warning", "ERROR: %s"%str(exc_value))
	
	def Bruker2HDF(self):
		try:
			raw_file = self.spec_file
			from lib.Bruker import convert_raw_to_uxd,get_Bruker
			uxd_file = raw_file.split(".")[0]+".uxd"
			convert_raw_to_uxd(raw_file, uxd_file)
			
			description = self.XRDML_description.get_text()
			
			self.XRDML_show_info.set_text("Reading Raw data ...")
			self.gtk_waiting()

			a    = self.substrate._geta1()[0] #in Angstrom
			a    = a/10.
			dataset = get_Bruker(uxd_file)
			theta   = dataset['omega']
			dTheta  = dataset['tth']
			Qhkl    = self.experiment.Ang2HKL(theta, dTheta)
			Qx,Qy,Qz = Qhkl[0],Qhkl[1],Qhkl[2]
			########## Correction d'offset ###############
			if self.offset_correction:
				x,y=np.unravel_index(np.argmax(dataset['data']),dataset['data'].shape)
				Hsub = Qhkl[0][x,y]
				Ksub = Qhkl[1][x,y]
				Lsub = Qhkl[2][x,y]
				Qx = Qhkl[0]+self.HKL[0]-Hsub
				Qy = Qhkl[1]+self.HKL[1]-Ksub
				Qz = Qhkl[2]+self.HKL[2]-Lsub
			
			Q = self.HKL2Q(Qx, Qy, Qz, a)
			self.XRDML_show_info.set_text("Raw data are successfully loaded.")
			self.gtk_waiting()
			
			if description == "":
				no_description = True
				description = "RSM"
			else:
				no_description = False
			
			h5file = description+".h5"
			info = "\nSaving file: %s"%(h5file)
			self.XRDML_show_info.set_text(info)
			self.gtk_waiting()
			h5file     = join(self.des_folder,h5file)
			if os.path.isfile(h5file):
				del_file = "rm -f %s"%h5file
				os.system(del_file)
			h5file     = h5.File(h5file,"w")
			
			s = h5file.create_group(description)
			s.create_dataset('intensity', data=dataset['data'], compression='gzip', compression_opts=9)
			s.create_dataset('Qx', data=Q[0], compression='gzip', compression_opts=9)
			s.create_dataset('Qy', data=Q[1], compression='gzip', compression_opts=9)
			s.create_dataset('Qz', data=Q[2], compression='gzip', compression_opts=9)
			s.create_dataset('description', data=description)
		
			h5file.close()
			
			self.popup_info("info","Data conversion completed!")
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			self.popup_info("warning", "ERROR: %s"%str(exc_value))
	def spec2HDF(self,widget):
		try:
			specfile = self.spec_file
			mcafile  = self.mca_file
			scan_beg = int(self.c4_entry1.get_text())
			scan_end = int(self.c4_entry2.get_text())
			substrate = self.e1_entry.get_active_text()
			if substrate == "-- other":
				substrate = self.e1_entry_other.get_text()
			command = "self.substrate = xu.materials."+substrate
			exec(command)
			scanid = range(scan_beg, scan_end+1)
			self.show_info.set_text("Reading MCA data ...")
			self.gtk_waiting()
			allMaps = SP.ReadMCA2D_complete(mcafile)
			description = self.c5_entry1.get_text()
			retard = self.c6_entry.get_active()
			total = len(allMaps)
			total_maps_loaded = "Number of map(s) loaded: %d"%total
			self.show_info.set_text(total_maps_loaded)
			self.gtk_waiting()
			if description == "":
				no_description = True
			else:
				description = description.split(",")
				no_description = False
			for i in range(len(allMaps)):
				scannumber = scanid[i]
				scan_name  = "Scan_%d"%scannumber
				if no_description:
					h5file     = scan_name+".h5"
					d = scan_name
				else:
					h5file = description[i].strip()+".h5"
					d = description[i].strip()
				info = "\nSaving file N# %d/%d: %s"%(i+1,total,h5file)
				out_info = total_maps_loaded + info
				self.show_info.set_text(out_info)
				self.gtk_waiting()
				h5file     = join(self.des_folder,h5file)
				if os.path.isfile(h5file):
					del_file = "rm -f %s"%h5file
					os.system(del_file)
				h5file     = h5.File(h5file,"w")
				Q,mapdata = self.loadAmap(scannumber, specfile, allMaps[i], retard)
				s = h5file.create_group(scan_name)
				s.create_dataset('intensity', data=mapdata, compression='gzip', compression_opts=9)
				s.create_dataset('Qx', data=Q[0], compression='gzip', compression_opts=9)
				s.create_dataset('Qy', data=Q[1], compression='gzip', compression_opts=9)
				s.create_dataset('Qz', data=Q[2], compression='gzip', compression_opts=9)
				s.create_dataset('description', data=d)
			
				h5file.close()
			
			self.popup_info("info","Data conversion completed!")
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			self.popup_info("warning", "ERROR: %s"%str(exc_value))
	
	def Export_HQ_Image(self, widget):
		dialog = gtk.FileChooserDialog(title="Save image", action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_OK))
		filename = self.rsm_choosen.split(".")[0] if self.rsm_choosen != "" else "Img"
		dialog.set_current_name(filename+".png")
		#dialog.set_filename(filename)
		dialog.set_current_folder(self.GUI_current_folder)
		filtre = gtk.FileFilter()
		filtre.set_name("images")
		filtre.add_pattern("*.png")
		filtre.add_pattern("*.jpg")
		filtre.add_pattern("*.pdf")
		filtre.add_pattern("*.ps")
		filtre.add_pattern("*.eps")
		dialog.add_filter(filtre)
		filtre = gtk.FileFilter()
		filtre.set_name("Other")
		filtre.add_pattern("*")
		dialog.add_filter(filtre)
		response = dialog.run()

		if response==gtk.RESPONSE_OK:
			#self.fig.savefig(dialog.get_filename())
			xlabel = r'$Q_x (nm^{-1})$'
			ylabel = r'$Q_z (nm^{-1})$'
			fig   = plt.figure(figsize=(10,8),dpi=100)
			ax  = fig.add_axes([0.12,0.2,0.7,0.7])
			cax = fig.add_axes([0.85,0.2,0.03,0.7])
			clabel = r'$Intensity\ (Counts\ per\ second)$'
			fmt = "%d"
			if self.linear_scale_btn.get_active():
				clabel = r'$Log_{10}\ (Intensity)\ [arb.\ units]$'
				fmt = "%.2f"
			data = self.gridder.data.T
			data = flat_data(data, self.vmin, self.vmax, self.linear_scale_btn.get_active())
			img = ax.contourf(self.gridder.xaxis, self.gridder.yaxis, data, 100, vmin=self.vmin*1.1, vmax=self.vmax)
			cb = fig.colorbar(img,cax=cax, format=fmt)
			cb.set_label(clabel, fontsize=20)
			ax.set_xlabel(xlabel)
			ax.set_ylabel(ylabel)
			ax.yaxis.label.set_size(20)
			ax.xaxis.label.set_size(20)
			ax.set_title(self.rsm_description,fontsize=20)
			fig.savefig(dialog.get_filename())
			plt.close()
		dialog.destroy()

if __name__=="__main__":
	MyMainWindow()
	gtk.main()
