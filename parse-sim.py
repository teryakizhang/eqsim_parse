import glob as gb
import os
import re
import sys
import logging

import pandas as pd

### DEBUG ###
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

fh = logging.FileHandler('Parse SIM Debug Log.txt')
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)


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


def post_process_pv_a(pv_a_dict, filename):
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

	# Output to CSV
	with open('./{0}/{0} PV-A.csv'.format(filename), 'w') as f:
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


def post_process_sv_a(sv_a_dict, filename):
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

	# Output to CSV
	with open('./{0}/{0} SV-A.csv'.format(filename), 'w') as f:
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


def post_process_beps(beps_dicts, filename):
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

	# Output to CSV
	with open('./{0}/{0} BEPS.csv'.format(filename), 'w') as f:
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
	ind_list = [['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'],
	            ['KWH', 'Max KW', 'Day/Hour', 'Peak End Use', 'Peak Pct']]
	index = pd.MultiIndex.from_product(ind_list, names=[u'Month', u'Measure'])
	# Creates a dictionary item for each meter
	for meter in list_of_meters:
		ps_f_dict[meter] = pd.DataFrame(index=index, columns=component_info_cols)

	return ps_f_dict


def post_process_ps_f(ps_f_dict, filename):
	# TODO: write PS-F documentation
	# Convert to numeric, will ignore day/hour
	for k in ps_f_dict:
		ps_f_dict[k] = ps_f_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	# Output to CSV
	with open('./{0}/{0} PS-F.csv'.format(filename), 'w') as f:
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


def post_process_ss_a(ss_a_dict, filename):
	for k in ss_a_dict:
		ss_a_dict[k] = ss_a_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	with open('./{0}/{0} SS-A.csv'.format(filename), 'w') as f:
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


def post_process_ss_b(ss_b_dict, filename):
	for k in ss_b_dict:
		ss_b_dict[k] = ss_b_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	with open('./{0}/{0} SS-B.csv'.format(filename), 'w') as f:
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


def post_process_lv_d(lv_d_dict, filename):
	df_avg_u = lv_d_dict['Avg_U']
	df_avg_u = df_avg_u.apply(lambda x: pd.to_numeric(x))

	# Calculate WWR
	wwr = df_avg_u.loc['ALL WALLS', 'Window Area (sqft)'] / \
	      df_avg_u.loc['ALL WALLS', 'Win+Wall Area (sqft)']

	with open('./{0}/{0} LV-D.csv'.format(filename), 'w') as f:
		print('{} LV-D Report\n\n'.format(filename), file=f)
		for k, v in lv_d_dict.items():
			print(k, file=f)
			print('WWR%,{}'.format(wwr), file=f)
			v.to_csv(f)
			print('', file=f)

	return lv_d_dict

### Parse Function ###

def multi_sim():
	filelist = gb.glob('./*.SIM')
	invalid_response = True
	prompt = "I found {} SIM files. \nDo you want to process " \
	         "all the SIM I found? (Y/N): ".format(len(filelist))
	while invalid_response:
		if len(filelist) < 1:
			print("Warning: No SIM file found.\n"
			      "Please put your SIM files in the same directory as this script.")
			exit()
		elif len(filelist) >= 1:
			proceed = input(prompt)
			if len(filelist) == 1 and proceed in ['Y', 'y']:
				parse_sim(filelist[0])
				invalid_response = False
			elif len(filelist) > 1 and proceed in ['Y', 'y']:
				for file in filelist:
					sim_path = file
					parse_sim(sim_path)
				invalid_response = False
			elif proceed in ['N', 'n']:
				print('Exiting....')
				invalid_response = False
			# something goes here
			else:
				print('Invalid Response. Please try again.')
				continue


