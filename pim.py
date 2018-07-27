#####################################
########  Process SIM Module ########
#####################################

import re

import pandas as pd
import xlsxwriter


### Process SIM functions ###
def create_pv_a_dict():
	"""
	Initializes a dictionary of dataframes for the PV-A report

	Args: None
	-----

	Returns:
	-----
		pv_a_dict(dict of pd.DataFrame): a dictionary of dataframes to collect
			the PV-A reports

	Requires:
	-----
		import pandas as pd

	"""

	pv_a_dict = {}

	###### CIRCULATION LOOPS
	loop_string = 'CIRCULATION LOOPS'
	loop_info_cols = ['Heating Cap. (mmBTU/hr)',
	                  'Cooling Cap. (mmBTU/hr)',
	                  'Loop Flow (GPM)',
	                  'Total Head (ft)',
	                  'Supply UA (BTU/h.F)',
	                  'Supply Loss DT (F)',
	                  'Return UA (BTU/h.F)',
	                  'Return Loss DT (F)',
	                  'Loop Volume (gal)',
	                  'Fluid Heat Cap. (BTU/lb.F)']
	df = pd.DataFrame(columns=loop_info_cols)
	df.index.name = 'Circulation Loop'
	pv_a_dict[loop_string] = df

	###### PUMPS
	pump_string = 'PUMPS'
	pump_info_cols = ['Attached to',
	                  'Flow (GPM)',
	                  'Head (ft)',
	                  'Head Setpoint (ft)',
	                  'Capacity Control',
	                  'Power (kW)',
	                  'Mech. Eff',
	                  'Motor Eff']
	df = pd.DataFrame(columns=pump_info_cols)
	df.index.name = 'Pump'
	pv_a_dict[pump_string] = df

	###### PRIMARY EQUIPMENT (Chillers, boilers)
	primary_string = 'PRIMARY EQUIPMENT'
	primary_info_cols = ['Equipment Type',
	                     'Attached to',
	                     'Capacity (mmBTU/hr)',
	                     'Flow (GPM)',
	                     'EIR',
	                     'HIR',
	                     'Aux. (kW)']
	df = pd.DataFrame(columns=primary_info_cols)
	df.index.name = 'Primary Equipment'
	pv_a_dict[primary_string] = df

	###### COOLING TOWERS
	ct_string = 'COOLING TOWERS'
	ct_info_cols = ['Equipment Type',
	                'Attached to',
	                'Cap. (mmBTU/hr)',
	                'Flow (GPM)',
	                'Nb of Cells',
	                'Fan Power per Cell (kW)',
	                'Spray Power per Cell (kW)',
	                'Aux. (kW)']
	df = pd.DataFrame(columns=ct_info_cols)
	df.index.name = 'Cooling Tower'
	pv_a_dict[ct_string] = df

	###### DHW Heaters
	dhw_string = 'DW-HEATERS'
	dhw_info_cols = ['Equipment Type',
	                 'Attached to',
	                 'Cap. (mmBTU/hr)',
	                 'Flow (GPM)',
	                 'EIR',
	                 'HIR',
	                 'Auxiliary (kW)',
	                 'Tank (Gal)',
	                 'Tank UA (BTU/h.ft)']
	df = pd.DataFrame(columns=dhw_info_cols)
	df.index.name = 'DHW Heaters'
	pv_a_dict[dhw_string] = df

	return pv_a_dict


