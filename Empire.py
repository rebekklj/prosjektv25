from __future__ import division
from pyomo.environ import *
import csv
import sys
import cloudpickle
import pdb
import time
import pandas as pd
model = AbstractModel()

###########
##SOLVERS##
###########

CPLEX_SOLVER = 0
XPRESS_SOLVER = 0
GUROBI_SOLVER = 1

if CPLEX_SOLVER == 1:
    print("Solver: CPLEX")
if XPRESS_SOLVER == 1:
    print("Solver: Xpress")
if GUROBI_SOLVER == 1:
    print("Solver: Gurobi")

#Note! Only one solver can be activated!
if CPLEX_SOLVER + XPRESS_SOLVER + GUROBI_SOLVER > 1:
    sys.exit("ERROR! Only one solver can be activated!")

##########
##MODULE##
##########

ModelName = 'py_big'

WRITE_LP = 0 #Set to 1 if LP-file should be written and saved

EMISSION_CAP = 0 #Set to 1 if an absolute emission cap should be used (required significantly more memory!)

if WRITE_LP == 1:
    print("Will write LP-file...")

if EMISSION_CAP ==1:
	print("Absolute emission cap in each scenario...")
else:
	print("No absolute emission cap...")

########
##SETS##
########

#Define the sets

print("Declaring sets...")

#Supply technology sets
model.Generator = Set(ordered=True) #g
model.Technology = Set(ordered=True) #t
model.Storage =  Set() #b

#Temporal sets
model.Period = Set(ordered=True) #i
model.Operationalhour = Set(ordered=True) #h
model.Season = Set(ordered=True) #s

#Spatial sets
model.Node = Set(ordered=True) #n
model.DirectionalLink = Set(dimen=2, within=model.Node*model.Node, ordered=True) #a
model.TransmissionType = Set(ordered=True)

#Stochastic sets
model.Scenario = Set(ordered=True) #w

#Subsets
model.GeneratorsOfTechnology=Set(dimen=2) #(t,g) for all t in T, g in G_t
model.GeneratorsOfNode = Set(dimen=2) #(n,g) for all n in N, g in G_n
model.TransmissionTypeOfDirectionalLink = Set(dimen=3) #(n1,n2,t) for all (n1,n2) in L, t in T
model.ThermalGenerators = Set(within=model.Generator) #g_ramp
model.RegHydroGenerator = Set(within=model.Generator) #g_reghyd
model.HydroGenerator = Set(within=model.Generator) #g_hyd
model.StoragesOfNode = Set(dimen=2) #(n,b) for all n in N, b in B_n
model.DependentStorage = Set(within=model.Storage) #b_dagger
model.HoursOfSeason = Set(dimen=2, ordered=True) #(s,h) for all s in S, h in H_s
model.FirstHoursOfRegSeason = Set(within=model.Operationalhour, ordered=True, initialize=[1,169,337,505])
model.FirstHoursOfPeakSeason = Set(within=model.Operationalhour, ordered=True, initialize=[673,697])

print("Reading sets...")

#Load the data

data = DataPortal()
data.load(filename='Sets_Generator.tab',format="set", set=model.Generator)
data.load(filename='Sets_ThermalGenerators.tab',format="set", set=model.ThermalGenerators)
data.load(filename='Sets_HydroGenerator.tab',format="set", set=model.HydroGenerator)
data.load(filename='Sets_HydroGeneratorWithReservoir.tab',format="set", set=model.RegHydroGenerator)
data.load(filename='Sets_Storage.tab',format="set", set=model.Storage)
data.load(filename='Sets_DependentStorage.tab',format="set", set=model.DependentStorage)
data.load(filename='Sets_Technology.tab',format="set", set=model.Technology)
data.load(filename='Sets_Period.tab',format="set", set=model.Period)
data.load(filename='Sets_Operationalhour.tab',format="set", set=model.Operationalhour)
data.load(filename='Sets_Season.tab',format="set", set=model.Season)
data.load(filename='Sets_Node.tab',format="set", set=model.Node)
data.load(filename='Sets_DirectionalLines.tab',format="set", set=model.DirectionalLink)
data.load(filename='Sets_LineType.tab',format="set", set=model.TransmissionType)
data.load(filename='Sets_Scenario.tab',format="set", set=model.Scenario)
data.load(filename='Sets_LineTypeOfDirectionalLines.tab',format="set", set=model.TransmissionTypeOfDirectionalLink)
data.load(filename='Sets_GeneratorsOfTechnology.tab',format="set", set=model.GeneratorsOfTechnology)
data.load(filename='Sets_GeneratorsOfNode.tab',format="set", set=model.GeneratorsOfNode)
data.load(filename='Sets_StorageOfNodes.tab',format="set", set=model.StoragesOfNode)
data.load(filename='Sets_HourOfSeason.tab',format="set", set=model.HoursOfSeason)

print("Constructing sub sets...")

#Build arc subsets

def NodesLinked_init(model, node):
    retval = []
    for (i,j) in model.DirectionalLink:
        if j == node:
            retval.append(i)
    return retval
model.NodesLinked = Set(model.Node, initialize=NodesLinked_init)

def BidirectionalArc_init(model):
    retval = []
    for (i,j) in model.DirectionalLink:
        if i != j and (not (j,i) in retval):
            retval.append((i,j))
    return retval
model.BidirectionalArc = Set(dimen=2, initialize=BidirectionalArc_init, ordered=True) #l

##############
##PARAMETERS##
##############

#Define the parameters

print("Declaring parameters...")

#Scaling

model.discountrate = Param(initialize=0.05) #NB! Hard-coded
model.WACC = Param(initialize=0.05) #NB! Hard-coded
model.LeapYearsInvestment = Param(initialize=5)
model.operationalDiscountrate = Param(initialize=0.05, mutable=True)
model.sceProbab = Param(model.Scenario, mutable=True)
model.seasScale = Param(model.Season, initialize=1.0, mutable=True)
model.lengthRegSeason = Param(initialize=168) #NB! Hard-coded
model.lengthPeakSeason = Param(initialize=24) #NB! Hard-coded

#Cost

model.genCapitalCost = Param(model.Generator, model.Period, default=0, mutable=True)
model.transmissionTypeCapitalCost = Param(model.TransmissionType, model.Period, default=0, mutable=True)
model.storPWCapitalCost = Param(model.Storage, model.Period, default=0, mutable=True)
model.storENCapitalCost = Param(model.Storage, model.Period, default=0, mutable=True)
model.genFixedOMCost = Param(model.Generator, model.Period, default=0, mutable=True)
model.transmissionTypeFixedOMCost = Param(model.TransmissionType, model.Period, default=0, mutable=True)
model.storPWFixedOMCost = Param(model.Storage, model.Period, default=0, mutable=True)
model.storENFixedOMCost = Param(model.Storage, model.Period, default=0, mutable=True)
model.genInvCost = Param(model.Generator, model.Period, default=9000000, mutable=True)
model.transmissionInvCost = Param(model.BidirectionalArc, model.Period, default=3000000, mutable=True)
model.storPWInvCost = Param(model.Storage, model.Period, default=1000000, mutable=True)
model.storENInvCost = Param(model.Storage, model.Period, default=800000, mutable=True)
model.transmissionLength = Param(model.BidirectionalArc, default=0, mutable=True)
model.genVariableOMCost = Param(model.Generator, default=0.0, mutable=True)
model.genFuelCost = Param(model.Generator, model.Period, default=0.0, mutable=True)
model.genMargCost = Param(model.Generator, model.Period, default=600, mutable=True)
model.genCO2TypeFactor = Param(model.Generator, default=0.0, mutable=True)
model.nodeLostLoadCost = Param(model.Node, model.Period, default=22000.0)
model.CO2price = Param(model.Period, default=0.0, mutable=True)
model.CCSCostTSFix = Param(initialize=1149873.72) #NB! Hard-coded
model.CCSCostTSVariable = Param(model.Period, default=0.0, mutable=True)
model.CCSRemFrac = Param(initialize=0.9)

