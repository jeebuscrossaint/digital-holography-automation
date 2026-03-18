# -*- coding: utf-8 -*-
"""
Created on Thu Feb 19 16:14:43 2026

@author: mecdm
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from MMF import MMF
import os
import re
from scipy.special import jv, kv  # Bessel functions
from scipy.optimize import fsolve
from scipy.interpolate import interp1d
from usefulFunctions import *

#shorthand for np.sum(np.abs(x)))
def sumAbs(a):
    return np.sum(np.abs(a))

#plots absolute value of a field
def pltAbs(a,ticks = 0, cmap = 'bone'):
    plt.imshow(np.abs(a), cmap = cmap)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False , 
                labelbottom = False, bottom = False) 

#plots absolute angle of a field
def pltAngle(a,ticks = 0, cmap = 'viridis'):
    plt.imshow(np.angle(a), cmap = cmap)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False , 
                labelbottom = False, bottom = False) 
        
#plots amplitude (brightness) and angle (color) of a field
def pltBoth(a,colorOffset = .25,ticks = 0): #plot both amplitude and angle
    # Calculate magnitude and phase
    magnitude = np.abs(a)/ np.max(np.abs(a))
    phase = (np.angle(a)+ np.pi) / (2 * np.pi)
    
    hsv_image = np.zeros((magnitude.shape[0],magnitude.shape[1],3))
    hsv_image[..., 0] = (phase+colorOffset)%1   # Hue (angle) #changed hue offset for prettier colors
    hsv_image[..., 1] = 1           # Saturation (constant)
    hsv_image[..., 2] = magnitude  # Value/Intensity (amplitude)
    
    # Convert HSV to RGB for displaying
    rgb_image = mcolors.hsv_to_rgb(hsv_image)
    
    # Plot the result
    plt.imshow(rgb_image)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False , 
                labelbottom = False, bottom = False) 
        
#plots all modes in a, unless cut off by numShown
def pltAll(a, columns = 6, numShown=-1,ticks = 0, colorOffset= .25):
    if numShown == -1:
        numShown = a.shape[0]
    rows = numShown//columns
    for i in range(numShown):
        plt.subplot(rows+1, columns, i+1)
        pltBoth(a[i],ticks=ticks, colorOffset=colorOffset)
        if ticks == 0:
            plt.tick_params(left = False, right = False , labelleft = False , 
                        labelbottom = False, bottom = False) 

#generates a random distribution of (a) values w/ complex phases that sum to 1
def randomWeights(a):
    amplitude = np.random.default_rng().random(a)
    amplitude = amplitude/np.sum(amplitude)
    phase = np.exp(2j*np.pi*np.random.default_rng().random(a))
    array = np.multiply(amplitude, phase)
    return array

#easy way to output a field given an amount of weights
def combinedOutput(modes, weights):
    field = np.zeros(modes[0].shape)
    for i in range(len(weights)):
        field = field + modes[i]*weights[i]
    return field

#outputs an array as percent in a more pretty way
def asPercent(a):
    for i in range(len(a)):
        print(str(round(np.abs(a[i])*100,2)).zfill(5) + 
              " % at phase " + str(round(1 + np.angle(a[i])/np.pi,2)) + " π ")

#sums to 1
def normalize(a):
    return a / (np.sum(np.abs(a)))

#sums where  a * a.conj == 1
def normalizeIntensity(a):
    return a / np.sqrt(np.sum(np.square(np.abs(a))))

#note, this does no normalization
def overlap2Fields(a,b):
    return np.sum(a * np.conj(b))

#This normalizes a and b such that their intensities sum to 1
def overlap2FieldsV2(a,b):
    num = np.sum(a * np.conj(b))
    den1 = np.sqrt(np.sum(np.square(np.abs(a))))
    den2 = np.sqrt(np.sum(np.square(np.abs(b))))
    return num/(den1*den2)

#defaults to no normalization
def modeDecomp(field, modes, numModes):
    decompMatrix = np.zeros(numModes, np.complex64)
    for i in range(numModes):
        decompMatrix[i] = overlap2Fields(field, modes[i])
    return decompMatrix

#intensit integral, sum (square(abs(field)))
def sumInt(a):
    return np.sum(np.square(np.abs(a)))

def intWithPhase(a):
    return np.square(np.abs(a))*np.exp(1j*np.angle(a))

def middleSlice(a):
    return a[a.shape[0]//2]

#This one is a little hacky, it assumes a Gaussian-like thing centered on the middlest row
#Returns FWHM in pixels with interpolation
def findFWHM(a):
    row = a[a.shape[0]//2]
    index = np.linspace(0,a.shape[0]-1,a.shape[0])
    maximum = np.max(row)
    halfMax = maximum / 2.0
    indices = np.where(row>= halfMax)[0]
    
    leftIndex = indices[0]
    rightIndex = indices[-1]
    
    x1 = index[leftIndex-1]
    x2 = index[leftIndex]
    y1 = row[leftIndex -1]
    y2 = row[leftIndex]
    leftFloat = x1 + (halfMax - y1) * (x2 - x1) / (y2 - y1)
    
    x1 = index[rightIndex-1]
    x2 = index[rightIndex]
    y1 = row[rightIndex -1]
    y2 = row[rightIndex]
    rightFloat = x1 + (halfMax - y1) * (x2 - x1) / (y2 - y1)
    
    return rightFloat - leftFloat