def post_process_pv_a(pv_a_dict, filename, sim_folder):
	"""
	Convert the dataframes in the dictionary to numeric dtype
	and calculates some efficiency metrics, such as Chiller COP, Pump kW/GPM, etc.

	Args:
	------
		pv_a_dict(dict of pd.DataFrame): dictionary of dataframes
			that has the PV-A info

		output_to_csv (boolean): whether you want to output 'PV-A.csv'

	Returns:
	--------
		pv_a_dict(dict of pd.DataFrame): dataframes in numeric dtype and more metrics

		Also spits out a 'PV-A.csv' file if required.


	Needs:
	-------------------------------
		import pandas as pd

	"""

	# Convert numeric for circulation loops
	df_circ = pv_a_dict['CIRCULATION LOOPS']
	df_circ = df_circ.apply(lambda x: pd.to_numeric(x))

	# Calculate kW/GPM for pumps
	df_pumps = pv_a_dict['PUMPS']
	num_cols = ['Flow (GPM)', 'Head (ft)', 'Head Setpoint (ft)', 'Power (kW)', 'Mech. Eff', 'Motor Eff']
	df_pumps[num_cols] = df_pumps[num_cols].apply(lambda x: pd.to_numeric(x))
	df_pumps['W/GPM'] = 1000 * df_pumps['Power (kW)'] / df_pumps['Flow (GPM)']

	# Calculate fan kW/GPM for cooling towers
	df_ct = pv_a_dict['COOLING TOWERS']
	num_cols = ['Cap. (mmBTU/hr)', 'Flow (GPM)', 'Nb of Cells', 'Fan Power per Cell (kW)', 'Spray Power per Cell (kW)',
	            'Aux. (kW)']
	df_ct[num_cols] = df_ct[num_cols].apply(lambda x: pd.to_numeric(x))
	df_ct['Fan W/GPM'] = 1000 * df_ct['Fan Power per Cell (kW)'] * df_ct['Nb of Cells'] / df_ct['Flow (GPM)']
	# GPM per ton
	df_ct['GPM/ton'] = df_ct['Flow (GPM)'] * 12 / (1000 * df_ct['Cap. (mmBTU/hr)'])

	# Calculate proper efficiency for primary equipment
	# First, convert to numeric
	df_primary = pv_a_dict['PRIMARY EQUIPMENT']
	num_cols = ['Capacity (mmBTU/hr)', 'Flow (GPM)', 'EIR', 'HIR', 'Aux. (kW)']
	df_primary[num_cols] = df_primary[num_cols].apply(lambda x: pd.to_numeric(x))

	# Separate between chillers and boilers
	boilers = df_primary['Equipment Type'].str.contains('HW')
	df_boilers = df_primary.loc[boilers].copy()
	df_chillers = df_primary.loc[~boilers].copy()
	# Delete from dict
	del pv_a_dict['PRIMARY EQUIPMENT']

	# Deal with boilers first
	df_boilers['Thermal Eff'] = 1 / df_boilers['HIR']
	# Assign that to the pv_a_dict
	pv_a_dict['BOILERS'] = df_boilers

	# Chillers
	df_chillers['COP'] = 1 / df_chillers['EIR']
	# KW/ton = 12 / (COP x 3.412)
	df_chillers['kW/ton'] = 12 / (df_chillers['COP'] * 3.412)
	# GPM/ton
	df_chillers['GPM/ton'] = df_chillers['Flow (GPM)'] * 12 / (1000 * df_chillers['Capacity (mmBTU/hr)'])

	pv_a_dict['CHILLERS'] = df_chillers

	# DW-HEATERs
	df_dhw = pv_a_dict['DW-HEATERS']
	num_cols = ['Cap. (mmBTU/hr)', 'Flow (GPM)', 'EIR', 'HIR', 'Auxiliary (kW)', 'Tank (Gal)', 'Tank UA (BTU/h.ft)']
	df_dhw[num_cols] = df_dhw[num_cols].apply(lambda x: pd.to_numeric(x))
	df_dhw['Thermal Eff'] = 1 / df_dhw['HIR']

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/PV-A'

	# Output to CSV
	with open(folder_name + '/{0} PV-A.csv'.format(filename), 'w') as f:
		print('{} PV-A Report\n\n'.format(filename), file=f)
		for k, v in pv_a_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return pv_a_dict