#Node dependent technology limitations

model.genRefInitCap = Param(model.GeneratorsOfNode, default=0.0, mutable=True)
model.genScaleInitCap = Param(model.Generator, model.Period, default=0.0, mutable=True)
model.genInitCap = Param(model.GeneratorsOfNode, model.Period, default=0.0, mutable=True)
model.transmissionInitCap = Param(model.BidirectionalArc, model.Period, default=0.0, mutable=True)
model.storPWInitCap = Param(model.StoragesOfNode, model.Period, default=0.0, mutable=True)
model.storENInitCap = Param(model.StoragesOfNode, model.Period, default=0.0, mutable=True)
model.genMaxBuiltCap = Param(model.Node, model.Technology, model.Period, default=500000.0, mutable=True)
model.transmissionMaxBuiltCap = Param(model.BidirectionalArc, model.Period, default=20000.0, mutable=True)
model.storPWMaxBuiltCap = Param(model.StoragesOfNode, model.Period, default=500000.0, mutable=True)
model.storENMaxBuiltCap = Param(model.StoragesOfNode, model.Period, default=500000.0, mutable=True)
model.genMaxInstalledCapRaw = Param(model.Node, model.Technology, default=0.0, mutable=True)
model.genMaxInstalledCap = Param(model.Node, model.Technology, model.Period, default=0.0, mutable=True)
model.transmissionMaxInstalledCapRaw = Param(model.BidirectionalArc, model.Period, default=0.0)
model.transmissionMaxInstalledCap = Param(model.BidirectionalArc, model.Period, default=0.0, mutable=True)
model.storPWMaxInstalledCap = Param(model.StoragesOfNode, model.Period, default=0.0, mutable=True)
model.storPWMaxInstalledCapRaw = Param(model.StoragesOfNode, default=0.0, mutable=True)
model.storENMaxInstalledCap = Param(model.StoragesOfNode, model.Period, default=0.0, mutable=True)
model.storENMaxInstalledCapRaw = Param(model.StoragesOfNode, default=0.0, mutable=True)

#Type dependent technology limitations

model.genLifetime = Param(model.Generator, default=0.0, mutable=True)
model.transmissionLifetime = Param(model.BidirectionalArc, default=40.0, mutable=True)
model.storageLifetime = Param(model.Storage, default=0.0, mutable=True)
model.genEfficiency = Param(model.Generator, model.Period, default=1.0, mutable=True)
model.lineEfficiency = Param(model.DirectionalLink, default=0.97, mutable=True)
model.storageChargeEff = Param(model.Storage, default=1.0, mutable=True)
model.storageDischargeEff = Param(model.Storage, default=1.0, mutable=True)
model.storageBleedEff = Param(model.Storage, default=1.0, mutable=True)
model.genRampUpCap = Param(model.ThermalGenerators, default=0.0, mutable=True)
model.storageDiscToCharRatio = Param(model.Storage, default=1.0, mutable=True) #NB! Hard-coded
model.storagePowToEnergy = Param(model.DependentStorage, default=1.0, mutable=True)

#Stochastic input

model.sloadRaw = Param(model.Node, model.Operationalhour,  model.Scenario, default=0.0, mutable=True)
model.sloadAnnualDemand = Param(model.Node, model.Period, default=0.0, mutable=True)
model.sload = Param(model.Node, model.Operationalhour, model.Period, model.Scenario, default=0.0, mutable=True)
model.genCapAvailTypeRaw = Param(model.Generator, default=1.0, mutable=True) 
model.genCapAvailStochRaw = Param(model.GeneratorsOfNode, model.Operationalhour, model.Scenario, default=0.0, mutable=True)
model.genCapAvail = Param(model.GeneratorsOfNode, model.Operationalhour, model.Scenario, default=0.0, mutable=True)
model.maxRegHydroGenRaw = Param(model.Node, model.HoursOfSeason, model.Scenario, default=1.0, mutable=True)
model.maxRegHydroGen = Param(model.Node, model.Season, model.Period, model.Scenario, default=1.0, mutable=True)
model.maxHydroNode = Param(model.Node, default=0.0, mutable=True)
model.storOperationalInit = Param(model.Storage, default=0.0, mutable=True) #Percentage of installed energy capacity initially

if EMISSION_CAP==1:
	model.CO2cap = Param(model.Period, default=5000.0, mutable=True)

#Load the parameters

print("Reading parameters...")

data.load(filename='Generator_CapitalCosts.tab', param=model.genCapitalCost, format="table")
data.load(filename='Generator_FixedOMCosts.tab', param=model.genFixedOMCost, format="table")
data.load(filename='Generator_VariableOMCosts.tab', param=model.genVariableOMCost, format="table")
data.load(filename='Generator_FuelCosts.tab', param=model.genFuelCost, format="table")
data.load(filename='Generator_CCSCostTSVariable.tab', param=model.CCSCostTSVariable, format="table")
data.load(filename='Generator_Efficiency.tab', param=model.genEfficiency, format="table")
data.load(filename='Generator_RefInitialCap.tab', param=model.genRefInitCap, format="table")
data.load(filename='Generator_ScaleFactorInitialCap.tab', param=model.genScaleInitCap, format="table")
data.load(filename='Generator_InitialCapacity.tab', param=model.genInitCap, format="table") #node_generator_intial_capacity.xlsx
data.load(filename='Generator_MaxBuiltCapacity.tab', param=model.genMaxBuiltCap, format="table")#?
data.load(filename='Generator_MaxInstalledCapacity.tab', param=model.genMaxInstalledCapRaw, format="table")#maximum_capacity_constraint_040317_high
data.load(filename='Generator_CO2Content.tab', param=model.genCO2TypeFactor, format="table")
data.load(filename='Generator_RampRate.tab', param=model.genRampUpCap, format="table")
data.load(filename='Generator_GeneratorTypeAvailability.tab', param=model.genCapAvailTypeRaw, format="table")
data.load(filename='Generator_Lifetime.tab', param=model.genLifetime, format="table") 

data.load(filename='Transmission_InitialCapacity.tab', param=model.transmissionInitCap, format="table")
data.load(filename='Transmission_MaxBuiltCapacity.tab', param=model.transmissionMaxBuiltCap, format="table")
data.load(filename='Transmission_MaxInstallCapacityRaw.tab', param=model.transmissionMaxInstalledCapRaw, format="table")
data.load(filename='Transmission_Length.tab', param=model.transmissionLength, format="table")
data.load(filename='Transmission_TypeCapitalCost.tab', param=model.transmissionTypeCapitalCost, format="table")
data.load(filename='Transmission_TypeFixedOMCost.tab', param=model.transmissionTypeFixedOMCost, format="table")
data.load(filename='Transmission_lineEfficiency.tab', param=model.lineEfficiency, format="table")
data.load(filename='Transmission_Lifetime.tab', param=model.transmissionLifetime, format="table")

