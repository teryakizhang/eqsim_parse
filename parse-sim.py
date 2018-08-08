print('Parse SIM starting...looking for SIM files')

import glob as gb
import logging
import os
import re
import sys

import pandas as pd

import pim

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


### Parse Function ###

def process_sim():
	filelist = gb.glob('./*.SIM')
	if len(filelist) < 1:
		logger.warning("Warning: No SIM file found. \n"
		               "Please put your SIM files in the same directory as this script.")
		exit()

	def yes_no(prompt):
		invalid_response = True
		while invalid_response:
			answer = input(prompt)
			if answer in ['Y', 'y', 'N', 'n']:
				invalid_response = False
			else:
				logger.warning('Invalid Response. Please try again.')
				continue
		return answer.lower()

	# Options
	proceed_prompt = "I found {} SIM files. \nDo you want to process " \
	                 "all the SIM I found? (Y/N): ".format(len(filelist))
	proceed_opt = yes_no(proceed_prompt)

	# Parse SIM
	master_list = []

	if len(filelist) >= 1:
		if proceed_opt == 'y':
			folder_prompt = "Y for SIM report specific folders/N for default project folders. \n" \
			                "SIM report folders such as /BEPS/project.csv (good for batch benchmarking) (Y/N): "
			yn_dict = {'y': True, 'n': False}
			sim_folder = yn_dict[yes_no(folder_prompt)]
			for file in filelist:
				sim_path = file
				measure_dicts = parse_sim(sim_path, sim_folder)  # TODO: Dictionary for location, scenario, and BEPS
				loc_scene = parse_master(sim_path)
				loc_scene.append(measure_dicts[2]['BUILDING COMPONENTS'].copy())
				master_list.append(loc_scene)
		elif proceed_opt == 'n':
			logger.info('Exiting.....')
			exit('User Terminated')
	# something goes here

	# CSV Aggregating option
	agg_prompt = "Do you want to aggregate all the CSVs into 1 Excel file? (Y/N): "
	agg_opt = yes_no(agg_prompt)
	if agg_opt == 'y' and not sim_folder:
		for file in filelist:
			filename = file[2:-4]
			try:
				pim.aggregate_csv(filename)
			except OSError as err:
				logger.error('OS Error:{}'.format(err))
				continue
		print('Navigate to the output folders and click the Master.xlsm to finish aggregating.\n')
	elif agg_opt == 'y' and sim_folder:
		report_name = ['BEPS', 'PV-A', 'SV-A', 'PS-F', 'SS-A', 'SS-B', 'LV-D']
		for report in report_name:
			try:
				pim.aggregate_csv(report, True)
			except OSError as err:
				logger.error('OS Error:{}'.format(err))
				continue
		print('Navigate to the output folders and click the Master.xlsm to finish aggregating.\n')
	elif agg_opt == 'n':
		print('No CSV aggregation, continuing...\n')

	# Master EUB dump option
	# Currently only designed for CaGBC parametrics
	master_prompt = 'Do you want to output a master EUB table? \n' \
	                'Note: Currently only compatible with parametrics (Y/N)'
	master_opt = yes_no(master_prompt)
	if master_opt == 'y':
		process_master(master_list)
	else:
		print('Continuing...\n')

	input('All Done! Press ENTER to exit')


# if master_list != None:
# 	return master_list