def create_sv_a_dict():
	"""
	Initializes a dictionary of dataframes for the SV-A report

	Args: None
	------

	Returns:
	--------
		sv_a_dict(dict of pd.DataFrame): a dictionary of dataframes to collect
			the SV-A reports
			Has three keys: 'Systems', 'Fans', 'Zones'

	Needs:
	-------------------------------
		import pandas as pd

	"""

	sv_a_dict = {}

	system_info_cols = ['System Type',
	                    'Altitude Factor',
	                    'Floor Area (sqft)',
	                    'Max People',
	                    'Outside Air Ratio',
	                    'Cooling Capacity (kBTU/hr)',
	                    'Sensible (SHR)',
	                    'Heating Capacity (kBTU/hr)',
	                    'Cooling EIR (BTU/BTU)',
	                    'Heating EIR (BTU/BTU)',
	                    'Heat Pump Supplemental Heat (kBTU/hr)']

	system_info = pd.DataFrame(columns=system_info_cols)
	system_info.index.name = 'System'
	sv_a_dict['Systems'] = system_info

	fan_info_cols = ['Capacity (CFM)',
	                 'Diversity Factor (FRAC)',
	                 'Power Demand (kW)',
	                 'Fan deltaT (F)',
	                 'Static Pressure (in w.c.)',
	                 'Total efficiency',
	                 'Mechanical Efficiency',
	                 'Fan Placement',
	                 'Fan Control',
	                 'Max Fan Ratio (Frac)',
	                 'Min Fan Ratio (Frac)']
	index = pd.MultiIndex(levels=[['System'], ['Fan Type']],
	                      labels=[[], []],
	                      names=[u'System', u'Fan Type'])
	fan_info = pd.DataFrame(index=index, columns=fan_info_cols)
	sv_a_dict['Fans'] = fan_info

	zone_info_cols = ['Supply Flow (CFM)',
	                  'Exhaust Flow (CFM)',
	                  'Fan (kW)',
	                  'Minimum Flow (Frac)',
	                  'Outside Air Flow (CFM)',
	                  'Cooling Capacity (kBTU/hr)',
	                  'Sensible (FRAC)',
	                  'Extract Rate (kBTU/hr)',
	                  'Heating Capacity (kBTU/hr)',
	                  'Addition Rate (kBTU/hr)',
	                  'Zone Mult']
	index = pd.MultiIndex(levels=[['System'], ['Zone Name']],
	                      labels=[[], []],
	                      names=[u'System', u'Zone Name'])
	zone_info = pd.DataFrame(index=index, columns=zone_info_cols)
	sv_a_dict['Zones'] = zone_info

	return sv_a_dict


def post_process_sv_a(sv_a_dict, filename, sim_folder):
	"""
	Convert the dataframe to numeric dtype
	and calculates some efficiency metrics, such as Fan W/CFM

	Args:
	------
		sv_a_dict(dict pd.DataFrame): Dictionary of DataFrame with SV-A report data
		filename(str): A string representing the filename of the CSV
		output_to_csv (boolean): whether you want to output 'SV-A.csv'. Defaults True

	Returns:
	--------
		system_info(pd.DataFrame): dataframe in numeric dtype and more metrics

		Also spits out a 'SV-A.csv' file if required.


	Needs:
	-------------------------------
		import pandas as pd

	"""

	# Convert to numeric
	sv_a_dict['Systems'].iloc[:, 1:] = sv_a_dict['Systems'].iloc[:, 1:].apply(lambda x: pd.to_numeric(x))

	not_num = ['Fan Placement', 'Fan Control']
	num_cols = [x for x in sv_a_dict['Fans'].columns if x not in not_num]
	sv_a_dict['Fans'][num_cols] = sv_a_dict['Fans'][num_cols].apply(lambda x: pd.to_numeric(x))

	sv_a_dict['Zones'] = sv_a_dict['Zones'].apply(lambda x: pd.to_numeric(x))

	# Calculate Fan W/CFM
	# At Central level
	sv_a_dict['Fans']['W/CFM'] = sv_a_dict['Fans']['Power Demand (kW)'] * 1000 / sv_a_dict['Fans']['Capacity (CFM)']
	sv_a_dict['Zones']['W/CFM'] = sv_a_dict['Zones']['Fan (kW)'] * 1000 / sv_a_dict['Zones']['Supply Flow (CFM)']

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/SV-A'

	# Output to CSV
	with open(folder_name + '/{0} SV-A.csv'.format(filename), 'w') as f:
		print('{} SV-A Report\n\n'.format(filename), file=f)
		for k, v in sv_a_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return sv_a_dict