data.load(filename='Storage_StorageBleedEfficiency.tab', param=model.storageBleedEff, format="table")
data.load(filename='Storage_StorageChargeEff.tab', param=model.storageChargeEff, format="table")
data.load(filename='Storage_StorageDischargeEff.tab', param=model.storageDischargeEff, format="table")
data.load(filename='Storage_StoragePowToEnergy.tab', param=model.storagePowToEnergy, format="table")
data.load(filename='Storage_EnergyCapitalCost.tab', param=model.storENCapitalCost, format="table")
data.load(filename='Storage_EnergyFixedOMCost.tab', param=model.storENFixedOMCost, format="table")
data.load(filename='Storage_EnergyInitialCapacity.tab', param=model.storENInitCap, format="table")
data.load(filename='Storage_EnergyMaxBuiltCapacity.tab', param=model.storENMaxBuiltCap, format="table")
data.load(filename='Storage_EnergyMaxInstalledCapacity.tab', param=model.storENMaxInstalledCapRaw, format="table")
data.load(filename='Storage_StorageInitialEnergyLevel.tab', param=model.storOperationalInit, format="table")
data.load(filename='Storage_PowerCapitalCost.tab', param=model.storPWCapitalCost, format="table")
data.load(filename='Storage_PowerFixedOMCost.tab', param=model.storPWFixedOMCost, format="table")
data.load(filename='Storage_InitialPowerCapacity.tab', param=model.storPWInitCap, format="table")
data.load(filename='Storage_PowerMaxBuiltCapacity.tab', param=model.storPWMaxBuiltCap, format="table")
data.load(filename='Storage_PowerMaxInstalledCapacity.tab', param=model.storPWMaxInstalledCapRaw, format="table")
data.load(filename='Storage_Lifetime.tab', param=model.storageLifetime, format="table")

data.load(filename='Node_NodeLostLoadCost.tab', param=model.nodeLostLoadCost, format="table")
data.load(filename='Node_ElectricAnnualDemand.tab', param=model.sloadAnnualDemand, format="table") 

data.load(filename='Stochastic_HydroGenMaxAnnualProduction.tab', param=model.maxHydroNode, format="table") 
data.load(filename='Stochastic_HydroGenMaxSeasonalProduction.tab', param=model.maxRegHydroGenRaw, format="table")
data.load(filename='Stochastic_StochasticAvailability.tab', param=model.genCapAvailStochRaw, format="table") 
data.load(filename='Stochastic_ElectricLoadRaw.tab', param=model.sloadRaw, format="table") 

data.load(filename='General_seasonScale.tab', param=model.seasScale, format="table") 
data.load(filename='General_CO2Price.tab', param=model.CO2price, format="table")

if EMISSION_CAP==1:
    data.load(filename='General_CO2Cap.tab', param=model.CO2cap, format="table")

print("Constructing parameter values...")

def prepSceProbab_rule(model):
	#Build an equiprobable probability distribution for scenarios

	for sce in model.Scenario:
		model.sceProbab[sce] = value(1/len(model.Scenario))

model.build_SceProbab = BuildAction(rule=prepSceProbab_rule)

def prepInvCost_rule(model):
	#Build investment cost for generators, storages and transmission. Annual cost is calculated for the lifetime of the generator and discounted for a year.
	#Then cost is discounted for the investment period (or the remaining lifetime). CCS generators has additional fixed costs depending on emissions. 

	#Generator 
	for g in model.Generator:
		for i in model.Period:
			costperyear=(model.WACC/(1+model.WACC-((1+model.WACC)**(1-model.genLifetime[g]))))*model.genCapitalCost[g,i]+model.genFixedOMCost[g,i]
			costperperiod=costperyear*1000*(1-(1+model.discountrate)**-(min(value((9-i+1)*5), value(model.genLifetime[g]))))/(1-(1/(1+model.discountrate)))
			if ('CCS',g) in model.GeneratorsOfTechnology:
				costperperiod+=model.CCSCostTSFix*model.CCSRemFrac*model.genCO2TypeFactor[g]*(3.6/model.genEfficiency[g,i])
			model.genInvCost[g,i]=costperperiod

	#Storage
	for b in model.Storage:
		for i in model.Period:
			costperyearPW=(model.WACC/(1+model.WACC-((1+model.WACC)**(1-model.storageLifetime[b]))))*model.storPWCapitalCost[b,i]+model.storPWFixedOMCost[b,i]
			costperperiodPW=costperyearPW*1000*(1-(1+model.discountrate)**-(min(value((9-i+1)*5), value(model.storageLifetime[b]))))/(1-(1/(1+model.discountrate)))
			model.storPWInvCost[b,i]=costperperiodPW
			costperyearEN=(model.WACC/(1+model.WACC-((1+model.WACC)**(1-model.storageLifetime[b]))))*model.storENCapitalCost[b,i]+model.storENFixedOMCost[b,i]
			costperperiodEN=costperyearEN*1000*(1-(1+model.discountrate)**-(min(value((9-i+1)*5), value(model.storageLifetime[b]))))/(1-(1/(1+model.discountrate)))
			model.storENInvCost[b,i]=costperperiodEN

	#Transmission
	for (n1,n2) in model.BidirectionalArc:
		for i in model.Period:
			for t in model.TransmissionType:
				if (n1,n2,t) in model.TransmissionTypeOfDirectionalLink:
					costperyear=(model.WACC/(1+model.WACC-((1+model.WACC)**(1-model.transmissionLifetime[n1,n2]))))*model.transmissionLength[n1,n2]*model.transmissionTypeCapitalCost[t,i]+model.transmissionTypeFixedOMCost[t,i]
					costperperiod=costperyear*(1-(1+model.discountrate)**-(min(value((9-i+1)*5), value(model.transmissionLifetime[n1,n2]))))/(1-(1/(1+model.discountrate)))
					model.transmissionInvCost[n1,n2,i]=costperperiod

model.build_InvCost = BuildAction(rule=prepInvCost_rule)

def prepOperationalCostGen_rule(model):
	#Build generator short term marginal costs

	for g in model.Generator:
		for i in model.Period:
			if ('CCS',g) in model.GeneratorsOfTechnology:
				costperenergyunit=(3.6/model.genEfficiency[g,i])*(model.genFuelCost[g,i]+(1-model.CCSRemFrac)*model.genCO2TypeFactor[g]*model.CO2price[i])+ \
				(3.6/model.genEfficiency[g,i])*(model.CCSRemFrac*model.genCO2TypeFactor[g]*model.CCSCostTSVariable[i])+ \
				model.genVariableOMCost[g]
			else:
				costperenergyunit=(3.6/model.genEfficiency[g,i])*(model.genFuelCost[g,i]+model.genCO2TypeFactor[g]*model.CO2price[i])+ \
				model.genVariableOMCost[g]
			model.genMargCost[g,i]=costperenergyunit

model.build_OperationalCostGen = BuildAction(rule=prepOperationalCostGen_rule)

def prepInitialCapacityNodeGen_rule(model):
	#Build initial capacity for generator type in node

	for (n,g) in model.GeneratorsOfNode:
		for i in model.Period:
			if model.genInitCap[n,g,i] == 0:
				model.genInitCap[n,g,i] = model.genRefInitCap[n,g]*(1-model.genScaleInitCap[g,i])

model.build_InitialCapacityNodeGen = BuildAction(rule=prepInitialCapacityNodeGen_rule)

def prepInitialCapacityTransmission_rule(model):
	#Build initial capacity for transmission lines to ensure initial capacity is the upper installation bound if infeasible

	for (n1,n2) in model.BidirectionalArc:
		for i in model.Period:
			if value(model.transmissionMaxInstalledCapRaw[n1,n2,i]) <= value(model.transmissionInitCap[n1,n2,i]):
				model.transmissionMaxInstalledCap[n1,n2,i] = model.transmissionInitCap[n1,n2,i]
			else:
				model.transmissionMaxInstalledCap[n1,n2,i] = model.transmissionMaxInstalledCapRaw[n1,n2,i]

model.build_InitialCapacityTransmission = BuildAction(rule=prepInitialCapacityTransmission_rule)

