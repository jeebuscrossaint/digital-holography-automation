# -*- coding: utf-8 -*-
"""
Created on Mon Mar 10 14:06:09 2025

@author: Caleb Dobias, Miguel Romer, Miguel Bandres, Daniel Cruz Delgado

This amalgamation of code decomposes an electric field into an LP mode basis,
then outputs the reconstruction success rate.
#Mode coupling equations found https://opg.optica.org/ol/fulltext.cfm?uri=ol-23-13-986

"""

# %% IMPORTS
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from MMF import MMF
import os
import re
from scipy.special import jv, kv  # Bessel functions
from scipy.optimize import fsolve
from usefulFunctions import *

#%%
#LP Mode Generation Settings

N = 500 #pixels in row/column
pxz = 50e-6/N  #field over 50 um
coreRadius = 12e-6 #Radius of core
NA = .11 #NA of Fiber
F1 = MMF(coreRadius, NA, pxz, N) #Generate multimode fiber object

wavelength = 1550e-9 #wavelenght in m, so use e-9
effectiveIndex = 1.453 #Index of glass
#note
modes = F1.modes2(wavelength, effectiveIndex, figNum=101) #Generate mode set at 850nm


#normalize modes such that sumInt = 1 (This is it's own function in other code)
for i in range(len(modes)):
    modes = modes/ np.sqrt(np.sum(np.square(np.abs(modes[i]))))


#%%Ordinary Example
#You can change the number of weights, but make sure it does not exceep the number of calculated modes from above
#To increase the calcuated modes, incrase the core diameter
numOfModes = 7
weights = randomWeights(numOfModes)

#As weights describe intensity, we calculate the E-Field with its square root
for i in range(len(weights)):
    weights[i] = np.sqrt(np.abs(weights[i]))*np.exp(1j*np.angle(weights[i]))

#This is the field we are decomposing.  It is ideal, but you can add noise here to see how it affects the reconstruction
fieldToDecomp = combinedOutput(modes,weights) #+ np.random.normal(0,.005,modes[0].shape)

#You could also offset a LP mode to treat as "Uncapturable" or "Uncoupled" light, or light lost in the cladding
#fieldToDecomp = combinedOutput(modes,weights[:-1])
#fieldToDecomp = fieldToDecomp + np.roll(modes[len(weights)-1],250)*weights[-1]


#field should be normalized, but if not
fieldToDecomp = normalizeIntensity(fieldToDecomp)
#this can be checked with sumAbs(fieldToDecomp**2) == 1 (or at least.99998)

#decomp refers to the modes present in the field
decomp = modeDecomp(fieldToDecomp, modes, numOfModes)
#recomp referes to generating a field from the idealized LP modes
recomp = combinedOutput(modes, decomp)
recomp = normalizeIntensity(recomp)#will not be normalized if decomp**2 =/= 1

#Overlap Integral is how we guage success
success = overlap2Fields(fieldToDecomp,recomp)

#plots
plt.figure()
plt.subplot(1,2,1)
pltBoth(fieldToDecomp)
plt.subplot(1,2,2)
pltBoth(recomp)


#Relative Intensity w/ Phase.  This way, everything sums to 1, assuming full resconstruction
weightIntensity = intWithPhase(weights)
decompIntensity = intWithPhase(decomp)

print("Values of Intital Field")
asPercent(weightIntensity)
print()
print("Values of Decomposition")
asPercent(decompIntensity)
print()
print(str(sumAbs(decompIntensity)*100) + "% Reconstruction")




#%% displacement efficiency  

#Displacement of SM Beam

N = 500 #pixels in row/column
pxz = 50e-6/N  #area per px, which ends up being 0.1 um in the case of 50e-6/500
coreRadius = 4.5e-6 #Radius of core
NA = .11 #NA of Fiber
F1 = MMF(coreRadius, NA, pxz, N) #Generate multimode fiber object

wavelength = 1550e-9 #wavelenght in m, so use e-9
effectiveIndex = 1.453 #Index of glass
#note
smMode = F1.modes2(wavelength, effectiveIndex, figNum=101) #Generate mode set at 850nm

#nomralize Modes (I guess for sm there's only one, but I might use this for MM fiber)
for i in range(smMode.shape[0]):
    smMode[i] = normalizeIntensity(smMode[i])

#number of pixels of displacement
displacementNum =250
#array describing displacement in um
displacementMicrons = np.linspace(0,pxz*(displacementNum-1)*1e6, displacementNum)
smTransmission = np.zeros(displacementMicrons.shape)

percentTransmission = np.zeros(displacementNum)
for displacement in range(displacementNum):
    referenceMode = np.roll(smMode, displacement)
    smTransmission[displacement] = abs(overlap2FieldsV2(smMode, referenceMode))

#displacement in um
plt.figure()
plt.plot(displacementMicrons,smTransmission*100)
plt.title("SM Coupling efficiency vs Displacement")
plt.xlabel("Displacement (um)")
plt.ylabel("Coupling Efficiency")
plt.ylim((0,100))


fwhm = findFWHM(smMode[0])
#find displacement in terms of FWHM
displacementFWHM = displacementMicrons/ (fwhm*pxz)
#displacement in FWHM
plt.figure()
plt.plot(displacementFWHM,smTransmission*100)
plt.title("SM Coupling efficiency vs Displacement")
plt.xlabel("Displacement (FWHM)")
plt.ylabel("Coupling Efficiency")
plt.ylim((0,100))

#%%
#Displacement of fundamental mode on MM Collection

N = 500 #pixels in row/column
pxz = 50e-6/N  #area per px, which ends up being 0.1 um in the case of 50e-6/500
coreRadius = 12e-6 #Radius of core
NA = .11 #NA of Fiber
F1 = MMF(coreRadius, NA, pxz, N) #Generate multimode fiber object

wavelength = 1550e-9 #wavelenght in m, so use e-9
effectiveIndex = 1.453 #Index of glass
#note
modes = F1.modes2(wavelength, effectiveIndex, figNum=101) #Generate mode set at 850nm
numModes = 3
#nomralize modes
for i in range(modes.shape[0]):
    modes[i] = normalizeIntensity(modes[i])

#number of pixels of displacement
displacementNum =250
#array describing displacement in um
displacementMicrons = np.linspace(0,pxz*(displacementNum-1)*1e6, displacementNum)
mmTransmission = np.zeros(displacementMicrons.shape)

percentTransmission = np.zeros(displacementNum)
for displacement in range(displacementNum):
    field = np.roll(modes[0], displacement)
    decomp = modeDecomp(field,modes,numModes)
    transmission = np.sum(np.square(np.abs(decomp)))
    mmTransmission[displacement] = transmission

#displacement in um
plt.figure()
plt.plot(displacementMicrons,smTransmission*100)
plt.plot(displacementMicrons,mmTransmission*100)
plt.title("MM Coupling efficiency vs Displacement")
plt.xlabel("Displacement (um)")
plt.ylabel("Coupling Efficiency")
plt.ylim((0,100))


fwhm = findFWHM(modes[0])
#find displacement in terms of FWHM
displacementFWHM = displacementMicrons/ (fwhm*pxz)
#displacement in FWHM
plt.figure()
plt.plot(displacementFWHM,mmTransmission*100)
plt.title("MM Coupling efficiency vs Displacement")
plt.xlabel("Displacement (FWHM)")
plt.ylabel("Coupling Efficiency")
plt.ylim((0,100))