def create_beps_dict():
	'''
	Initializes a dictioanry of dataframes for BEPS report

	Args: None
	-----

	Returns:
	-----
		(dict of pd.DataFrame)
			A dictionary of dataframes that corresponds to BEPS report

	Requires:
	-----
		import pandas as pd
	'''
	beps_dict = {}

	##### BUILDING COMPONENTS
	component_string = 'BUILDING COMPONENTS'
	component_info_cols = ['Energy Type',
	                       'Lights',
	                       'Task Lights',
	                       'Misc Equipment',
	                       'Space Heating',
	                       'Space Cooling',
	                       'Heat Reject',
	                       'Pumps/Aux',
	                       'Vent Fans',
	                       'Refrig Display',
	                       'Ht Pump Supplem',
	                       'DHW',
	                       'Ext Usage',
	                       'Total']
	df = pd.DataFrame(columns=component_info_cols)
	df.index.name = 'Meters'
	beps_dict[component_string] = df

	###### Energy Summary
	summary_string = "ENERGY SUMMARY"
	summary_info_cols = ['Total [MBTU]',
	                     'Energy per GFA [kBTU/sqft]',
	                     'Energy per Net Area [kBTU/sqft]']
	df = pd.DataFrame(columns=summary_info_cols)
	df.index.name = 'Energy Summary'
	beps_dict[summary_string] = df

	###### Unmet Information
	unmet_string = "UNMET INFO"
	unmet_info_cols = ['% of Hours Outside Throttling Range',
	                   '% of Hours Plant Load Unmet',
	                   'Hours Cooling Unmet',
	                   'Hours Heating Unmet']
	df = pd.DataFrame(columns=unmet_info_cols)
	df.index.name = 'Unmet Info'
	beps_dict[unmet_string] = df

	return beps_dict


def post_process_beps(beps_dicts, filename, sim_folder):
	# TODO: Add post_process_beps documentation
	# Convert to numeric
	df_comp = beps_dicts['BUILDING COMPONENTS']
	not_num = ['Energy Type']
	num_cols = [x for x in df_comp.columns if x not in not_num]
	df_comp[num_cols] = df_comp[num_cols].apply(lambda x: pd.to_numeric(x))

	# Convert summary to numeric
	df_summ = beps_dicts['ENERGY SUMMARY']
	df_summ = df_summ.apply(lambda x: pd.to_numeric(x))

	# Convert Unmet Info to numeric
	df_unmet = beps_dicts['UNMET INFO']
	df_unmet = df_unmet.apply(lambda x: pd.to_numeric(x))
	zone_percent = df_unmet.loc['Unmet']['% of Hours Outside Throttling Range'] / 100
	load_percent = df_unmet.loc['Unmet']['% of Hours Plant Load Unmet'] / 100
	beps_dicts['UNMET INFO'].at['Unmet', '% of Hours Outside Throttling Range'] = zone_percent
	beps_dicts['UNMET INFO'].at['Unmet', '% of Hours Plant Load Unmet'] = load_percent

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/BEPS'

	# Output to CSV
	with open(folder_name + '/{0} BEPS.csv'.format(filename), 'w') as f:
		print('{} BEPS Report\n\n'.format(filename), file=f)
		for k, v in beps_dicts.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return beps_dicts