def prepOperationalDiscountrate_rule(model):
	#Build operational discount rate

    model.operationalDiscountrate = sum((1+model.discountrate)**(-j) for j in list(range(0,value(model.LeapYearsInvestment))))

model.build_operationalDiscountrate = BuildAction(rule=prepOperationalDiscountrate_rule)     

def prepGenMaxInstalledCap_rule(model):
	#Build resource limit (installed limit) for all periods. Avoid infeasibility if installed limit lower than initially installed cap.

    for t in model.Technology:
        for n in model.Node:
            for i in model.Period:
                if value(model.genMaxInstalledCapRaw[n,t] <= sum(model.genInitCap[n,g,i] for g in model.Generator if (n,g) in model.GeneratorsOfNode and (t,g) in model.GeneratorsOfTechnology)):
                    model.genMaxInstalledCap[n,t,i]=sum(model.genInitCap[n,g,i] for g in model.Generator if (n,g) in model.GeneratorsOfNode and (t,g) in model.GeneratorsOfTechnology)
                else:
                    model.genMaxInstalledCap[n,t,i]=model.genMaxInstalledCapRaw[n,t]
                    
model.build_genMaxInstalledCap = BuildAction(rule=prepGenMaxInstalledCap_rule)

def storENMaxInstalledCap_rule(model):
	#Build installed limit (resource limit) for storEN

    for (n,b) in model.StoragesOfNode:
        for i in model.Period:
            model.storENMaxInstalledCap[n,b,i]=model.storENMaxInstalledCapRaw[n,b]

model.build_storENMaxInstalledCap = BuildAction(rule=storENMaxInstalledCap_rule)

def storPWMaxInstalledCap_rule(model):
	#Build installed limit (resource limit) for storPW

    for (n,b) in model.StoragesOfNode:
        for i in model.Period:
            model.storPWMaxInstalledCap[n,b,i]=model.storPWMaxInstalledCapRaw[n,b]

model.build_storPWMaxInstalledCap = BuildAction(rule=storPWMaxInstalledCap_rule)

def prepRegHydro_rule(model):
	#Build hydrolimits for all periods

    for n in model.Node:
        for s in model.Season:
            for i in model.Period:
                for sce in model.Scenario:
                    model.maxRegHydroGen[n,s,i,sce]=sum(model.maxRegHydroGenRaw[n,s,h,sce] for h in model.Operationalhour if (s,h) in model.HoursOfSeason)

model.build_maxRegHydroGen = BuildAction(rule=prepRegHydro_rule)

def prepGenCapAvail_rule(model):
	#Build generator availability for all periods

    for (n,g) in model.GeneratorsOfNode:
    	for h in model.Operationalhour:
            for s in model.Scenario:
                if model.genCapAvailTypeRaw[g] == 0:
                    model.genCapAvail[n,g,h,s]=model.genCapAvailStochRaw[n,g,h,s]
                else:
                    model.genCapAvail[n,g,h,s]=model.genCapAvailTypeRaw[g]                        

model.build_genCapAvail = BuildAction(rule=prepGenCapAvail_rule)

def prepSload_rule(model):
	#Build load profiles for all periods

    for n in model.Node:
        nodeaverageload=sum(model.sloadRaw[n,h,sce] for h in model.Operationalhour if value(h) < value(model.FirstHoursOfRegSeason[-1]+model.lengthRegSeason) for sce in model.Scenario)/value((model.FirstHoursOfRegSeason[-1]+model.lengthRegSeason-1)*len(model.Scenario))
        for i in model.Period:
            hourlyadjustment=value(model.sloadAnnualDemand[n,i]/8760) - nodeaverageload
            for h in model.Operationalhour:
                for sce in model.Scenario:
                    if value(model.sloadRaw[n,h,sce]+hourlyadjustment)>0:
                        model.sload[n,h,i,sce]=model.sloadRaw[n,h,sce]+hourlyadjustment
                    else:
                    	print(n);print(h);print(sce);print('Adjusted load is negative')

model.build_sload = BuildAction(rule=prepSload_rule)

#instance = model.create_instance(data)
#instance.storPWMaxInstalledCap.pprint()
#import pdb; pdb.set_trace()

print("Sets and parameters declared and read...")

#############
##VARIABLES##
#############

print("Declaring variables...")

model.genInvCap = Var(model.GeneratorsOfNode, model.Period, domain=NonNegativeReals)
model.transmisionInvCap = Var(model.BidirectionalArc, model.Period, domain=NonNegativeReals)
model.storPWInvCap = Var(model.StoragesOfNode, model.Period, domain=NonNegativeReals)
model.storENInvCap = Var(model.StoragesOfNode, model.Period, domain=NonNegativeReals)
model.genOperational = Var(model.GeneratorsOfNode, model.Operationalhour, model.Period, model.Scenario, domain=NonNegativeReals)
model.storOperational = Var(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, domain=NonNegativeReals)
model.transmisionOperational = Var(model.DirectionalLink, model.Operationalhour, model.Period, model.Scenario, domain=NonNegativeReals) #flow
model.storCharge = Var(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, domain=NonNegativeReals)
model.storDischarge = Var(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, domain=NonNegativeReals)
model.loadShed = Var(model.Node, model.Operationalhour, model.Period, model.Scenario, domain=NonNegativeReals)
model.genInstalledCap = Var(model.GeneratorsOfNode, model.Period, domain=NonNegativeReals)
model.transmisionInstalledCap = Var(model.BidirectionalArc, model.Period, domain=NonNegativeReals)
model.storPWInstalledCap = Var(model.StoragesOfNode, model.Period, domain=NonNegativeReals)
model.storENInstalledCap = Var(model.StoragesOfNode, model.Period, domain=NonNegativeReals)

###############
##EXPRESSIONS##
###############

def multiplier_rule(model,period):
    coeff=1
    if period>1:
        coeff=pow(1.0+model.discountrate,(-5*(int(period)-1)))
    return coeff
model.discount_multiplier=Expression(model.Period, rule=multiplier_rule)

def shed_component_rule(model,i):
    return sum(model.operationalDiscountrate*model.seasScale[s]*model.sceProbab[w]*model.nodeLostLoadCost[n,i]*model.loadShed[n,h,i,w] for n in model.Node for w in model.Scenario for (s,h) in model.HoursOfSeason)
model.shedcomponent=Expression(model.Period,rule=shed_component_rule)

def operational_cost_rule(model,i):
    return sum(model.operationalDiscountrate*model.seasScale[s]*model.sceProbab[w]*model.genMargCost[g,i]*model.genOperational[n,g,h,i,w] for (n,g) in model.GeneratorsOfNode for (s,h) in model.HoursOfSeason for w in model.Scenario)
model.operationalcost=Expression(model.Period,rule=operational_cost_rule)

#############
##OBJECTIVE##
#############

def Obj_rule(model):
    return sum(model.discount_multiplier[i]*(sum(model.genInvCost[g,i]* model.genInvCap[n,g,i] for (n,g) in model.GeneratorsOfNode ) + \
        sum(model.transmissionInvCost[n1,n2,i]*model.transmisionInvCap[n1,n2,i] for (n1,n2) in model.BidirectionalArc ) + \
        sum((model.storPWInvCost[b,i]*model.storPWInvCap[n,b,i]+model.storENInvCost[b,i]*model.storENInvCap[n,b,i]) for (n,b) in model.StoragesOfNode ) + \
        model.shedcomponent[i] + model.operationalcost[i]) for i in model.Period)
model.Obj = Objective(rule=Obj_rule, sense=minimize)

###############
##CONSTRAINTS##
###############