def parse_sim(sim_path, sim_folder=False):
	logging.info('Loading{}'.format(sim_path))

	with open(sim_path, encoding="Latin1") as f:
		f_list = f.readlines()

	filename = sim_path[2:-4]
	### SVA ###
	# Initializes a dictionary of dataframes to collect the SV-A report data
	sv_a_dict = pim.create_sv_a_dict()
	sva_header_pattern = 'REPORT- SV-A System Design Parameters for\s+((.*?))\s+WEATHER FILE'
	current_sv_a_section = None
	system_name = None

	### BEPS ###
	beps_dict = pim.create_beps_dict()
	unmet_info = []
	current_type = None
	meter_pattern = '^(\w*?)\s{1,}?[NE][LA]'
	summ_pattern = '^\s{19}TOTAL'
	unmet_pattern = '^\s{19}[PH]'

	### LV-D ###
	lv_d_dict = pim.create_lv_d_dict()
	surface_pattern = '^[\w-]+(?=\s{15,21}\d+)|(?<=\s{4})[\w+]+(?=\s+?\d+)|ALL WALLS'

	### PS-F ###
	ps_f_header_pattern = 'REPORT- PS-F Energy End-Use Summary for\s+((.*?))\s+WEATHER FILE'
	list_of_meters = pim.find_in_header(f_list, ps_f_header_pattern, 'PS-F')
	ps_f_dict = pim.create_ps_f_dict(list_of_meters)
	current_month = None
	month_pattern = '^\w{3}(?=\\n)|(?<=\s{14})[=]{7}'

	### PV-A ###
	pv_a_dict = pim.create_pv_a_dict()
	current_report = None
	current_plant_equip = None
	plant_equip_pattern = '\*\*\* (.*?) \*\*\*'

	### SS-A ###
	ss_a_header_pattern = 'REPORT- SS-A System Loads Summary for\s+((.*?))\s+WEATHER FILE'
	list_of_sys = pim.find_in_header(f_list, ss_a_header_pattern, 'SS-A')
	ss_a_dict = pim.create_ss_a_dict(list_of_sys)

	### SS-B ###
	ss_b_header_pattern = 'REPORT- SS-B System Loads Summary for\s+((.*?))\s+WEATHER FILE'
	ss_b_dict = pim.create_ss_b_dict(list_of_sys)

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
				elif current_report == 'SS-A':
					m3 = re.match(ss_a_header_pattern, line)
					if m3:
						current_sys = m3.group(1)
					else:
						raise Exception('Error, no SS-A system name')
				elif current_report == 'SS-B':
					m4 = re.match(ss_b_header_pattern, line)
					if m4:
						current_sys = m4.group(1)
					else:
						raise Exception('Error, no SS-B system name')
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
					unmet_info.append(l_list[-1].strip('='))

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
			                'MAX THERM/HR': 'Max Therm/Hr', 'THERM': 'Therm', 'MON/DY': 'Mon/Day', 'DAY/HR': 'Day/Hour'}
			# Match current month
			month_m = re.search(month_pattern, line)
			if month_m:
				current_month = month_m.group()
				if current_month == '=======':
					current_month = 'TOTAL'
					index = ps_f_dict[current_meter].index
					names = index.names
					index = ps_f_dict[current_meter].index.tolist()
					index[-3] = ('TOTAL', 'Mon/Day')
					ps_f_dict[current_meter].index = pd.MultiIndex.from_tuples(index, names=names)

			if psf_l_list[0] in ['KWH', 'MAX KW']:
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			elif psf_l_list[0] in ['THERM', 'MAX THERM/HR']:
				df = ps_f_dict[current_meter]
				new_index = [['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL',
				              'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'TOTAL'],
				             ['Therm', 'Max Therm/Hr', 'Day/Hour', 'Peak End Use', 'Peak Pct']]
				df.index = pd.MultiIndex.from_product(new_index, names=[u'Month', u'Measure'])
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			# These two measures do not have a totals column, append empty item to make same length
			elif psf_l_list[0] in ['PEAK ENDUSE', 'PEAK PCT']:
				l_list.append('')
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = l_list[-13:]

			# This measure has values with a slash followed by a space, requires psf_l_list
			elif psf_l_list[0] in ['DAY/HR', 'MON/DY']:
				psf_l_list[-1] = psf_l_list[-1].rstrip('\n')
				proper_date = ["'" + date for date in psf_l_list[-13:]]
				ps_f_dict[current_meter].loc[(current_month, measure_dict[psf_l_list[0]]), :] = proper_date

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

	if sim_folder:
		report_name = ['/BEPS/', '/PV-A/', '/SV-A/', '/PS-F/', '/SS-A/', '/SS-B/', '/LV-D/']
		for folder in report_name:
			folder = './Parse-SIM output' + folder
			os.makedirs(os.path.dirname(folder), exist_ok=True)
	else:
		folder_name = "./{}/".format(filename)
		os.makedirs(os.path.dirname(folder_name), exist_ok=True)

	sv_a_dict = pim.post_process_sv_a(sv_a_dict, filename, sim_folder)
	pv_a_dict = pim.post_process_pv_a(pv_a_dict, filename, sim_folder)
	beps_dict = pim.post_process_beps(beps_dict, filename, sim_folder)
	ps_f_dict = pim.post_process_ps_f(ps_f_dict, filename, sim_folder)
	ss_a_dict = pim.post_process_ss_a(ss_a_dict, filename, sim_folder)
	ss_b_dict = pim.post_process_ss_b(ss_b_dict, filename, sim_folder)
	lv_d_dict = pim.post_process_lv_d(lv_d_dict, filename, sim_folder)

	logger.info("Parsing {} Done!".format(filename))

	return sv_a_dict, pv_a_dict, beps_dict, ps_f_dict, ss_a_dict, ss_b_dict, lv_d_dict


def parse_master(sim_path):
	### Open file ###
	with open(sim_path, encoding="Latin1") as f:
		f_list = f.readlines()

	filename = sim_path[2:-4]

	### Master Info ###
	location_pattern = "(?<=WEATHER\s{1}FILE-\s{1})\w*(?=\s{1}[A-Z]{2})"
	location = None
	scenario_pattern = "\d{1,2}(?=[.]SIM)|Baseline Design(?=[.]SIM)"
	scenario = None

	### Parsing for Master ###
	for i, line in enumerate(f_list):
		l_list = line.split()
		if len(l_list) > 1:
			if location == None:
				m = re.search(location_pattern, line)
				if m:
					location = m.group()
				# print(location)
			if scenario == None:
				m2 = re.search(scenario_pattern, sim_path)
				if m2:
					scenario = m2.group()
				# print(scenario)
		if not location == None and not scenario == None:
			break

	return [location, scenario]


def process_master(master_list):
	master_df = pim.create_master_df()
	eub = ['Lights',
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
	       'Ext Usage']

	for sim in master_list:
		location = sim[0]
		scenario = 'Parametric ' + sim[1]
		beps = sim[2]
		for row in beps.itertuples(name=None):
			ener_list = []
			val = row[2:-1]
			values = list(map(lambda x: x * 293.07107, val))  # Convert MBTU to kWh
			eub_val = zip(eub, values)
			if 'ELECTRICITY' in row:
				ener_list = [['Electricity'] + list(tup) for tup in eub_val]
			if 'NATURAL-GAS' in row:
				ener_list = [['Natural Gas'] + list(tup) for tup in eub_val]
			if len(ener_list[0]) == 3:
				para_list = [[scenario] + list(tup) for tup in ener_list]
				# logger.debug(para_list)
				final_list = [[location] + list(tup) for tup in para_list]
				master_df = master_df.append(pd.DataFrame(final_list, columns=master_df.columns), ignore_index=True)

	try:
		with open('Master EUB.csv', 'w') as f:
			print('Master EUB\n\n', file=f)
			master_df.to_csv(f)
			print('', file=f)
	except OSError as err:
		logger.error(err)

	logger.info('EUB Dump Complete!')
	return master_df


# def infiltration(sim_path):
# 	# TODO: write infiltration parse
# 	logging.info('Loading{} for infiltration'.format(sim_path))
#
# 	with open(sim_path, encoding="Latin1") as f:
# 		f_list = f.readlines()
#
# 	filename = sim_path[2:-4]
#
# 	### Infiltration ###
# 	# Initializes a dictionary of dataframes to collect infiltration data
# 	infil_dict = pim.create_infil_dict()
# 	space_pattern = r'(?<=\s{2}in\sspace:\s)[\w\s()-]+?(?=\s+)'
# 	current_surface = None
# 	current_space = None
#
# 	### Infiltration Parsing ###
# 	for i, line in enumerate(f_list):
# 		l_list = line.split()
# 		if len(l_list) > 1:
# 			if l_list[0] == "REPORT-":
# 				current_report = l_list[1]
#
# 				if current_report == 'LV-D':
# 					pass


### Main Function ###

if __name__ == '__main__':
	process_sim()

	sys.exit(0)
