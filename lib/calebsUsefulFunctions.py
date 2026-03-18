# -*- coding: utf-8 -*-
"""
Created on Thu Aug 21 14:57:09 2025

@author: ca109683
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from MMF import MMF
from PIL import Image
import scipy

def fft(x):
    return np.fft.fftshift(np.fft.fft2(x))
def ifft(x):
    return np.fft.ifftshift(np.fft.ifft2(x))

#shorthand for np.sum(np.abs(x)))
def sumAbs(a):
    return np.sum(np.abs(a))

def logAbs(a):
    return np.log10(np.abs(a))


def sumInt(a):
    return np.sum(np.abs(a)**2)

def tupleToInt(a):
    return tuple(int(round(x)) for x in a)

#plots absolute value of a field
def pltAbs(a,ticks = 0, cmap = 'viridis',aspect = 1):
    plt.imshow(np.abs(a), cmap = cmap,aspect=aspect)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False ,
                labelbottom = False, bottom = False)

def pltLogAbs(a,ticks = 0, cmap = 'viridis',aspect = 1):
    plt.imshow(np.log10(np.abs(a)))
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False ,
                labelbottom = False, bottom = False)
        
def pltInt(a,ticks = 0, cmap = 'viridis',aspect = 1):
    plt.imshow(np.square(np.abs(a)), cmap = cmap, aspect = aspect)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False ,
                labelbottom = False, bottom = False)

#plots absolute angle of a field
def pltAngle(a,ticks = 0, cmap = 'viridis',aspect = 1):
    plt.imshow(np.angle(a), cmap = cmap,aspect = aspect)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False ,
                labelbottom = False, bottom = False)

#crops array around a centerpoint (x,y) and size
def cropArray(field, centerOfMass, cropSize):
    cropX1 = int(centerOfMass[0]-cropSize//2)
    cropY1 = int(centerOfMass[1]-cropSize//2)
    return field[cropX1:cropX1+cropSize,cropY1:cropY1+cropSize]

def full_frame(width=None, height=None):
    import matplotlib as mpl
    mpl.rcParams['savefig.pad_inches'] = 0
    figsize = None if width is None else (width, height)
    fig = plt.figure(figsize=figsize)
    ax = plt.axes([0,0,1,1], frameon=False)
    ax.get_xaxis().set_visible(False)
    ax.get_yaxis().set_visible(False)
    plt.autoscale(tight=True)
    
#plots amplitude (brightness) and angle (color) of a field
def pltBoth(a,colorOffset = .25,ticks = 0,colorRange=1,aspect = 1): #plot both amplitude and angle
    # Calculate magnitude and phase
    magnitude = np.abs(a)/ np.max(np.abs(a))
    phase = (np.angle(a)+ np.pi) / (2 * np.pi)

    hsv_image = np.zeros((magnitude.shape[0],magnitude.shape[1],3))
    hsv_image[..., 0] = (phase*colorRange+colorOffset)%1   # Hue(angle) #changed hue offset for prettier colors
    hsv_image[..., 1] = 1           # Saturation (constant)
    hsv_image[..., 2] = magnitude  # Value/Intensity (amplitude)
    
    # Convert HSV to RGB for displaying
    rgb_image = mcolors.hsv_to_rgb(hsv_image)
    
    # Plot the result
    # full_frame()
    plt.imshow(rgb_image,aspect = aspect)
    if ticks == 0:
        plt.tick_params(left = False, right = False , labelleft = False , 
                labelbottom = False, bottom = False) 
        
def genPhaseAmplitude(a,colorOffset = .25,ticks = 0,colorRange=1,aspect = 1): #plot both amplitude and angle
    # Calculate magnitude and phase
    magnitude = np.abs(a)/ np.max(np.abs(a))
    phase = (np.angle(a)+ np.pi) / (2 * np.pi)

    hsv_image = np.zeros((magnitude.shape[0],magnitude.shape[1],3))
    hsv_image[..., 0] = (phase*colorRange+colorOffset)%1   # Hue(angle) #changed hue offset for prettier colors
    hsv_image[..., 1] = 1           # Saturation (constant)
    hsv_image[..., 2] = magnitude  # Value/Intensity (amplitude)
    
    # Convert HSV to RGB for displaying
    rgb_image = mcolors.hsv_to_rgb(hsv_image)
    return rgb_image
                
        
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

#outputs an array as percent in a more pretty way, including phase
def asPercent(a):
    for i in range(len(a)):
        print(str(round(np.abs(a[i])*100,2)).zfill(5) + 
              " % at phase " + str(round(1 + np.angle(a[i])/np.pi,2)) + " π ")

#normalizes an array to sum to 1
def normalize(a):
    return a / (np.sum(np.abs(a)))

#normalizes the intensity of an electric field to 1, useful for inner products
def normalizeIntensity(a):
    return a / np.sqrt(np.sum(np.square(np.abs(a))))

#note, this does no normalization
def overlap2Fields(a,b):
    return np.sum(a * np.conj(b))

#This should normalize such that the sum of the squared field is 1.
def overlap2FieldsV2(a,b):
    num = np.sum(a * np.conj(b))
    den1 = np.sqrt(np.sum(np.square(np.abs(a))))
    den2 = np.sqrt(np.sum(np.square(np.abs(b))))
    return num/(den1*den2)

#defaults to no normalization
def modeDecomp(field, modes, numModes):
    decompMatrix = np.zeros(numModes, np.complex64)
    for i in range(numModes):
        decompMatrix[i] = overlap2FieldsV2(field, modes[i])
    return decompMatrix


#squares values but retains relative phase.  Useful for describing relative intensities
def intWithPhase(a):
    return np.square(np.abs(a))*np.exp(1j*np.angle(a))

#Rolls a matrix with wraparound.
def rollMatrix(matrix, x, y):
    matrix = np.roll(matrix, x, 1)
    matrix = np.roll(matrix, y, 0)
    return matrix

#Creates a quadratic phase mask
def generatePhaseMask(N = 50, phaseFactor = 1):
    if phaseFactor == 0:
        return np.ones((N,N))
    X,Y = np.meshgrid(np.arange(1, N+1) - (N/2 + 1),
                      np.arange(1, N+1) - (N/2 + 1))
    quadraticPhase = np.exp(1j *phaseFactor * ((X)**2 + (Y)**2)/N)
    return quadraticPhase

#applys a quadratic phase mask to a field, perhaps should combine with "generatePhaseMask"
def applyQuadraticPhase(field,phaseFactor = 1):
    quadraticPhase = generatePhaseMask(field.shape[0],phaseFactor)
    return field * quadraticPhase

#generates LP modes, N is output matrix diameter, pxz is pixel width in m, 
#coreRadius is fiber radius, NA is Numerical Aperture, wavelength is in m,
#rIndex is refractive index
def generateModes(N=50, pxz = 70e-6/50,coreRadius = 25e-6, NA =.11, 
                  wavelength = 1575e-9, rIndex=1.453):
    F1 = MMF(coreRadius, NA, pxz, N) #Generate multimode fiber object
    modes = F1.modes2(wavelength, rIndex) #Generate mode set at wavelength
    modes = modes/np.sqrt(np.sum(np.square(np.abs(modes[0]))))#normalize
    return modes

#generates a 2D circular mask, ones in the middle, zeros on the outside
def generateMask(fieldSize, maskSize):
    mask = np.zeros((fieldSize,fieldSize), dtype=bool)
    x, y = np.ogrid[:fieldSize, :fieldSize]
    circle = (x - fieldSize//2)**2 + (y - fieldSize//2)**2 <= (maskSize//2)**2
    mask[circle] = 1
    return mask

#returns index of maximum of array
def getMaxIndex(field):
    return np.unravel_index(np.argmax(field), field.shape)

#returns the centroid of a matrix that is blurred with a circle the size of maskSize
def getBlurredCentroid(array, maskSize):
    mask = generateMask(maskSize,maskSize)
    convolution = scipy.signal.fftconvolve(array, mask, mode='same')
    indices = scipy.ndimage.center_of_mass(np.square(convolution)) #returns subpixel accuracy
    return mask, convolution, indices

#removes data from all quadrants except selected quadrant
#[1,2]
#[4,3]
def filterForQuadrant(field, quadrant):
    if quadrant == 0:
        return field
    array = np.abs(field.copy())
    match quadrant:
        case 1:
            array[array.shape[0] // 2:, :] = 0
            array[:, array.shape[1] // 2:] = 0
        case 2:
            array[array.shape[0] // 2:, :] = 0
            array[:, :array.shape[1] // 2] = 0
        case 3:
            array[:array.shape[0] // 2, :] = 0
            array[:, :array.shape[1] // 2] = 0
        case 4:
            array[:array.shape[0] // 2, :] = 0
            array[:, array.shape[1] // 2:] = 0
        case _:
            print("Bad Quadrant Error, check findCentroid")
    return array

##finds "centroid" of a field, 
#if given a quadrant, filters out DC component
#[1,2]
#[4,3]
#It also technically doesn't find a centroid,
#as much as finds the peak of a gaussian blur
def findCentroid(field, quadrant=0, maskSize = 256,lineFilterWidth=1, dcCenterSize=40):
    array = np.abs(field.copy())
    if quadrant:
        array = filterForQuadrant(array, quadrant)
        array = filterDCComponents(array,lineFilterWidth,dcCenterSize)
    mask, convolution, indices = getBlurredCentroid(array, maskSize)
    return array, mask, convolution, indices

#Zeros DC components in an FFT, including the on axis components **assumign DC is in the middle**
def filterDCComponents(field, lineFilterWidth=1, centerFilterDiameter=30):
    field[field.shape[0]//2-lineFilterWidth:
                     field.shape[0]//2+lineFilterWidth,:]= 0
    field[:,field.shape[0]//2-lineFilterWidth:
                      field.shape[0]//2+lineFilterWidth]= 0
    mask = generateMask(field.shape[0],centerFilterDiameter)
    return field * (~mask) #this flips the mask 1's and 0's
    

#returns modes by (diameter, modeNumber, x, y)
#diameter is expected to be around 80, changes relative pixel size rather than core diameter
def generateModesByDiameter(startDiameter,stopDiameter, step=1, N=100, coreRadius = 25e-6, NA =.11, wavelength = 1575e-9, rIndex=1.453):
    modes = generateModes(N,startDiameter*(1e-6)/N,coreRadius,NA,wavelength, rIndex)
    modesByDiameter = np.zeros((np.abs(startDiameter-stopDiameter)//step, modes.shape[0],N,N))
    counter = 0
    for diameter in np.arange(startDiameter,stopDiameter,step):
        modes = generateModes(N,diameter*(1e-6)/N,coreRadius,NA,wavelength, rIndex)
        for ii in range(modes.shape[0]):
            modes[ii] = normalizeIntensity(modes[ii])
        modesByDiameter[counter] = modes
        counter += 1
    return modesByDiameter

#decomposes a field into the given modes, then returns the best reconstruction
def decompAndRecomp(field, modes,numModes=0):
    if numModes == 0:
        numModes = modes.shape[0]
    decomp = modeDecomp(field, modes,numModes)
    recomp = combinedOutput(modes,decomp)
    recomp = normalizeIntensity(recomp)
    return decomp, recomp

def findBestOffset(field, modes, xstart=-5, xstop=5, ystart=-5,ystop=5,step =1):
    bestFidelity = 0
    for x in np.arange(xstart,xstop,step):
        for y in np.arange(ystart,ystop,step):
            rolledField = rollMatrix(field,x,y)
            decomp, recomp = decompAndRecomp(rolledField,modes)
            fidelity = overlap2FieldsV2(recomp, rolledField)
            # print(fidelity.real)
            if (fidelity.real > bestFidelity.real):
                bestFidelity = fidelity
                optimalXOffset = x
                optimalYOffset = y
    return optimalXOffset, optimalYOffset

#note, field gets smaller with larger *diameter*. It's actually pixel size.
def findBestDiameter(field, modesByDiameter):
    bestFidelity = 0
    for diameter in range(modesByDiameter.shape[0]): #for diameter in number of diameters
        decomp, recomp = decompAndRecomp(field, modesByDiameter[diameter])
        fidelity = overlap2FieldsV2(recomp, field)
        # print(fidelity.real)
        if (fidelity.real > bestFidelity.real):
            bestFidelity = fidelity
            bestDiameter = diameter
    return bestDiameter

#note, field gets smaller with larger *diameter*. It's actually pixel size.
def findBestPhase(field, modes, start = -1, stop = 1, step = .1):
    bestFidelity = 0
    for phase in np.arange(start,stop,step):
        phasedField = applyQuadraticPhase(field, phase)
        decomp, recomp = decompAndRecomp(phasedField, modes)
        fidelity = overlap2FieldsV2(recomp, phasedField)
        # print(fidelity.real)
        if (fidelity.real > bestFidelity.real):
            bestFidelity = fidelity
            optimalPhase = phase
    return optimalPhase

def adjustField(field, phase, xOffset,yOffset):
    adjustedField = applyQuadraticPhase(field, phase)
    adjustedField = rollMatrix(adjustedField,xOffset,yOffset)
    adjustedField = normalizeIntensity(adjustedField)
    return adjustedField

#X and Y are flipped, didn't figure out this bug yet
def makeButterworth(N,centerX=0, centerY=0, wc=15,n=3):
    if (wc == 0 or n == 0):
        return np.ones((N,N))
    X,Y = np.meshgrid(np.arange(N), np.arange(N))
    W = np.sqrt((X-centerX)**2 + (Y-centerY)**2)
    return (1/(1+(W/wc)**(2*n)))

def fourier_interp_2d(img, span=32, output_size=64, sample_limit=32, offset=(0,0)): 
    '''
    Interpolate using Fourier Fine-Binning Method (Ransom 2002).
    New samples are generated from weighted sum of original image values in
    a range 'span' about the center

    Parameters
    ----------
    img : Array 2D
        Input image over which interpolation will occur
    span : float, optional
        Range that will be sampled for the interpolation. New image will span
        a value of span/2 from center in all direction. The default is 32.
    output_size : int, optional
        Number of samples in output image. The default is 64.
    sample_limit : int, optional
        How many integer samples are taken ito the sum for the interpolation.
        The default is 32.
    offset : tuple (x,y), optional
        x and y values for offset from center of desired data. Default is 0,0.

    Returns
    -------
    A_r: Array 2D
        [output_size x output_size] array of complex numbers.
    r_vec : Array 1D
        Vector of real-valued sampled locations.

    '''
    N0 = img.shape[0] #Size of input image (assumed to be square)
   
   
    out_min = N0/2-span/2 #Minimum coordinate to interpolate within
    out_max = out_min + span #Maximum coordinate to interpolate within
   
    #Sample points to be filled in
    r_vec_x = np.linspace(out_min, out_max, output_size+1)[0:output_size] + offset[0]
    r_vec_y = np.linspace(out_min, out_max, output_size+1)[0:output_size] + offset[1]
   
    sample_min = (N0 - sample_limit)//2 #Minimum used sample index from img
    sample_max = sample_min + sample_limit #Maximum used sample index from img
   
    #Indeces to be used in sum
    Kx = np.arange(N0)[sample_min:sample_max] + round(offset[0])
    Ky = np.arange(N0)[sample_min:sample_max] + round(offset[1])
   
    #'Cropped' img; only these values will be summed over
    A_k = img[sample_min+round(offset[0]):sample_max+round(offset[0]),
              sample_min+round(offset[1]):sample_max+round(offset[1])]
   
    # Meshgrid can get pretty memory intensive
    kx1, ky1, rx1= np.meshgrid(Kx.astype(complex), Ky.astype(complex), r_vec_x.astype(complex), indexing='ij')
    rx2, ky2, ry2= np.meshgrid(r_vec_x.astype(complex), Ky.astype(complex), r_vec_y.astype(complex), indexing='ij')
   
    kernel_x = np.sinc(rx1 - kx1)
    kernel_y = np.sinc(ry2 - ky2).T
   
    phasor_x = np.exp(-1j * np.pi * ((rx1 - kx1) / N0))
    phasor_y = np.exp(-1j * np.pi * ((ry2 - ky2) / N0))
   
   
    # XXX: x and y flipping might need to be accounted for
    A_k2x = np.tile(A_k.T, (len(r_vec_x), 1, 1)).T
   
    A_temp = np.zeros((A_k.shape[0], len(r_vec_y)), dtype='D')
    A_r = np.zeros((len(r_vec_x), len(r_vec_y)), dtype='D')
    
    A_temp[:,:] = np.sum(A_k2x.astype(complex) * phasor_x * kernel_x, axis=(0))
   
    A_k2y = np.tile(A_temp, (len(r_vec_y), 1, 1))
   
    A_r[:,:] = np.sum(A_k2y.astype(complex) * phasor_y * kernel_y, axis=(1))
   
   
    return A_r.T, r_vec_x, r_vec_y

#intakes a list of PNGs in current folder and makes a gif
def makeGifFromPNG(filenames, gifName, msPerFrame=1000):
    images = [Image.open(f'{f}') for f in filenames]
    # Save as GIF
    images[0].save(
        gifName,
        save_all=True,
        append_images=images[1:],
        duration=msPerFrame,   # duration in ms
        loop=0)          # 0 = infinite loop