def FlowBalance_rule(model, n, h, i, w):
    return sum(model.genOperational[n,g,h,i,w] for g in model.Generator if (n,g) in model.GeneratorsOfNode) \
        + sum((model.storageDischargeEff[b]*model.storDischarge[n,b,h,i,w]-model.storCharge[n,b,h,i,w]) for b in model.Storage if (n,b) in model.StoragesOfNode) \
        + sum((model.lineEfficiency[link,n]*model.transmisionOperational[link,n,h,i,w] - model.transmisionOperational[n,link,h,i,w]) for link in model.NodesLinked[n]) \
        - model.sload[n,h,i,w] + model.loadShed[n,h,i,w] \
        == 0
model.FlowBalance = Constraint(model.Node, model.Operationalhour, model.Period, model.Scenario, rule=FlowBalance_rule)

#################################################################

def genMaxProd_rule(model, n, g, h, i, w):
        return model.genOperational[n,g,h,i,w] - model.genCapAvail[n,g,h,w]*model.genInstalledCap[n,g,i] <= 0
model.maxGenProduction = Constraint(model.GeneratorsOfNode, model.Operationalhour, model.Period, model.Scenario, rule=genMaxProd_rule)

#################################################################

def ramping_rule(model, n, g, h, i, w):
    if h in model.FirstHoursOfRegSeason or h in model.FirstHoursOfPeakSeason:
        return Constraint.Skip
    else:
        if g in model.ThermalGenerators:
            return model.genOperational[n,g,h,i,w]-model.genOperational[n,g,(h-1),i,w] - model.genRampUpCap[g]*model.genInstalledCap[n,g,i] <= 0   #
        else:
            return Constraint.Skip
model.ramping = Constraint(model.GeneratorsOfNode, model.Operationalhour, model.Period, model.Scenario, rule=ramping_rule)

#################################################################

def storage_energy_balance_rule(model, n, b, h, i, w):
    if h in model.FirstHoursOfRegSeason or h in model.FirstHoursOfPeakSeason:
        return model.storOperationalInit[b]*model.storENInstalledCap[n,b,i] + model.storageChargeEff[b]*model.storCharge[n,b,h,i,w]-model.storDischarge[n,b,h,i,w]-model.storOperational[n,b,h,i,w] == 0   #
    else:
        return model.storageBleedEff[b]*model.storOperational[n,b,(h-1),i,w] + model.storageChargeEff[b]*model.storCharge[n,b,h,i,w]-model.storDischarge[n,b,h,i,w]-model.storOperational[n,b,h,i,w] == 0   #
model.storage_energy_balance = Constraint(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, rule=storage_energy_balance_rule)

#################################################################


def storage_seasonal_net_zero_balance_rule(model, n, b, h, i, w):
    if h in model.FirstHoursOfRegSeason:
        return model.storOperational[n,b,h+value(model.lengthRegSeason)-1,i,w] - model.storOperationalInit[b]*model.storENInstalledCap[n,b,i] == 0  #
    elif h in model.FirstHoursOfPeakSeason:
        return model.storOperational[n,b,h+value(model.lengthPeakSeason)-1,i,w] - model.storOperationalInit[b]*model.storENInstalledCap[n,b,i] == 0  #
    else:
        return Constraint.Skip
model.storage_seasonal_net_zero_balance = Constraint(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, rule=storage_seasonal_net_zero_balance_rule)

#################################################################

def storage_operational_cap_rule(model, n, b, h, i, w):
    return model.storOperational[n,b,h,i,w] - model.storENInstalledCap[n,b,i]  <= 0   #
model.storage_operational_cap = Constraint(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, rule=storage_operational_cap_rule)

#################################################################

def storage_power_discharg_cap_rule(model, n, b, h, i, w):
    return model.storDischarge[n,b,h,i,w] - model.storageDiscToCharRatio[b]*model.storPWInstalledCap[n,b,i] <= 0   #
model.storage_power_discharg_cap = Constraint(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, rule=storage_power_discharg_cap_rule)

#################################################################

def storage_power_charg_cap_rule(model, n, b, h, i, w):
    return model.storCharge[n,b,h,i,w] - model.storPWInstalledCap[n,b,i] <= 0   #
model.storage_power_charg_cap = Constraint(model.StoragesOfNode, model.Operationalhour, model.Period, model.Scenario, rule=storage_power_charg_cap_rule)

#################################################################

def hydro_gen_limit_rule(model, n, g, s, i, w):
    if g in model.RegHydroGenerator:
        return sum(model.genOperational[n,g,h,i,w] for h in model.Operationalhour if (s,h) in model.HoursOfSeason) - model.maxRegHydroGen[n,s,i,w] <= 0
    else:
        return Constraint.Skip  #
model.hydro_gen_limit = Constraint(model.GeneratorsOfNode, model.Season, model.Period, model.Scenario, rule=hydro_gen_limit_rule)

#################################################################

def hydro_node_limit_rule(model, n, i):
    return sum(model.genOperational[n,g,h,i,w]*model.seasScale[s]*model.sceProbab[w] for g in model.HydroGenerator if (n,g) in model.GeneratorsOfNode for (s,h) in model.HoursOfSeason for w in model.Scenario) - model.maxHydroNode[n] <= 0   #
model.hydro_node_limit = Constraint(model.Node, model.Period, rule=hydro_node_limit_rule)


#################################################################

def transmission_cap_rule(model, n1, n2, h, i, w):
    if (n1,n2) in model.BidirectionalArc:
        return model.transmisionOperational[(n1,n2),h,i,w]  - model.transmisionInstalledCap[(n1,n2),i] <= 0
    elif (n2,n1) in model.BidirectionalArc:
        return model.transmisionOperational[(n1,n2),h,i,w]  - model.transmisionInstalledCap[(n2,n1),i] <= 0
model.transmission_cap = Constraint(model.DirectionalLink, model.Operationalhour, model.Period, model.Scenario, rule=transmission_cap_rule)

#################################################################

if EMISSION_CAP==1:
	def emission_cap_rule(model, i, w):
	    return sum(model.seasScale[s]*model.genCO2TypeFactor[g]*(3.6/model.genEfficiency[g,i])*model.genOperational[n,g,h,i,w] for (n,g) in model.GeneratorsOfNode for (s,h) in model.HoursOfSeason)/1000000 - model.CO2cap[i] <= 0   #
	model.emission_cap = Constraint(model.Period, model.Scenario, rule=emission_cap_rule)

#################################################################

def lifetime_rule_gen(model, n, g, i):
    startPeriod=1
    if value(1+i-(model.genLifetime[g]/model.LeapYearsInvestment))>startPeriod:
        startPeriod=value(1+i-model.genLifetime[g]/model.LeapYearsInvestment)
    return sum(model.genInvCap[n,g,j]  for j in model.Period if j>=startPeriod and j<=i )- model.genInstalledCap[n,g,i] + model.genInitCap[n,g,i]== 0   #
model.installedCapDefinitionGen = Constraint(model.GeneratorsOfNode, model.Period, rule=lifetime_rule_gen)

#################################################################

def lifetime_rule_storEN(model, n, b, i):
    startPeriod=1
    if value(1+i-model.storageLifetime[b]*(1/model.LeapYearsInvestment))>startPeriod:
        startPeriod=value(1+i-model.storageLifetime[b]/model.LeapYearsInvestment)
    return sum(model.storENInvCap[n,b,j]  for j in model.Period if j>=startPeriod and j<=i )- model.storENInstalledCap[n,b,i] + model.storENInitCap[n,b,i]== 0   #
model.installedCapDefinitionStorEN = Constraint(model.StoragesOfNode, model.Period, rule=lifetime_rule_storEN)

#################################################################

