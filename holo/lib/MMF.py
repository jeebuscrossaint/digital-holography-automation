# -*- coding: utf-8 -*-
"""
Created on Mon Mar 10 14:51:18 2025

@author: Miguel Bandres
"""
import functools
import math

import numpy as np
from scipy.special import jv, kv  # Bessel functions
from scipy.optimize import fsolve
import warnings

#cartesian units to polar units
def cart2pol(x: float, y: float) -> tuple[float]:
    theta = np.arctan2(y,x); rho = np.sqrt(x**2+y**2)
    return(theta,rho)  

#outputs laguerre coefficients to the nth term with alpha
def laguerre_coef(n: int, alpha: int) -> np.ndarray:
    coeff = np.zeros(n+1); factorial_l = math.factorial(n+alpha)
    for m in range(0,n+1):
        bino = factorial_l/(math.factorial(n-m)*math.factorial(n+alpha-(n-m)))
        coeff[n-m] = bino*(-1)**m/math.factorial(m)
    return(coeff)

#generates LP Modes 
def LP_mode(l: int, m: int, w0: float, theta: float, radius: float) -> tuple[np.ndarray]:
        mfd = w0/(2*np.sqrt(2)); V = 1/(mfd**2)
        LG = laguerre_coef((m-1),l)
        F_lm = radius**l*np.polyval(LG,V*radius**2)*np.exp(-0.5*V*radius**2)
        l_TH = l*theta;
        ex = F_lm*np.cos(l_TH); ey = F_lm*np.sin(l_TH)
        if np.sqrt(np.sum(abs(ex)**2)) == 0:
            print(l,m)
        if np.sqrt(np.sum(abs(ex)**2)) != 0:
            ex = ex/np.sqrt(np.sum(abs(ex)**2))
        if (l>0):
            if np.sqrt(np.sum(abs(ey)**2)) == 0:
                print(l,m)
            if np.sqrt(np.sum(abs(ey)**2)) != 0:
                ey = ey/np.sqrt(np.sum(abs(ey)**2))
        return(ex,ey)

def LP_mismatch(coreRadius, nCore, nCladding, wavelength, order, u):
    k = 2 * np.pi / wavelength # Wavenumber
    beta = np.sqrt(k**2 * nCore**2 - (u / coreRadius) ** 2) # Beta value
    w = coreRadius * np.sqrt(beta**2 - k**2 * nCladding**2) # w value (cladding)
    coreTerm = jv(order, u) / (u * jv(order - 1, u)) # Core function
    claddingTerm = kv(order, w) / (w * kv(order - 1, w)) # Cladding function
    residual = coreTerm + claddingTerm # Calculate mismatch
    return residual

def _polar_grid(X, Y, coreRadius):
    """Polar coordinates, core/cladding masks and the distinct radii of each
    region. Identical for every mode on one grid, so GET_LP_mode can take
    them precomputed instead of re-sorting the grid per mode."""
    angle, rad = np.arctan2(Y, X), np.sqrt(X**2 + Y**2)
    inCore = rad <= coreRadius
    inCladding = rad > coreRadius
    return (angle, inCore, inCladding,
            np.unique(rad[inCore], return_inverse=True),
            np.unique(rad[inCladding], return_inverse=True))


# modes2 is called on the same few grids (one per FOV candidate) for every
# wavelength, so keep each grid's polar data across calls.
_GRIDS = {}