def create_ps_f_dict(list_of_meters):
	# TODO: Add ps_f_dict documentation
	ps_f_dict = {}

	##### BUILDING COMPONENTS
	component_info_cols = ['Lights',
	                       'Task Lights',
	                       'Misc Equipment',
	                       'Space Heating',
	                       'Space Cooling',
	                       'Heat Reject',
	                       'Pumps/Aux',
	                       'Vent Fans',
	                       'Refrig Display',
	                       'Ht Pump Supplem',
	                       'DHW',
	                       'Ext Usage',
	                       'Total']
	ind_list = [['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'TOTAL'],
	            ['KWH', 'Max KW', 'Day/Hour', 'Peak End Use', 'Peak Pct']]
	index = pd.MultiIndex.from_product(ind_list, names=[u'Month', u'Measure'])
	# Creates a dictionary item for each meter
	for meter in list_of_meters:
		ps_f_dict[meter] = pd.DataFrame(index=index, columns=component_info_cols)

	return ps_f_dict


def post_process_ps_f(ps_f_dict, filename, sim_folder):
	# TODO: write PS-F documentation
	# Convert to numeric, will ignore day/hour
	for k in ps_f_dict:
		ps_f_dict[k] = ps_f_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))
		ps_f_dict[k] = ps_f_dict[k].T

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/PS-F'

	# Output to CSV
	with open(folder_name + '/{0} PS-F.csv'.format(filename), 'w') as f:
		print('{} PS-F Report\n\n'.format(filename), file=f)
		for k, v in ps_f_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return ps_f_dict


def find_in_header(f_list, pattern, report):
	'''
	Helper function
	Finds either zones or meters in headers of the SIM file and returns a list of strings repr them.

	Args
	-----
		f_list(listof Str): A list of string from reading the SIM file
		pattern(str): A regex specifying what header to search
		report(str): A string representing what report the pattern is to be found

	Returns
	-----
		(listof Str): A list of strings representing the pattern (meter/system) found

	Requires
	-----
		None
	'''
	all_finds = []

	for i, line in enumerate(f_list):
		l_list = line.split()
		if len(l_list) > 1:
			if l_list[0] == "REPORT-" and l_list[1] == report:
				find_m = re.match(pattern, line)
				if find_m:
					current_find = find_m.group(1)
					if current_find not in all_finds:
						all_finds.append(current_find)

	return all_finds


def create_ss_a_dict(list_of_sys):
	ss_a_dict = {}
	ss_a_cols = ['Cooling Energy (MBTU)',
	             'Day', 'Hour',
	             'Dry-bulb Temp',
	             'Wet-bulb Temp',
	             'Max Cooling Load (KBtu/hr)',
	             'Heating Energy (MBTU)',
	             'Day', 'Hour',
	             'Dry-bulb Temp',
	             'Wet-bulb Temp',
	             'Max Heating Load (KBtu/hr)',
	             'Electrical Energy (KWH)',
	             'Max Elec Load (KW)']
	ind_list = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'TOTAL', 'MAX']
	for sys in list_of_sys:
		ss_a_dict[sys] = pd.DataFrame(index=ind_list, columns=ss_a_cols)

	return ss_a_dict


def post_process_ss_a(ss_a_dict, filename, sim_folder):
	for k in ss_a_dict:
		ss_a_dict[k] = ss_a_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/SS-A'

	with open(folder_name + '/{0} SS-A.csv'.format(filename), 'w') as f:
		print('{} SS-A Report\n\n'.format(filename), file=f)
		for k, v in ss_a_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return ss_a_dict


def create_ss_b_dict(list_of_sys):
	ss_b_dict = {}
	ss_b_cols = ['Cooling by Zone Coils or Nat Ventil (MBTU)',
	             'Max Cooling by Zone Coils or Nat Ventil (KBtu/Hr)',
	             'Heating by Zone Coils or Nat Ventil (MBTU)',
	             'Max Heating by Zone Coils or Nat Ventil (KBtu/Hr)',
	             'Baseboard Heating Energy (MBTU)',
	             'Max Baseboard Heating Energy (KBtu/Hr)',
	             'Preheat Coil Energy or Elec For Furn Fan (MBTU)',
	             'Max Preheat Coil Energy or Elec for Furn Fan (KBtu/Hr)']
	ind_list = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'TOTAL', 'MAX']
	for sys in list_of_sys:
		ss_b_dict[sys] = pd.DataFrame(index=ind_list, columns=ss_b_cols)

	return ss_b_dict