def lifetime_rule_storPOW(model, n, b, i):
    startPeriod=1
    if value(1+i-model.storageLifetime[b]*(1/model.LeapYearsInvestment))>startPeriod:
        startPeriod=value(1+i-model.storageLifetime[b]/model.LeapYearsInvestment)
    return sum(model.storPWInvCap[n,b,j]  for j in model.Period if j>=startPeriod and j<=i )- model.storPWInstalledCap[n,b,i] + model.storPWInitCap[n,b,i]== 0   #
model.installedCapDefinitionStorPOW = Constraint(model.StoragesOfNode, model.Period, rule=lifetime_rule_storPOW)

#################################################################

def lifetime_rule_trans(model, n1, n2, i):
    startPeriod=1
    if value(1+i-model.transmissionLifetime[n1,n2]*(1/model.LeapYearsInvestment))>startPeriod:
        startPeriod=value(1+i-model.transmissionLifetime[n1,n2]/model.LeapYearsInvestment)
    return sum(model.transmisionInvCap[n1,n2,j]  for j in model.Period if j>=startPeriod and j<=i )- model.transmisionInstalledCap[n1,n2,i] + model.transmissionInitCap[n1,n2,i] == 0   #
model.installedCapDefinitionTrans = Constraint(model.BidirectionalArc, model.Period, rule=lifetime_rule_trans)

#################################################################

def investment_gen_cap_rule(model, t, n, i):
    return sum(model.genInvCap[n,g,i] for g in model.Generator if (n,g) in model.GeneratorsOfNode and (t,g) in model.GeneratorsOfTechnology) - model.genMaxBuiltCap[n,t,i] <= 0
model.investment_gen_cap = Constraint(model.Technology, model.Node, model.Period, rule=investment_gen_cap_rule)

#################################################################

def investment_trans_cap_rule(model, n1, n2, i):
    return model.transmisionInvCap[n1,n2,i] - model.transmissionMaxBuiltCap[n1,n2,i] <= 0
model.investment_trans_cap = Constraint(model.BidirectionalArc, model.Period, rule=investment_trans_cap_rule)

#################################################################

def investment_storage_power_cap_rule(model, n, b, i):
    return model.storPWInvCap[n,b,i] - model.storPWMaxBuiltCap[n,b,i] <= 0
model.investment_storage_power_cap = Constraint(model.StoragesOfNode, model.Period, rule=investment_storage_power_cap_rule)

#################################################################

def investment_storage_energy_cap_rule(model, n, b, i):
    return model.storENInvCap[n,b,i] - model.storENMaxBuiltCap[n,b,i] <= 0
model.investment_storage_energy_cap = Constraint(model.StoragesOfNode, model.Period, rule=investment_storage_energy_cap_rule)

################################################################

def installed_gen_cap_rule(model, t, n, i):
    return sum(model.genInstalledCap[n,g,i] for g in model.Generator if (n,g) in model.GeneratorsOfNode and (t,g) in model.GeneratorsOfTechnology) - model.genMaxInstalledCap[n,t,i] <= 0
model.installed_gen_cap = Constraint(model.Technology, model.Node, model.Period, rule=installed_gen_cap_rule)

#################################################################

def installed_trans_cap_rule(model, n1, n2, i):
    return model.transmisionInstalledCap[n1,n2,i] - model.transmissionMaxInstalledCap[n1,n2,i] <= 0
model.installed_trans_cap = Constraint(model.BidirectionalArc, model.Period, rule=installed_trans_cap_rule)

#################################################################

def installed_storage_power_cap_rule(model, n, b, i):
    return model.storPWInstalledCap[n,b,i] - model.storPWMaxInstalledCap[n,b,i] <= 0
model.installed_storage_power_cap = Constraint(model.StoragesOfNode, model.Period, rule=installed_storage_power_cap_rule)

#################################################################

def installed_storage_energy_cap_rule(model, n, b, i):
    return model.storENInstalledCap[n,b,i] - model.storENMaxInstalledCap[n,b,i] <= 0
model.installed_storage_energy_cap = Constraint(model.StoragesOfNode, model.Period, rule=installed_storage_energy_cap_rule)

#################################################################

def power_energy_relate_rule(model, n, b, i):
    if b in model.DependentStorage:
        return model.storPWInstalledCap[n,b,i] - model.storagePowToEnergy[b]*model.storENInstalledCap[n,b,i] == 0   #
    else:
        return Constraint.Skip
model.power_energy_relate = Constraint(model.StoragesOfNode, model.Period, rule=power_energy_relate_rule)

#################################################################

#######
##RUN##
#######

print("Objective and constraints read...")

print("Building instance...")

start = time.time()

instance = model.create_instance(data) #, report_timing=True)
instance.dual = Suffix(direction=Suffix.IMPORT) #Make sure the dual value is collected into solver results (if solver supplies dual information)

end = time.time()
print("Building instance took [sec]:")
print(end - start)

#import pdb; pdb.set_trace()
#instance.installed_storage_power_cap.pprint()

print("----------------------Problem Statistics---------------------")
print("")
print("Nodes: "+ str(len(instance.Node)))
print("Lines: "+str(len(instance.BidirectionalArc)))
print("")
print("GeneratorTypes: "+str(len(instance.Generator)))
print("TotalGenerators: "+str(len(instance.GeneratorsOfNode)))
print("StorageTypes: "+str(len(instance.Storage)))
print("TotalStorages: "+str(len(instance.StoragesOfNode)))
print("")
print("InvestmentYears: "+str(len(instance.Period)))
print("Scenarios: "+str(len(instance.Scenario)))
print("TotalOperationalHoursPerScenario: "+str(len(instance.Operationalhour)))
print("TotalOperationalHoursPerInvYear: "+str(len(instance.Operationalhour)*len(instance.Scenario)))
print("Seasons: "+str(len(instance.Season)))
print("RegularSeasons: "+str(len(instance.FirstHoursOfRegSeason)))
print("LengthOfRegSeason: "+str(value(instance.lengthRegSeason)))
print("PeakSeasons: "+str(len(instance.FirstHoursOfPeakSeason)))
print("LengthOfPeakSeason: "+str(value(instance.lengthPeakSeason)))
print("") 
print("Discount rate: "+str(value(instance.discountrate))) 
print("Operational discount scale: "+str(value(instance.operationalDiscountrate)))
print("--------------------------------------------------------------")

print("Solving...")

if CPLEX_SOLVER == 1:
    opt = SolverFactory("cplex", Verbose=True)
    opt.options["lpmethod"] = 4
    opt.options["barrier crossover"] = -1
    #instance.display('outputs_cplex.txt')
if XPRESS_SOLVER == 1:
    opt = SolverFactory("xpress") #Verbose=True
    opt.options["defaultAlg"] = 4
    opt.options["crossover"] = 0
    opt.options["lpLog"] = 1
    #instance.display('outputs_xpress.txt')
if GUROBI_SOLVER == 1:
    opt = SolverFactory('gurobi', Verbose=True)
    opt.options["Crossover"]=0
    opt.options["Method"]=2

results = opt.solve(instance, tee=True, logfile='logfile.log')#, keepfiles=True, symbolic_solver_labels=True)
#instance.display('outputs_gurobi.txt')

#import pdb; pdb.set_trace()

###########
##RESULTS##
###########

print("Writing results to .csv...")

