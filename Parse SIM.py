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


def post_process_pv_a(pv_a_dict, output_to_csv=True):
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
	with open('PV-A.csv', 'w') as f:
		print('PV-A Report\n\n', file=f)

	with open('PV-A.csv', 'a') as f:
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


def post_process_sv_a(sv_a_dict, output_to_csv=True):
	"""
    Convert the dataframe to numeric dtype
    and calculates some efficiency metrics, such as Fan W/CFM

    Args:
    ------
        sv_a_dict(dict pd.DataFrame): Dictionary of DataFrame with SV-A report data

        output_to_csv (boolean): whether you want to output 'SV-A.csv'

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
	with open('SV-A.csv', 'w') as f:
		print('SV-A Report\n\n', file=f)
	with open('SV-A.csv', 'a') as f:
		for k, v in sv_a_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return sv_a_dict


def create_beps_dict():
	# TODO: add beps_dict documentation
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


def post_process_beps(beps_dicts, output_to_csv=True):
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
	with open('BEPS.csv', 'w') as f:
		print('BEPS Report\n\n', file=f)
		for k, v in beps_dicts.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return beps_dicts


def create_ps_f_dict(list_of_meters):
	# TODO: Add ps_f_dict documentation
	ps_f_dict = {}

	##### BUILDING COMPONENTS
	component_string = 'BUILDING COMPONENTS'
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
	component_info = pd.DataFrame(index=index, columns=component_info_cols)
	# Creates a dictionary item for each meter
	for meter in list_of_meters:
		ps_f_dict[meter] = component_info

	return ps_f_dict


def post_process_ps_f(ps_f_dict, output_to_csv=True):
	# TODO: write documentation
	# Convert to numeric, will ignore day/hour
	for k in ps_f_dict:
		ps_f_dict[k] = ps_f_dict[k].apply(lambda x: pd.to_numeric(x, errors='ignore'))

	# Output to CSV

	with open('PS-F.csv', 'w') as f:
		print('PS-F Report\n\n', file=f)
		for k, v in ps_f_dict.items():
			print(k, file=f)
			v.to_csv(f)
			print('', file=f)

	return ps_f_dict


def find_meters(f_list, pattern):
	'''Finds all the PS-F meters in the SIM file and returns a list of strings repr them.
    Helper function for create_ps_f_dict()'''
	all_meters = []

	for i, line in enumerate(f_list):
		l_list = line.split()
		if len(l_list) > 1:
			if l_list[0] == "REPORT-":
				current_report = l_list[1]
				if current_report == 'PS-F':
					meter_m = re.match(pattern, line)
					if meter_m:
						current_meter = meter_m.group(1)
						if current_meter not in all_meters:
							all_meters.append(current_meter)

	return all_meters


# TODO: Write LV-D dict

# TODO: Write post_process_LV-D

### Parse Function ###

def parse_sim(sim_path=None):
	# Load SIM File

	if sim_path is None:

		filelist = gb.glob('./*.SIM')
		if len(filelist) != 1:
			raise Exception("Too many SIM files found")
			exit()
		# 	raise Exception("No SIM file found. Please put your SIM files in the same directory as this.")
		# 	exit()
		# elif len(filelist) == 1:
		# 	proceed = input("I found 1 SIM file. Proceed with this? (Y/N): ")
		# 	if proceed == "Y":
		#
		# 	else: exit()
		# TODO: Add batch process SIM Support
		# elif len(filelist) > 1:
		# 	multi = input(" I found {} SIM files. \
		# 	Do you want to process all the SIM I found? (Y/N): ".format(len(filelist)))
		# 	if multi == "N" and len(filelist) != 1:
		# 		raise Exception("Too many SIM files found. Please only put the SIM you want to process")
		# 		exit()
		# 	elif multi == "Y":
		# 		for file in filelist:
		# 			sim_path = file
		else:
			sim_path = filelist[0]
			logging.info('Loading{}'.format(sim_path))

			with open(sim_path, encoding="Latin1") as f:
				f_list = f.readlines()


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

	### PS-F ###
	ps_f_header_pattern = 'REPORT- PS-F Energy End-Use Summary for\s+((.*?))\s+WEATHER FILE'
	list_of_meters = find_meters(f_list, ps_f_header_pattern)
	ps_f_dict = create_ps_f_dict(list_of_meters)
	month_pattern = '^\w{3}\\n'

	### PV-A ###
	pv_a_dict = create_pv_a_dict()
	current_report = None
	current_plant_equip = None
	plant_equip_pattern = '\*\*\* (.*?) \*\*\*'

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
				if current_report == 'PS-F':
					# Match meter names
					m2 = re.match(ps_f_header_pattern, line)
					if m2:
						current_meter = m2.group(1)
					else:
						raise Exception("Error, no meter name")
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

		# Parsing PS-F
		if current_report == 'PS-F' and len(l_list) > 0:
			# Only split at 2 spaces or more so words like 'MAX KW' don't get split
			psf_l_list = re.split(r'\s{2,}', line)
			measure_dict = {'KWH': 'KWH', 'MAX KW': 'Max KW', 'PEAK ENDUSE': 'Peak End Use', 'PEAK PCT': 'Peak Pct'}
			# Match current month
			month_m = re.match(month_pattern, line)
			if month_m:
				current_month = month_m.group()
				current_month = current_month.rstrip()

			if psf_l_list[0] in ['KWH', 'MAX KW']:
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			# These two measures do not have a totals column, append empty item to make same length
			elif psf_l_list[0] in ['PEAK ENDUSE', 'PEAK PCT']:
				l_list.append('')
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			# This measure has values with a slash followed by a space, requires psf_l_list
			elif psf_l_list[0] == 'DAY/HR':
				psf_l_list[-1] = psf_l_list[-1].rstrip('\n')
				ps_f_dict[current_meter].loc[(current_month, 'Day/Hour'), :] = psf_l_list[-13:]

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

	sv_a_dict = post_process_sv_a(sv_a_dict, output_to_csv=True)
	pv_a_dict = post_process_pv_a(pv_a_dict, output_to_csv=True)
	beps_dict = post_process_beps(beps_dict, output_to_csv=True)
	ps_f_dict = post_process_ps_f(ps_f_dict, output_to_csv=True)

	logger.info("All Done!")

	return sv_a_dict, pv_a_dict, beps_dict, ps_f_dict


### Main Function ###

if __name__ == '__main__':
	sv_a_dict, pv_a_dict, beps_dict, ps_f_dict = parse_sim(sim_path=None)

	sys.exit(0)