def post_process_ss_b(ss_b_dict, filename, sim_folder):
	for k in ss_b_dict:
		ss_b_dict[k] = ss_b_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/SS-B'

	with open(folder_name + '/{0} SS-B.csv'.format(filename), 'w') as f:
		print('{} SS-B Report\n\n'.format(filename), file=f)
		for k, v in ss_b_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return ss_b_dict


def create_lv_d_dict():
	lv_d_dict = {}

	avg_u_cols = ['Avg Window U-value',
	              'Avg Walls U-Value',
	              'Avg Window+Walls U-Value',
	              'Window Area (sqft)',
	              'Wall Area (sqft)',
	              'Win+Wall Area (sqft)']
	avg_u_info = pd.DataFrame(columns=avg_u_cols)
	avg_u_info.index.name = 'Surface'
	lv_d_dict['Avg_U'] = avg_u_info

	return lv_d_dict


def post_process_lv_d(lv_d_dict, filename, sim_folder):
	df_avg_u = lv_d_dict['Avg_U']
	df_avg_u = df_avg_u.apply(lambda x: pd.to_numeric(x))

	# Calculate WWR
	wwr = df_avg_u.loc['ALL WALLS', 'Window Area (sqft)'] / \
	      df_avg_u.loc['ALL WALLS', 'Win+Wall Area (sqft)']

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/LV-D'

	with open(folder_name + '/{0} LV-D.csv'.format(filename), 'w') as f:
		print('{} LV-D Report\n\n'.format(filename), file=f)
		for k, v in lv_d_dict.items():
			print(k, file=f)
			print('WWR%,{}'.format(wwr), file=f)
			v.to_csv(f)
			print('', file=f)

	return lv_d_dict


def create_infil_dict():
	'''Creates a dictionary with all the necessary information to calculate infiltration'''
	infil_dict = {}

	ext_surfaces_cols = ['Win U-Value',
	                     'Win Area (Sqft)',
	                     'Wall U-Value',
	                     'Wall Area (Sqft)',
	                     'Win+Wall U- Value',
	                     'Win+Wall Area',
	                     'Azimuth']

	ext_surfaces_info = pd.DataFrame(columns=ext_surfaces_cols)
	ext_surfaces_info.index.name = 'Surface'
	infil_dict['Ext Surfaces'] = ext_surfaces_info

	lv_b_cols = ['Multiplier', 'Floor Area (sqft)']
	lv_b_info = pd.DataFrame(columns=lv_b_cols)
	lv_b_info.index.name = 'Space'

	infil_dict['Space'] = lv_b_info

	return infil_dict


def post_process_infil(infil_dict, filename, sim_folder):
	# TODO: Write post process infiltration
	infil_dict['Ext Surfaces'] = infil_dict['Ext Surfaces'].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	infil_dict['Space'] = infil_dict['Space'].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	folder_name = './{0}'.format(filename)  # default project specific folder
	if sim_folder:
		folder_name = './Parse-SIM output/SV-A'

	with open(folder_name + '/{0} Infiltration.csv'.format(filename), 'w') as f:
		print('{} Infiltration\n\n'.format(filename), file=f)
		for k, v in ss_b_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)


def aggregate_csv(foldername):
	workbook = xlsxwriter.Workbook('./{0}/{0} Master.xlsm'.format(foldername))
	worksheet = workbook.add_worksheet()
	worksheet.set_column('A:A', 30)
	try:
		workbook.add_vba_project('./data/vbaProject.bin')
	except OSError as err:
		print("OS error: {}".format(err))
	worksheet.write('A1', "Press button to select the files you'd like to aggregate")
	worksheet.insert_button('B1', {'macro': 'CombineCsvFiles',
	                               'caption': 'Press Me',
	                               'Width': 80,
	                               'height': 30})
	workbook.close()