def GET_LP_mode(X, Y, order, u, w, coreRadius, grid=None):
    
    dx = abs(X[0, 0] - X[0, 1])
    dy = abs(Y[0, 1] - Y[1, 1])

    # Convert to polar coordinates
    if grid is None:
        grid = _polar_grid(X, Y, coreRadius)
    angle, inCore, inCladding, coreRadii, claddingRadii = grid

    # Initialize mode profiles
    modeCos = np.zeros_like(X)
    modeSin = np.zeros_like(X)

    # Calculate the cos and sin terms
    cosTerm = np.cos(order * angle)
    sinTerm = np.sin(order * angle)

    # Compute core and cladding functions. The Bessel calls are ~80% of mode
    # generation, so evaluate each only where it is used (jv in the core, kv in
    # the cladding) and only once per distinct radius (the square grid repeats
    # radii ~8x). Same inputs to the same functions: results are bit-identical.
    def radial(fn, arg_scale, norm, radii):
        r_unique, inverse = radii
        return (fn(order, arg_scale * r_unique) / norm)[inverse]

    coreBessel = radial(jv, u / coreRadius, jv(order, u), coreRadii)
    claddingBessel = radial(kv, w / coreRadius, kv(order, w), claddingRadii)

    # Compute mode profiles
    modeCos[inCore] = coreBessel * cosTerm[inCore]
    modeSin[inCore] = coreBessel * sinTerm[inCore]

    modeCos[inCladding] = claddingBessel * cosTerm[inCladding]
    modeSin[inCladding] = claddingBessel * sinTerm[inCladding]

    # Normalize to total energy of 1
    normCos = np.sqrt(np.sum(modeCos**2) * dx * dy)
    normSin = np.sqrt(np.sum(modeSin**2) * dx * dy)

    modeCos /= normCos if normCos != 0 else 1
    modeSin /= normSin if normSin != 0 else 1

    # Handle NaN values
    modeCos = np.nan_to_num(modeCos)
    modeSin = np.nan_to_num(modeSin)

    return modeCos, modeSin

# The LP eigenvalues depend only on the fiber and the wavelength, not on the
# grid a basis is sampled on, but modes2 is called once per FOV candidate (11 per
# frame). Solving once per wavelength cuts mode generation by ~half; the solve
# is unchanged, so the bases are bit-identical.
@functools.lru_cache(maxsize=256)
def _lp_solutions(coreRadius, numAperture, wavelength, nCore):
    k = 2*np.pi/wavelength
    nCladding = np.sqrt(nCore**2 - numAperture**2)
    V = coreRadius*numAperture*(2*np.pi/(wavelength))     

    nu = 5000
    u = np.linspace(0, V - 0.001, nu)
    
    coreTerm = np.zeros(nu)
    claddingTerm = np.zeros(nu)
    signChange = np.zeros(nu)


    # Initialize variables
    order = 0
    LP = []  # List to store mode solutions
    
    while True:
        #print('Order:', order)
        # Beta value
        beta = np.sqrt(k**2 * nCore**2 - (u / coreRadius) ** 2)
    
        # w value (cladding)
        w = coreRadius * np.sqrt(beta**2 - k**2 * nCladding**2)
    
        # Core function
        coreTerm = jv(order, u) / (u * jv(order - 1, u))
    
        # Cladding function
        claddingTerm = kv(order, w) / (w * kv(order - 1, w))
    
        # Compute result
        Res = coreTerm + claddingTerm
    
        # Detect sign changes
        signChange = (np.sign(Res[1:]) != np.sign(Res[:-1])) * (Res[1:] > Res[:-1])
        coarseSolutions = np.where(signChange)[0] + 1
    
        # Find exact solutions using root-finding
        for iSolution in range(len(coarseSolutions)):
            minRange = u[coarseSolutions[iSolution] - 1]
            maxRange = u[coarseSolutions[iSolution]]
    
            # Find the exact root
            u_solution = fsolve(LP_mismatch, [minRange, maxRange], (coreRadius, nCore, nCladding, wavelength, order))[0]

            LP.append({
                'u': u_solution,
                'l': order,
                'beta': np.sqrt(k**2 * nCore**2 - (u_solution / coreRadius)**2),
                'w': np.sqrt(V**2 - u_solution**2),
                'm': iSolution
            })   
    
        if len(coarseSolutions) == 0:
            break  # Stop if no solutions found
    
        # Move to the next order
        order += 1
    return V, tuple(LP)

# %% CLASSES