def parse_sim(sim_path):
	logging.info('Loading{}'.format(sim_path))

	with open(sim_path, encoding="Latin1") as f:
		f_list = f.readlines()

	filename = sim_path[2:-4]
	### SVA ###
	# Initializes a dictionary of dataframes to collect the SV-A report data
	sv_a_dict = create_sv_a_dict()
	sva_header_pattern = 'REPORT- SV-A System Design Parameters for\s+((.*?))\s+WEATHER FILE'
	current_sv_a_section = None
	system_name = None

	### BEPS ###
	beps_dict = create_beps_dict()
	unmet_info = []
	current_type = None
	meter_pattern = '^(\w*?)\s{1,}?[NE][LA]'
	summ_pattern = '^\s{19}TOTAL'
	unmet_pattern = '^\s{19}[PH]'

	### LV-D ###
	lv_d_dict = create_lv_d_dict()
	surface_pattern = '^[\w-]+(?=\s{15,21}\d+)|(?<=\s{4})[\w+]+(?=\s+?\d+)|ALL WALLS'


	### PS-F ###
	ps_f_header_pattern = 'REPORT- PS-F Energy End-Use Summary for\s+((.*?))\s+WEATHER FILE'
	list_of_meters = find_in_header(f_list, ps_f_header_pattern, 'PS-F')
	ps_f_dict = create_ps_f_dict(list_of_meters)
	month_pattern = '^\w{3}(?=\\n)'

	### PV-A ###
	pv_a_dict = create_pv_a_dict()
	current_report = None
	current_plant_equip = None
	plant_equip_pattern = '\*\*\* (.*?) \*\*\*'

	### SS-A ###
	ss_a_header_pattern = 'REPORT- SS-A System Loads Summary for\s+((.*?))\s+WEATHER FILE'
	list_of_sys = find_in_header(f_list, ss_a_header_pattern, 'SS-A')
	ss_a_dict = create_ss_a_dict(list_of_sys)

	### SS-B ###
	ss_b_header_pattern = 'REPORT- SS-B System Loads Summary for\s+((.*?))\s+WEATHER FILE'
	ss_b_dict = create_ss_b_dict(list_of_sys)

	### Parsing ###
	for i, line in enumerate(f_list):
		l_list = line.split()
		if len(l_list) > 1:
			if l_list[0] == "REPORT-":
				current_report = l_list[1]

				if current_report == 'SV-A':
					# Match system_name
					m = re.match(sva_header_pattern, line)
					if m:
						system_name = m.group(1)
					else:
						print("Error, on line {i} couldn't find the name for the system. Here is the line:".format(i=i))
						print(line)
				elif current_report == 'PS-F':
					# Match meter names
					m2 = re.match(ps_f_header_pattern, line)
					if m2:
						current_meter = m2.group(1)
					else:
						raise Exception("Error, no meter name")
						print(line)
				elif current_report == 'SS-A':
					m3 = re.match(ss_a_header_pattern, line)
					if m3:
						current_sys = m3.group(1)
					else:
						raise Exception('Error, no SS-A system name')
						print(line)
				elif current_report == 'SS-B':
					m4 = re.match(ss_b_header_pattern, line)
					if m4:
						current_sys = m4.group(1)
					else:
						raise Exception('Error, no SS-B system name')
						print(line)
				continue

		# Parsing BEPS
		if current_report == 'BEPS' and len(l_list) > 0:

			m = re.match(meter_pattern, line)

			# Match with meters and parse data
			if m:
				meter = m.group()
				meter = meter.split()[0]
				current_type = l_list[1]

			if current_type in ["NATURAL-GAS", "ELECTRICITY"]:
				if re.match("^\s{4}[MBTU]", line):
					comp_info = [current_type] + l_list[1:]
					beps_dict['BUILDING COMPONENTS'].loc[meter] = comp_info
					current_type = None

			# Match with site and source energy summary
			m2 = re.match(summ_pattern, line)
			if m2:
				l_list[0:3] = [' '.join(l_list[0:3])]
				current_summ = l_list[0]
				summ_info = [l_list[1]] + [l_list[3]] + [l_list[6]]
				beps_dict['ENERGY SUMMARY'].loc[current_summ] = summ_info

			# Match with unmet hours information
			m3 = re.match(unmet_pattern, line)
			if m3:
				if len(unmet_info) < 4:
					unmet_info.append(l_list[-1])

				if len(unmet_info) == 4:
					beps_dict['UNMET INFO'].loc['Unmet'] = unmet_info

		# Parsing LV-D
		if current_report == 'LV-D' and len(l_list) > 0:
			# Using search instead because match and lookbehind does not work at the beginning of a string
			m = re.search(surface_pattern, line)
			if m:
				current_surface = m.group()
				if current_surface == 'ALL WALLS':
					lv_d_dict['Avg_U'].loc[current_surface] = l_list[2:]
				else:
					lv_d_dict['Avg_U'].loc[current_surface] = l_list[1:]

		# Parsing PS-F
		if current_report == 'PS-F' and len(l_list) > 0:
			# Only split at 2 spaces or more so words like 'MAX KW' don't get split
			psf_l_list = re.split(r'\s{2,}', line)
			measure_dict = {'KWH': 'KWH', 'MAX KW': 'Max KW', 'PEAK ENDUSE': 'Peak End Use', 'PEAK PCT': 'Peak Pct',
			                'MAX THERM/HR': 'Max Therm/Hr', 'THERM': 'Therm'}
			# Match current month
			month_m = re.match(month_pattern, line)
			if month_m:
				current_month = month_m.group()

			if psf_l_list[0] in ['KWH', 'MAX KW']:
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			elif psf_l_list[0] in ['THERM', 'MAX THERM/HR']:
				df = ps_f_dict[current_meter]
				new_index = [['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'],
				             ['Therm', 'Max Therm/Hr', 'Day/Hour', 'Peak End Use', 'Peak Pct']]
				df.index = pd.MultiIndex.from_product(new_index, names=[u'Month', u'Measure'])
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			# These two measures do not have a totals column, append empty item to make same length
			elif psf_l_list[0] in ['PEAK ENDUSE', 'PEAK PCT']:
				l_list.append('')
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			# This measure has values with a slash followed by a space, requires psf_l_list
			elif psf_l_list[0] == 'DAY/HR':
				psf_l_list[-1] = psf_l_list[-1].rstrip('\n')
				ps_f_dict[current_meter].loc[(current_month, 'Day/Hour'), :] = psf_l_list[-13:]

		# Parsing SS-A
		if current_report == 'SS-A' and len(l_list) > 0:

			if l_list[0] in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']:
				ss_a_dict[current_sys].loc[l_list[0]] = l_list[1:]

			elif l_list[0] == 'TOTAL':
				# Empty list items to account for all the mismatched columns
				total_list = [l_list[1]] + [''] * 5 + [l_list[2]] + [''] * 5 + [l_list[3]] + ['']
				ss_a_dict[current_sys].loc[l_list[0]] = total_list
			elif l_list[0] == 'MAX':
				max_list = [''] * 5 + [l_list[1]] + [''] * 5 + [l_list[2]] + [''] + [l_list[3]]
				ss_a_dict[current_sys].loc[l_list[0]] = max_list

		# Parsing SS-B
		if current_report == 'SS-B' and len(l_list) > 0:
			if l_list[0] in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']:
				ss_b_dict[current_sys].loc[l_list[0]] = l_list[1:]
			elif l_list[0] == 'TOTAL':
				total_list = [l_list[1]] + [''] + [l_list[2]] + [''] + [l_list[3]] + [''] + [l_list[4]] + ['']
				ss_b_dict[current_sys].loc[l_list[0]] = total_list
			elif l_list[0] == 'MAX':
				max_list = [''] + [l_list[1]] + [''] + [l_list[2]] + [''] + [l_list[3]] + [''] + [l_list[4]]
				ss_b_dict[current_sys].loc[l_list[0]] = max_list

		# Parsing PV-A
		if current_report == 'PV-A':
			m = re.match(plant_equip_pattern, line)
			if m:
				current_plant_equip = m.group(1)

			# If the line starts with a number or letter a-zA-Z0-9
			if re.match('^\w', line) and "REPORT-" not in line:
				m2 = re.match('^(.*?)\s{2,}', line)
				if m2:
					equip_name = m2.group(1)
					pv_a_dict[current_plant_equip].loc[equip_name, :] = re.split('\s{2,}', f_list[i + 1].strip())

		# Parsing SV-A
		if current_report == 'SV-A' and len(l_list) > 0:
			# Check with section: System, Fan, or Zone
			if l_list[0] in ['SYSTEM', 'FAN', 'ZONE']:
				current_sv_a_section = l_list[0]

			if current_sv_a_section == 'SYSTEM':
				# If starts by an alpha
				if re.match('^\w', line):
					sv_a_dict['Systems'].loc[system_name] = l_list

			if current_sv_a_section == 'FAN':
				# If starts by two spaces and an alpha
				if re.match('^\s{2}\w', line):

					if len(l_list[1:]) > 11:
						l_list[9:11] = [''.join(l_list[9:11])]
					sv_a_dict['Fans'].loc[(system_name, l_list[0]), :] = l_list[1:]

			if current_sv_a_section == 'ZONE':
				if re.match('^\w', line):
					# Split by at least two spaces (otherwise names of zones like "Apt 1 Zn" becomes three elements in list)
					l_list = re.split('\s{2,}', line.strip())
					try:
						sv_a_dict['Zones'].loc[(system_name, l_list[0]), :] = l_list[1:]
					except:
						print(i)
						print(line)

	foldername = "./{}/".format(filename)
	os.makedirs(os.path.dirname(foldername), exist_ok=True)
	sv_a_dict = post_process_sv_a(sv_a_dict, filename)
	pv_a_dict = post_process_pv_a(pv_a_dict, filename)
	beps_dict = post_process_beps(beps_dict, filename)
	ps_f_dict = post_process_ps_f(ps_f_dict, filename)
	ss_a_dict = post_process_ss_a(ss_a_dict, filename)
	ss_b_dict = post_process_ss_b(ss_b_dict, filename)
	lv_d_dict = post_process_lv_d(lv_d_dict, filename)

	logger.info("All Done!")

	return sv_a_dict, pv_a_dict, beps_dict, ps_f_dict, ss_a_dict, ss_b_dict, lv_d_dict


### Main Function ###

if __name__ == '__main__':
	multi_sim()

	sys.exit(0)
