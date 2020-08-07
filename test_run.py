from reader import generate_tab_files
from Empire import run_empire
from scenario_random import generate_random_scenario
from datetime import datetime

########
##USER##
########

temp_dir = 'C:/Users/stianbac' #'/panfs/nas-0-0.local/work/stianbac'
version = 'test'
NoOfPeriods = 3
NoOfScenarios = 2
NoOfRegSeason = 2
lengthRegSeason = 24
regular_seasons = ["winter", "spring"] #, "summer", "fall"]
NoOfPeakSeason = 2
lengthPeakSeason = 24
discountrate = 0.05
WACC = 0.05
LeapYearsInvestment = 5
solver = "Gurobi" #"Xpress" # #"CPLEX"
scenariogeneration = True #False
EMISSION_CAP = True #False
IAMC_PRINT = False #True
WRITE_LP = False #True
PICKLE_INSTANCE = False #True 

#######
##RUN##
#######

name = version + '_reg' + str(lengthRegSeason) + '_peak' + str(lengthPeakSeason) 
if scenariogeneration:
	name = name + "_randomSGR"
else:
	name = name + "_noSGR"
name = name + str(datetime.now().strftime("_%Y%m%d%H%M"))
workbook_path = 'Data handler/' + version
tab_file_path = 'Data handler/' + version + '/Tab_Files_' + name
scenario_data_path = 'Data handler/' + version + '/ScenarioData'
result_file_path = 'Results/' + name
FirstHoursOfRegSeason = [lengthRegSeason*i + 1 for i in range(NoOfRegSeason)]
FirstHoursOfPeakSeason = [lengthRegSeason*NoOfRegSeason + lengthPeakSeason*i + 1 for i in range(NoOfPeakSeason)]
Period = [i + 1 for i in range(NoOfPeriods)]
Scenario = ["scenario"+str(i + 1) for i in range(NoOfScenarios)]
Season = regular_seasons + ['peak'+str(i + 1) for i in range(NoOfPeakSeason)]
Operationalhour = [i + 1 for i in range(FirstHoursOfPeakSeason[-1] + lengthPeakSeason - 1)]
dict_countries = {"DE": "Germany", "DK": "Denmark", "FR": "France"}

print('++++++++')
print('+EMPIRE+')
print('++++++++')
print('Solver: ' + solver)
print('Scenario Generation: ' + str(scenariogeneration))
print('++++++++')
print('ID: ' + name)
print('++++++++')

if scenariogeneration:
    generate_random_scenario(filepath = scenario_data_path,
                             tab_file_path = tab_file_path,
                             scenarios = NoOfScenarios,
                             seasons = regular_seasons,
                             Periods = NoOfPeriods,
                             regularSeasonHours = lengthRegSeason,
                             peakSeasonHours = lengthPeakSeason,
                             dict_countries = dict_countries)

generate_tab_files(filepath = workbook_path, tab_file_path = tab_file_path,
                   scenariogeneration = scenariogeneration)

run_empire(name = name, 
           tab_file_path = tab_file_path,
           result_file_path = result_file_path, 
           solver = solver,
           temp_dir = temp_dir, 
           FirstHoursOfRegSeason = FirstHoursOfRegSeason, 
           FirstHoursOfPeakSeason = FirstHoursOfPeakSeason, 
           lengthRegSeason = lengthRegSeason,
           lengthPeakSeason = lengthPeakSeason,
           Period = Period, 
           Operationalhour = Operationalhour,
           Scenario = Scenario,
           Season = Season,
           discountrate = discountrate, 
           WACC = WACC, 
           LeapYearsInvestment = LeapYearsInvestment,
           IAMC_PRINT = IAMC_PRINT, 
           WRITE_LP = WRITE_LP, 
           PICKLE_INSTANCE = PICKLE_INSTANCE, 
           EMISSION_CAP = EMISSION_CAP)