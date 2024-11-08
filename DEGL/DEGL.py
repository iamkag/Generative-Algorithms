import numpy as np
import warnings
import math
import shapely
from random import randint
import random

try:
    from joblib import Parallel, delayed
    import multiprocessing

    HaveJoblib = True
except ImportError:
    HaveJoblib = False


def get_Data(degl):
    obj = degl.GlobalBestPosition
    newOrder = [shapely.affinity.rotate(shapely.affinity.translate(degl.Order[j], xoff=obj[j * 3], yoff=obj[j * 3 + 1]),
                                        obj[j * 3 + 2], origin='centroid') for j in range(len(degl.Order))]
    unionNewOrder = shapely.ops.cascaded_union(newOrder)
    remaining = (degl.Stock).difference(unionNewOrder)

    return [newOrder, remaining]


class Degl:
    """ Differential evolution algorithm DE with
global and local neighborhood topologies).
        
           degl = Degl(ObjectiveFcn, nVars,, ...) creates the Degl object stored in variable degl and 
            performs all initialization tasks (including calling the output function once, if provided).
        
        degl.optimize() subsequently runs the whole iterative process.
        
        After initialization, the degl object has the following properties that can be queried (also during the 
            iterative process through the output function):
            o All the arguments passed during boject (e.g., pso.MaxIterations, pso.ObjectiveFcn,  pso.LowerBounds, 
                etc.). See the documentation of the __init__ member below for supported options and their defaults.
            o Iteration: the current iteration. Its value is -1 after initialization 0 or greater during the iterative
                process.
            o CurrentGenFitness: the current swarm's fitnesses for all particles (nParticles x 1)
            o PreviousBestPosition: the best-so-far positions found for each individual (nParticles x nVars)
            o PreviousBestFitness: the fitnesses of the best-so-far individuals (nParticles x 1)
            o GlobalBestFitness: the overall best fitness attained found from the beginning of the iterative process
            o GlobalBestPosition: the overall best position found from the beginning of the iterative process
            o AdaptiveNeighborhoodSize: the current neighborhood size
            o MinNeighborhoodSize: the minimum neighborhood size allowed
            o AdaptiveInertia: the current value of the inertia weight
            o StallCounter: the stall counter value (for updating inertia)
            o StopReason: string with the stopping reason (only available at the end, when the algorithm stops)
            o GlobalBestSoFarFitnesses: a numpy vector that stores the global best-so-far fitness in each iteration. 
                Its size is MaxIterations+1, with the first element (GlobalBestSoFarFitnesses[0]) reserved for the best
                fitness value of the initial swarm. Accordingly, pso.GlobalBestSoFarFitnesses[pso.Iteration+1] stores 
                the global best fitness at iteration pso.Iteration. Since the global best-so-far is updated only if 
                lower that the previously stored, this is a non-strictly decreasing function. It is initialized with 
                NaN values and therefore is useful for plotting it, as the ydata of the matplotlib line object (NaN 
                values are just not plotted). In the latter case, the xdata would have to be set to 
                np.arange(pso.MaxIterations+1)-1, so that the X axis starts from -1.
    """

    def __init__(self
                 , ObjectiveFcn
                 , nVars
                 , LowerBounds=None
                 , UpperBounds=None
                 , D=None
                 , MaxIterations=None
                 , Nf=0.1
                 , a=0.8
                 , b=0.8
                 , w_min=0.4
                 , w_max=0.6
                 , FunctionTolerance=1.0e-6
                 , MaxStallIterations=20
                 , OutputFcn=None
                 , UseParallel=False
                 , Stock=None
                 , Order=None
                 , remaining=None
                 , newOrder=None
                 , u=None
                 ):
        """ The object is initialized with two mandatory positional arguments:
                o ObjectiveFcn: function object that accepts a vector (the particle) and returns the scalar fitness 
                                value, i.e., FitnessValue = ObjectiveFcn(Particle)
                o nVars: the number of problem variables
            The algorithm tries to minimize the ObjectiveFcn.
            
            The arguments LowerBounds & UpperBounds lets you define the lower and upper bounds for each variable. They 
            must be either scalars or vectors/lists with nVars elements. If not provided, LowerBound is set to -1000 
            and UpperBound is set to 1000 for all variables. If vectors are provided and some of its elements are not 
            finite (NaN or +-Inf), those elements are also replaced with +-1000 respectively.
            
            The rest of the arguments are the algorithm's options:
                o D (default:  min(200,10*nVars)): Number of chromosomes in the population, an integer greater than 1.
                o Nf (default: 0.1): Neighborhood size fraction
                o alpha (default: 0.8): Scale factor.
                o beta (default: 0.8): Scale factor.
                o wmin (default: 0.4): Minimum weight.
                o wmax (default: 0.8): Maximum weight.
                o MinNeighborsFraction (default: 0.25): Minimum adaptive neighborhood size, a scalar in [0, 1].
                o FunctionTolerance (default: 1e-6): Iterations end when the relative change in best objective function 
                    value over the last MaxStallIterations iterations is less than options.FunctionTolerance.
                o MaxIterations (default: 100*nVars): Maximum number of iterations.
                o MaxStallIterations (default: 20): Iterations end when the relative change in best objective function 
                    value over the last MaxStallIterations iterations is less than options.FunctionTolerance.
                o OutputFcn (default: None): Output function, which is called at the end of each iteration with the 
                    iterative data and they can stop the solver. The output function must have the signature 
                    stop = fun(), returning True if the iterative process must be terminated. degl is the 
                    deglObject object (self here). The output function is also called after population initialization 
                    (i.e., within this member function).
                o UseParallel (default: False): Compute objective function in parallel when True. The latter requires
                    package joblib to be installed (i.e., pip install joplib or conda install joblib).
                o Stock: Stock useful for fitness function calculation.
                o Order: Order useful for fitness function calculation.
                o Remaining: Remaining useful for fitness function calculation and plots.
                o newOrder: The order with the transformation according to the current solution useful for fitness function calculation and plots.
                o u: New temporary solution used in fitness calculation for u vector.

        """
        self.ObjectiveFcn = ObjectiveFcn
        self.nVars = nVars
        self.Nf = Nf
        self.a = a
        self.b = b
        self.w_min = w_min
        self.w_max = w_max
        self.Order = Order
        self.Stock = Stock
        self.remaining = remaining
        self.newOrder = newOrder

        # assert options validity (simple checks only) & store them in the object
        if D is None:
            self.D = min(200, 10 * nVars)
        else:
            assert np.isscalar(D) and D > 1, \
                "The D option must be a scalar integer greater than 1 and not None."
            self.D = max(2, int(round(self.D)))

        assert np.isscalar(FunctionTolerance) and FunctionTolerance >= 0.0, \
            "The FunctionTolerance option must be a scalar number greater or equal to 0."
        self.FunctionTolerance = FunctionTolerance

        if MaxIterations is None:
            self.MaxIterations = 100 * nVars
        else:
            assert np.isscalar(MaxIterations), "The MaxIterations option must be a scalar integer greater than 0."
            self.MaxIterations = max(1, int(round(MaxIterations)))
        assert np.isscalar(MaxStallIterations), \
            "The MaxStallIterations option must be a scalar integer greater than 0."
        self.MaxStallIterations = max(1, int(round(MaxStallIterations)))

        self.OutputFcn = OutputFcn
        assert np.isscalar(UseParallel) and (isinstance(UseParallel, bool) or isinstance(UseParallel, np.bool_)), \
            "The UseParallel option must be a scalar boolean value."
        self.UseParallel = UseParallel

        # lower bounds
        if LowerBounds is None:
            self.LowerBounds = -1000.0 * np.ones(nVars)
        elif np.isscalar(LowerBounds):
            self.LowerBounds = LowerBounds * np.ones(nVars)
        else:
            self.LowerBounds = np.array(LowerBounds, dtype=float)
        self.LowerBounds[~np.isfinite(self.LowerBounds)] = -1000.0
        assert len(self.LowerBounds) == nVars, \
            "When providing a vector for LowerBounds its number of element must equal the number of problem variables."
        # upper bounds
        if UpperBounds is None:
            self.UpperBounds = 1000.0 * np.ones(nVars)
        elif np.isscalar(UpperBounds):
            self.UpperBounds = UpperBounds * np.ones(nVars)
        else:
            self.UpperBounds = np.array(UpperBounds, dtype=float)
        self.UpperBounds[~np.isfinite(self.UpperBounds)] = 1000.0
        assert len(self.UpperBounds) == nVars, \
            "When providing a vector for UpperBounds its number of element must equal the number of problem variables."

        assert np.all(self.LowerBounds <= self.UpperBounds), \
            "Upper bounds must be greater or equal to lower bounds for all variables."

        # check that we have joblib if UseParallel is True
        if self.UseParallel and not HaveJoblib:
            warnings.warn(
                """If UseParallel is set to True, it requires the joblib package that could not be imported; swarm objective values will be computed in serial mode instead.""")
            self.UseParallel = False

        # Initial swarm: randomly in [lower,upper] and if any is +-Inf in [-1000, 1000]
        lbMatrix = np.tile(self.LowerBounds, (self.D, 1))
        ubMatrix = np.tile(self.UpperBounds, (self.D, 1))
        bRangeMatrix = ubMatrix - lbMatrix
        self.z = lbMatrix + np.random.rand(self.D, nVars) * bRangeMatrix

        # Initial fitness
        self.CurrentGenFitness = np.zeros(self.D)
        self.__evaluateDEz()

        # Initial best-so-far individuals and global best
        self.PreviousBestPosition = self.z.copy()
        self.PreviousBestFitness = self.CurrentGenFitness.copy()

        bInd = self.CurrentGenFitness.argmin()
        self.GlobalBestFitness = self.CurrentGenFitness[bInd].copy()
        self.GlobalBestPosition = self.PreviousBestPosition[bInd, :].copy()

        # iteration counter starts at -1, meaning initial population
        self.Iteration = -1;
        self.StallCounter = 0;

        # Keep the global best of each iteration as an array initialized with NaNs. First element is for initial swarm,
        # so it has self.MaxIterations+1 elements. Useful for output functions, but is also used for the insignificant
        # improvement stopping criterion.
        self.GlobalBestSoFarFitnesses = np.zeros(self.MaxIterations + 1)
        self.GlobalBestSoFarFitnesses.fill(np.nan)
        self.GlobalBestSoFarFitnesses[0] = self.GlobalBestFitness

        # call output function, but neglect the returned stop flag
        if self.OutputFcn:
            self.OutputFcn(self)

    def __evaluateDEz(self):
        """ Helper private member function that evaluates the population, by calling ObjectiveFcn either in serial or
            parallel mode, depending on the UseParallel option during initialization.
        """
        n = self.D
        if self.UseParallel:
            nCores = multiprocessing.cpu_count()
            self.CurrentGenFitness[:] = Parallel(n_jobs=nCores)(
                delayed(self.ObjectiveFcn)(self.z[i, :]) for i in range(n))
        else:
            self.CurrentGenFitness[:] = [self.ObjectiveFcn(self.z[i, :], self.nVars, self.Stock, self.Order) for i in
                                         range(self.D)]

    def __evaluateDEu(self):
        """ Helper private member function that evaluates the population, by calling ObjectiveFcn either in serial or
            parallel mode, depending on the UseParallel option during initialization.
        """
        n = self.D
        if self.UseParallel:
            nCores = multiprocessing.cpu_count()
            self.CurrentGenFitness[:] = Parallel(n_jobs=nCores)(
                delayed(self.ObjectiveFcn)(self.u[i, :]) for i in range(n))
        else:
            self.CurrentGenFitness[:] = [self.ObjectiveFcn(self.u[i, :], self.nVars, self.Stock, self.Order) for i in
                                         range(self.D)]

    def optimize(self):
        """ Runs the iterative process on the initialized swarm. """
        nVars = self.nVars
        # find radius
        k = math.floor(self.D * self.Nf)  # Neighborhood size
        L = np.zeros([self.D, nVars])
        g = np.zeros([self.D, nVars])
        y = np.zeros([self.D, nVars])
        self.u = np.zeros([self.D, nVars])
        AdaptiveNeighborhoodSize = 3  # range [i − k, i + k]

        # find radius
        k = round(self.D * self.Nf)  # Neighborhood size

        # start the iteration
        doStop = False

        while not doStop:
            self.Iteration += 1
            # Calculate weight w through eq. (6) => w = w min + (w max − w min ) *(t − 1) / (I max − 1)

            w = self.w_min + (self.w_max - self.w_min) * (self.Iteration - 1) / (self.MaxIterations - 1)

            # -------------------start of loop through ensemble------------------------
            # for i = 1 to D
            for i in range(0, self.D):

                # find neighbors
                neighbors = np.array([w for w in range((i - k), (i + k + 1))])
                neighbors[neighbors < 0] += neighbors[neighbors < 0] + self.D
                neighbors[neighbors > self.D - 1] = neighbors[neighbors > self.D - 1] - self.D

                # print(neighbors)
                neighbors_idx = np.random.choice(neighbors, size=AdaptiveNeighborhoodSize, replace=False)
                neighbors_idx[neighbors_idx == i] = neighbors_idx[2];  # do not select itself, i.e., index i
                p = neighbors_idx[0]
                q = neighbors_idx[1]

                bInd = self.PreviousBestFitness[neighbors].argmin()
                bestNeighbor = neighbors[bInd]
                z_best = self.z[bestNeighbor]

                #   Mutate using eq. (3)–(5) → new vector yi
                #   Li = zi + α · (zbesti − zi) + β · (zp − zq), (3)
                L[i,] = self.z[i,] + self.a * (z_best - self.z[i,]) + self.b * (self.z[p,] - self.z[q,])

                # mutated solution by the whole population
                idx = np.random.choice(self.D, AdaptiveNeighborhoodSize, replace=False)
                idx[idx == i] = idx[2]  # do not select itself, i.e., index i

                # r1 and r2 random indices in space [1, D] so that r1 ̸ = r2 ̸ = i and zbest the best
                # chromosome of the whole population of the previous generation
                r1 = idx[0]
                r2 = idx[1]

                bInd = self.PreviousBestFitness[idx].argmin()
                z_best = self.z[bInd]

                # gi = zi + α · (zbest − zi) + β · (zr1 − zr2), (4)
                g[i,] = self.z[i,] + self.a * (z_best - self.z[i,]) + self.b * (self.z[r1,] - self.z[r2,])

                #   yi = w · gi + (1 − w) · Li, (5)
                y[i,] = w * g[i,] + (1 - w) * L[i,]

                # Crossover using eq. (7) → new vector ui
                Cr = 0.8
                j_rand = randint(0, self.D)
                for c in range(0, self.nVars):
                    self.u[i, c] = y[i, c] if (random.randrange(0, 1) < Cr or k == j_rand) else self.z[i, c]

                    # Ensure (saturate) => u(i,j) ∈ [z(min,j) , z(max,j)]
                # check bounds violation
                posInvalid = self.u[i, :] < self.LowerBounds
                self.u[i, posInvalid] = self.LowerBounds[posInvalid]

                posInvalid = self.u[i, :] > self.UpperBounds
                self.u[i, posInvalid] = self.UpperBounds[posInvalid]

            # calculate fitness
            self.__evaluateDEu()
            # find chromosomes tha has been improved and replace the old values with the new
            genProgressed = self.CurrentGenFitness < self.PreviousBestFitness
            self.PreviousBestPosition[genProgressed, :] = self.u[genProgressed, :]
            self.z[genProgressed, :] = self.u[genProgressed, :]
            self.PreviousBestFitness[genProgressed] = self.CurrentGenFitness[genProgressed]

            # update global best, adaptive neighborhood size and stall counter
            newBestInd = self.CurrentGenFitness.argmin()
            newBestFit = self.CurrentGenFitness[newBestInd]

            if newBestFit < self.GlobalBestFitness:
                self.GlobalBestFitness = newBestFit
                self.GlobalBestPosition = self.z[newBestInd, :].copy()

                self.StallCounter = max(0, self.StallCounter - 1)
                # calculate remaining only once when fitness is improved to save some time
                # useful for the plots created
                [self.newOrder, self.remaining] = get_Data(self)
            else:
                self.StallCounter += 1

            # first element of self.GlobalBestSoFarFitnesses is for self.Iteration == -1
            self.GlobalBestSoFarFitnesses[self.Iteration + 1] = self.GlobalBestFitness

            # run output function and stop if necessary
            if self.OutputFcn and self.OutputFcn(self):
                self.StopReason = 'OutputFcn requested to stop.'
                doStop = True
                continue

            # stop if max iterations
            if self.Iteration >= self.MaxIterations - 1:
                self.StopReason = 'MaxIterations reached.'
                doStop = True
                continue

            # stop if insignificant improvement
            if self.Iteration > self.MaxStallIterations:
                # The minimum global best fitness is the one stored in self.GlobalBestSoFarFitnesses[self.Iteration+1]
                # (only updated if newBestFit is less than the previously stored). The maximum (may be equal to the 
                # current) is the one  in self.GlobalBestSoFarFitnesses MaxStallIterations before.
                minBestFitness = self.GlobalBestSoFarFitnesses[self.Iteration + 1]
                maxPastBestFit = self.GlobalBestSoFarFitnesses[self.Iteration + 1 - self.MaxStallIterations]
                if (maxPastBestFit == 0.0) and (minBestFitness < maxPastBestFit):
                    windowProgress = np.inf  # don't stop
                elif (maxPastBestFit == 0.0) and (minBestFitness == 0.0):
                    windowProgress = 0.0  # not progressed
                else:
                    windowProgress = abs(minBestFitness - maxPastBestFit) / abs(maxPastBestFit)
                if windowProgress <= self.FunctionTolerance:
                    self.StopReason = 'Population did not improve significantly the last MaxStallIterations.'
                    doStop = True

        # print stop message
        print('Algorithm stopped after {} iterations. Best fitness attained: {}'.format(
            self.Iteration + 1, self.GlobalBestFitness))
        print(f'Stop reason: {self.StopReason}')