f = open('results_output_gen.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["Node,GeneratorType,Period,genInvCap_MW,genInstalledCap_MW,genExpectedCapacityFactor,DiscountedInvestmentCost_Euro,genExpectedAnnualProduction_GWh"])
for (n,g) in instance.GeneratorsOfNode:
    for i in instance.Period:
        my_string=str(n)+","+str(g)+","+str(value(2010+(i-1)*5))+","+str(value(instance.genInvCap[n,g,i]))+","+str(value(instance.genInstalledCap[n,g,i]))+","+ \
        str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*instance.genOperational[n,g,h,i,w] for (s,h) in instance.HoursOfSeason for w in instance.Scenario)/(instance.genInstalledCap[n,g,i]*8760) if instance.genInstalledCap[n,g,i] != 0 else 0))+","+ \
        str(value(instance.discount_multiplier[i]*instance.genInvCap[n,g,i]*instance.genInvCost[g,i]))+","+ \
        str(value(sum(instance.seasScale[s]*instance.sceProbab[w]*instance.genOperational[n,g,h,i,w]/1000 for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))  
        writer.writerow([my_string])
f.close()

f = open('results_output_stor.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["Node,StorageType,Period,storPWInvCap_MW,storPWInstalledCap_MW,storENInvCap_MWh,storENInstalledCap_MWh,DiscountedInvestmentCostPWEN_EuroPerMWMWh,ExpectedAnnualDischargeVolume_GWh,ExpectedAnnualLossesChargeDischarge_GWh"])
for (n,b) in instance.StoragesOfNode:
    for i in instance.Period:
        my_string=str(n)+","+str(b)+","+str(value(2010+(i-1)*5))+","+str(value(instance.storPWInvCap[n,b,i]))+","+str(value(instance.storPWInstalledCap[n,b,i]))+","+ \
        str(value(instance.storENInvCap[n,b,i]))+","+str(value(instance.storENInstalledCap[n,b,i]))+","+ \
        str(value(instance.discount_multiplier[i]*(instance.storPWInvCap[n,b,i]*instance.storPWInvCost[b,i] + instance.storENInvCap[n,b,i]*instance.storENInvCost[b,i])))+","+ \
        str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*instance.storDischarge[n,b,h,i,w]/1000 for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))+","+ \
        str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*((1 - instance.storageDischargeEff[b])*instance.storDischarge[n,b,h,i,w] + (1 - instance.storageChargeEff[b])*instance.storCharge[n,b,h,i,w])/1000 for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))
        writer.writerow([my_string])
f.close()

f = open('results_output_transmision.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["BetweenNode,AndNode,Period,transmisionInvCap_MW,transmisionInstalledCap_MW,DiscountedInvestmentCost_EuroPerMW,transmisionExpectedAnnualVolume_GWh,ExpectedAnnualLosses_GWh"])
for (n1,n2) in instance.BidirectionalArc:
    for i in instance.Period:
        my_string=str(n1)+","+str(n2)+","+str(value(2010+(i-1)*5))+","+str(value(instance.transmisionInvCap[n1,n2,i]))+","+str(value(instance.transmisionInstalledCap[n1,n2,i]))+","+ \
        str(value(instance.discount_multiplier[i]*instance.transmisionInvCap[n1,n2,i]*instance.transmissionInvCost[n1,n2,i]))+","+ \
        str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*(instance.transmisionOperational[n1,n2,h,i,w]+instance.transmisionOperational[n2,n1,h,i,w])/1000 for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))+","+ \
        str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*((1 - instance.lineEfficiency[n1,n2])*instance.transmisionOperational[n1,n2,h,i,w] + (1 - instance.lineEfficiency[n2,n1])*instance.transmisionOperational[n2,n1,h,i,w])/1000 for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))
        writer.writerow([my_string])
f.close()

f = open('results_output_Operational.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["Node,Period,Scenario,Season,Hour,Load_MW,Fossil_MW,CCS_MW,Nuclear_MW,Bio_MW,BioCoFire_MW,Hydro_reg_MW,Wind_onshr_MW,Wind_offshr_MW,Solar_MW,OtherRES_MW,Price_EURperMWh,MargCO2_kgCO2perMWh,storEnergyLevel_MWh,Discharge_MW,Charge_MW,LossesStorage_MW,FlowOut_MW,FlowIn_MW,LossesFlowIn_MW,LoadShed_MW"])
for n in instance.Node:
    for i in instance.Period:
        for w in instance.Scenario:
            for (s,h) in instance.HoursOfSeason:
                my_string=str(n)+","+str(value(2010+(i-1)*5))+","+str(w)+","+str(s)+","+str(h)+","+ \
                str(value(instance.sload[n,h,i,w]))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and not ('CCS',g) in instance.GeneratorsOfTechnology and (('Lignite',g) in instance.GeneratorsOfTechnology or ('Coal',g) in instance.GeneratorsOfTechnology or ('Gas',g) in instance.GeneratorsOfTechnology or ('Oil',g) in instance.GeneratorsOfTechnology))))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('CCS',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('Nuclear',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('Bio',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and not ('CCS',g) in instance.GeneratorsOfTechnology and ('CoFire',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('Hydro_reg',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('Wind_onshr',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('Wind_offshr',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and ('Solar',g) in instance.GeneratorsOfTechnology)))+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode and (('Geo',g) in instance.GeneratorsOfTechnology or ('Hydro_ror',g) in instance.GeneratorsOfTechnology or ('Wave',g) in instance.GeneratorsOfTechnology))))+","+ \
                str(instance.dual[instance.FlowBalance[n,h,i,w]])+","+ \
                str(value(sum(instance.genOperational[n,g,h,i,w]*instance.genCO2TypeFactor[g]*(3.6/instance.genEfficiency[g,i]) for g in instance.Generator if (n,g) in instance.GeneratorsOfNode)/sum(instance.genOperational[n,g,h,i,w] for g in instance.Generator if (n,g) in instance.GeneratorsOfNode)))+","+ \
                str(value(sum(instance.storOperational[n,b,h,i,w] for b in instance.Storage if (n,b) in instance.StoragesOfNode)))+","+ \
                str(value(sum(instance.storDischarge[n,b,h,i,w] for b in instance.Storage if (n,b) in instance.StoragesOfNode)))+","+ \
                str(value(sum(instance.storCharge[n,b,h,i,w] for b in instance.Storage if (n,b) in instance.StoragesOfNode)))+","+ \
                str(value(sum((1 - instance.storageDischargeEff[b])*instance.storDischarge[n,b,h,i,w] + (1 - instance.storageChargeEff[b])*instance.storCharge[n,b,h,i,w] + (1 - instance.storageBleedEff[b])*instance.storOperational[n,b,h,i,w] for b in instance.Storage if (n,b) in instance.StoragesOfNode)))+","+ \
                str(value(sum(instance.transmisionOperational[n,link,h,i,w] for link in instance.NodesLinked[n])))+","+ \
                str(value(sum(instance.transmisionOperational[link,n,h,i,w] for link in instance.NodesLinked[n])))+","+ \
                str(value(sum((1 - instance.lineEfficiency[link,n])*instance.transmisionOperational[link,n,h,i,w] for link in instance.NodesLinked[n])))+","+ \
                str(value(instance.loadShed[n,h,i,w]))
                writer.writerow([my_string])
f.close()

f = open('results_output_curtailed_prod.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["Node,RESGeneratorType,Period,ExpectedAnnualCurtailment_GWh"])
for t in instance.Technology:
    if t == 'Hydro_ror' or t == 'Wind_onshr' or t == 'Wind_offshr' or t == 'Solar':
        for (n,g) in instance.GeneratorsOfNode: 
            for i in instance.Period:
                my_string=str(n)+","+str(g)+","+str(value(2010+(i-1)*5))+","+ \
                str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*(instance.genCapAvail[n,g,h,w]*instance.genInstalledCap[n,g,i] - instance.genOperational[n,g,h,i,w])/1000 for w in instance.Scenario for (s,h) in instance.HoursOfSeason)))#+","+ \
                writer.writerow([my_string])
f.close()