class MMF():
    def __init__(self, coreRadius: float, numAperture: float, 
                 pixelSize: float=1e-6, pixelNumber: float=512):
        warnings.filterwarnings("ignore")
        self.r_core = coreRadius
        self.NA = numAperture
        self.pxz = pixelSize #Sampling distance of array
        self.N = pixelNumber #Number of pixels to be used for array
        
        xx = np.arange(-0.5*self.N,0.5*self.N)*self.pxz; yy = xx; # axis
        [self.XX,self.YY] = np.meshgrid(xx,yy); 
        [self.theta,self.radius] = cart2pol(self.XX,self.YY);  # axis
        self.MDS = {}
        
        

    # approximate solutions from Daniel  
    def modes(self, wavelength: float, maxMG: int, figNum=0) -> list[np.ndarray]:
        V = self.r_core*self.NA*(2*np.pi/(wavelength))
        mfd = 2*self.r_core*( 0.65 + 1.619/V**(3/2) + 2.879/V**6 )
        
        
        Nx = np.size(self.theta,1)
        l = np.arange(0,maxMG+1); 
        m = np.arange(1,maxMG+1); 
        [L,M] = np.meshgrid(l,m)
        MG = 2*M+L-1; MG = MG.flatten('F')
        MMG = MG.argsort(); MG.sort(); idxes = np.array((MG<=maxMG).nonzero()); aaa = MMG[idxes]
        L = L.flatten('F'); L = L[aaa]; M = M.flatten('F'); M = M[aaa]; O = L
        mcnt =  np.size(L[L==0]) + 2*np.size(L[L>0]);    
        MDS = np.zeros((mcnt,Nx,Nx))
        LL = np.zeros((1,mcnt)); MM = np.zeros((1,mcnt)); OO = np.zeros((1,mcnt))
        idx = 0
        for i in range(0, np.size(L)):
            print(i)
            ll = L[0,i]; mm = M[0,i]
            (Ex,Ey) = LP_mode(ll,mm,mfd,self.theta,self.radius)
            MDS[idx,:,:] = Ex
            if ll==0:
                OO[0,idx] = -1; LL[0,idx] = ll; MM[0,idx] = mm
            else:
                OO[0,idx] = 0; LL[0,idx] = ll; MM[0,idx] = mm;
            idx = idx+1
            if ll>0:
                MDS[idx,:,:] = Ey
                OO[0,idx] = 1; LL[0,idx] = ll; MM[0,idx] = mm
                idx = idx+1
        self.L = LL; self.M = MM; self.O = OO
        self.mnt = self.L.size
        self.MDS[f'{wavelength}'] = MDS
        # if figNum:
        #     montage(MDS, figNum)
        return(MDS) 
    
    # "exact" solutions from Dr. Bandres
    def modes2(self, wavelength: float, nCore=1.453, figNum=0) -> list[np.ndarray]:
        flag_Order = True
        V, LP = _lp_solutions(self.r_core, self.NA, wavelength, nCore)
        LP = list(LP)

        # Remove the first empty entry if necessary
        # if len(LP) > 0:
        #     LP.pop(0)
        
        # Calculate total number of modes
        totalNumModes = len(LP) + sum(1 for mode in LP if mode['l'] > 0)
        
        print(f'Found {totalNumModes} LP modes ({sum(1 for mode in LP if mode["l"] > 0) * 2} angular momentum modes).')
        
        mfd = 2*self.r_core*( 0.65 + 1.619/V**(3/2) + 2.879/V**6 )
        

        if flag_Order:
            LP = sorted(LP, key=lambda x: -x["beta"])
   

        MDS = []
        counter = 0
    
        key = (self.N, self.pxz, self.r_core)
        if key not in _GRIDS:
            if len(_GRIDS) >= 64:              # ~1 MB each at N=200; a sweep uses ~11
                _GRIDS.clear()
            _GRIDS[key] = _polar_grid(self.XX, self.YY, self.r_core)
        for lp in LP:
            mC, mS = GET_LP_mode(self.XX,self.YY, lp["l"], lp["u"], lp["w"], self.r_core,
                                 grid=_GRIDS[key])
    
            # Store cosine component
            MDS.append(mC)
            counter += 1
    
            # Store sine component if l ≠ 0
            if lp["l"] != 0:
                MDS.append(mS)
                counter += 1
       
        MDS = np.asarray(MDS[:36])
        #print(MDS.shape)
        self.MDS[f'{wavelength}'] = MDS
        # if figNum:
        #     montage(MDS, figNum)
        return(MDS)  