f = open('results_output_EuropePlot.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["Period,genInstalledCap_MW"])
my_string=""
for g in instance.Generator:
    my_string+=","+str(g)
writer.writerow([my_string])
for i in instance.Period:
    my_string=str(value(2010+(i-1)*5))
    for g in instance.Generator:
        my_string+=","+str(value(sum(instance.genInstalledCap[n,g,i] for n in instance.Node if (n,g) in instance.GeneratorsOfNode)))
    writer.writerow([my_string])
writer.writerow([""])
writer.writerow(["Period,genExpectedAnnualProduction_GWh"])
my_string=""
for g in instance.Generator:
    my_string+=","+str(g)
writer.writerow([my_string])
for i in instance.Period:
    my_string=str(value(2010+(i-1)*5))
    for g in instance.Generator:
        my_string+=","+str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*instance.genOperational[n,g,h,i,w]/1000 for n in instance.Node if (n,g) in instance.GeneratorsOfNode for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))
    writer.writerow([my_string])
writer.writerow([""])
writer.writerow(["Period,storPWInstalledCap_MW"])
my_string=""
for b in instance.Storage:
    my_string+=","+str(b)
writer.writerow([my_string])
for i in instance.Period:
    my_string=str(value(2010+(i-1)*5))
    for b in instance.Storage:
        my_string+=","+str(value(sum(instance.storPWInstalledCap[n,b,i] for n in instance.Node if (n,b) in instance.StoragesOfNode)))
    writer.writerow([my_string])
writer.writerow([""])
writer.writerow(["Period,storENInstalledCap_MW"])
my_string=""
for b in instance.Storage:
    my_string+=","+str(b)
writer.writerow([my_string])
for i in instance.Period:
    my_string=str(value(2010+(i-1)*5))
    for b in instance.Storage:
        my_string+=","+str(value(sum(instance.storENInstalledCap[n,b,i] for n in instance.Node if (n,b) in instance.StoragesOfNode)))
    writer.writerow([my_string])
writer.writerow([""])
writer.writerow(["Period,storExpectedAnnualDischarge_GWh"])
my_string=""
for b in instance.Storage:
    my_string+=","+str(b)
writer.writerow([my_string])
for i in instance.Period:
    my_string=str(value(2010+(i-1)*5))
    for b in instance.Storage:
        my_string+=","+str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*instance.storDischarge[n,b,h,i,w]/1000 for n in instance.Node if (n,b) in instance.StoragesOfNode for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))
    writer.writerow([my_string])
f.close()

f = open('results_output_EuropeSummary.csv', 'w', newline='')
writer = csv.writer(f)
writer.writerow(["Period,AvgExpectedCO2factor_TonPerMWh,AvgELPrice_EuroPerMWh,TotExpectedAnnualCurtailedRES_GWh,TotExpectedAnnualLossesChargeDischarge_GWh,ExpectedAnnualLossesTransmission_GWh"])
for i in instance.Period:
    my_string=str(value(2010+(i-1)*5))+","+ \
    str(value(sum(instance.sceProbab[w]*instance.genOperational[n,g,h,i,w]*instance.genCO2TypeFactor[g]*(3.6/instance.genEfficiency[g,i]) for (n,g) in instance.GeneratorsOfNode for h in instance.Operationalhour for w in instance.Scenario)/sum(instance.sceProbab[w]*instance.genOperational[n,g,h,i,w] for (n,g) in instance.GeneratorsOfNode for h in instance.Operationalhour for w in instance.Scenario)))+","+ \
    str(value(sum(instance.sceProbab[w]*instance.dual[instance.FlowBalance[n,h,i,w]] for n in instance.Node for h in instance.Operationalhour for w in instance.Scenario)/value(len(instance.Operationalhour)*len(instance.Node))))+","+ \
    str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*(instance.genCapAvail[n,g,h,w]*instance.genInstalledCap[n,g,i] - instance.genOperational[n,g,h,i,w])/1000 for (n,g) in instance.GeneratorsOfNode if ('RES',g) in instance.GeneratorsOfTechnology and g != 'Bioexisting' and g != 'Bio' and g != 'Geo' for w in instance.Scenario for (s,h) in instance.HoursOfSeason)))+","+ \
    str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*((1 - instance.storageDischargeEff[b])*instance.storDischarge[n,b,h,i,w] + (1 - instance.storageChargeEff[b])*instance.storCharge[n,b,h,i,w])/1000 for (n,b) in instance.StoragesOfNode for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))+","+ \
    str(value(sum(instance.sceProbab[w]*instance.seasScale[s]*((1 - instance.lineEfficiency[n1,n2])*instance.transmisionOperational[n1,n2,h,i,w] + (1 - instance.lineEfficiency[n2,n1])*instance.transmisionOperational[n2,n1,h,i,w])/1000 for (n1,n2) in instance.BidirectionalArc for (s,h) in instance.HoursOfSeason for w in instance.Scenario)))
    writer.writerow([my_string])
writer.writerow([""])
writer.writerow(["GeneratorType,Period,genInvCap_MW,genInstalledCap_MW,TotDiscountedInvestmentCost_Euro,genExpectedAnnualProduction_GWh"])
for g in instance.Generator:
    for i in instance.Period:
        my_string=str(g)+","+str(value(2010+(i-1)*5))+","+str(value(sum(instance.genInvCap[n,g,i] for n in instance.Node if (n,g) in instance.GeneratorsOfNode)))+","+ \
        str(value(sum(instance.genInstalledCap[n,g,i] for n in instance.Node if (n,g) in instance.GeneratorsOfNode)))+","+ \
        str(value(sum(instance.discount_multiplier[i]*instance.genInvCap[n,g,i]*instance.genInvCost[g,i] for n in instance.Node if (n,g) in instance.GeneratorsOfNode))) +","+ \
        str(value(sum(instance.seasScale[s]*instance.sceProbab[w]*instance.genOperational[n,g,h,i,w]/1000 for n in instance.Node if (n,g) in instance.GeneratorsOfNode for (s,h) in instance.HoursOfSeason or w in instance.Scenario)))       
        writer.writerow([my_string])
writer.writerow([""])
writer.writerow(["StorageType,Period,storPWInvCap_MW,storPWInstalledCap_MW,storENInvCap_MWh,storENInstalledCap_MWh,TotDiscountedInvestmentCostPWEN_Euro,ExpectedAnnualDischargeVolume_GWh"])
for b in instance.Storage:
    for i in instance.Period:
        my_string=str(b)+","+str(value(2010+(i-1)*5))+","+str(value(sum(instance.storPWInvCap[n,b,i] for n in instance.Node if (n,b) in instance.StoragesOfNode)))+","+ \
        str(value(sum(instance.storPWInstalledCap[n,b,i] for n in instance.Node if (n,b) in instance.StoragesOfNode)))+","+ \
        str(value(sum(instance.storENInvCap[n,b,i] for n in instance.Node if (n,b) in instance.StoragesOfNode)))+","+ \
        str(value(sum(instance.storENInstalledCap[n,b,i] for n in instance.Node if (n,b) in instance.StoragesOfNode)))+","+ \
        str(value(sum(instance.discount_multiplier[i]*(instance.storPWInvCap[n,b,i]*instance.storPWInvCost[b,i] + instance.storENInvCap[n,b,i]*instance.storENInvCost[b,i]) for n in instance.Node if (n,b) in instance.StoragesOfNode)))+","+ \
        str(value(sum(instance.seasScale[s]*instance.sceProbab[w]*instance.storDischarge[n,b,h,i,w]/1000 for n in instance.Node if (n,b) in instance.StoragesOfNode for (s,h) in instance.HoursOfSeason or w in instance.Scenario)))
        writer.writerow([my_string])
f.close()

#import pdb; pdb.set_trace()
