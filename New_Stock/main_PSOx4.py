from WoodProblemDefinitionX4 import Stock, Order1, Order2, Order3
import time, os
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import shapely
import shapely.ops
from descartes import PolygonPatch
from DynNeighborPSO import DynNeighborPSO
import sys
import math
import geopandas as gpd

# define weights of fitness function
w_f_OUT = 5000
w_f_OVERLAP = 5000
w_f_ATTR = 3
w_f_SMO = 1000
w_f_DIST = 5


# %% Simple helper class for getting matplotlib patches from shapely polygons with different face colors
class PlotPatchHelper:
    # a colormap with 41 colors
    CMapColors = np.array([
        [0, 0.447, 0.741, 1],
        [0.85, 0.325, 0.098, 1],
        [0.929, 0.694, 0.125, 1],
        [0.494, 0.184, 0.556, 1],
        [0.466, 0.674, 0.188, 1],
        [0.301, 0.745, 0.933, 1],
        [0.635, 0.078, 0.184, 1],
        [0.333333333, 0.333333333, 0, 1],
        [0.333333333, 0.666666667, 0, 1],
        [0.666666667, 0.333333333, 0, 1],
        [0.666666667, 0.666666667, 0, 1],
        [1, 0.333333333, 0, 1],
        [1, 0.666666667, 0, 1],
        [0, 0.333333333, 0.5, 1],
        [0, 0.666666667, 0.5, 1],
        [0, 1, 0.5, 1],
        [0.333333333, 0, 0.5, 1],
        [0.333333333, 0.333333333, 0.5, 1],
        [0.333333333, 0.666666667, 0.5, 1],
        [0.333333333, 1, 0.5, 1],
        [0.666666667, 0, 0.5, 1],
        [0.666666667, 0.333333333, 0.5, 1],
        [0.666666667, 0.666666667, 0.5, 1],
        [1, 0, 0.5, 1],
        [1, 0.333333333, 0.5, 1],
        [1, 0.666666667, 0.5, 1],
        [1, 1, 0.5, 1],
        [0, 0.333333333, 1, 1],
        [0, 0.666666667, 1, 1],
        [0, 1, 1, 1],
        [0.333333333, 0, 1, 1],
        [0.333333333, 0.333333333, 1, 1],
        [0.333333333, 0.666666667, 1, 1],
        [0.333333333, 1, 1, 1],
        [0.666666667, 0, 1, 1],
        [0.666666667, 0.333333333, 1, 1],
        [0.666666667, 0.666666667, 1, 1],
        [0.666666667, 1, 1, 1],
        [1, 0, 1, 1],
        [1, 0.333333333, 1, 1],
        [1, 0.666666667, 1, 1]
    ])

    # Alpha controls the opaqueness, Gamma how darker the edge line will be and LineWidth its weight
    def __init__(self, Gamma=1.3, Alpha=0.9, LineWidth=2.0):
        self.count = 0
        self.Gamma = Gamma  # darker edge color if Gamma>1 -> faceColor ** Gamma; use np.inf for black
        self.Alpha = Alpha  # opaqueness level (1-transparency)
        self.LineWidth = LineWidth  # edge weight

    # circles through the colormap and returns the FaceColor and the EdgeColor (as FaceColor^Gamma)
    def nextcolor(self):
        col = self.CMapColors[self.count, :].copy()
        self.count = (self.count + 1) % self.CMapColors.shape[0]
        return (col, col ** self.Gamma)

    # returns a list of matplotlib.patches.PathPatch from the provided shapely polygons, using descartes; a list is
    # returned even for a single polygon for common handling
    def get_patches(self, poly):
        if not isinstance(poly, list):  # single polygon, make it a one element list for common handling
            poly = [poly]
        patchList = []
        for p in poly:
            fCol, eCol = self.nextcolor()
            patchList.append(PolygonPatch(p, alpha=self.Alpha, fc=fCol, ec=eCol,
                                          lw=self.LineWidth))
        return patchList


def plot_shapes(stock):
    fig, ax = plt.subplots()
    fig.canvas.manager.set_window_title('Shifted Order1 pieces for better viewing')
    shifted = stock.copy()
    for i in range(1, len(shifted)):
        xshift = shifted[i - 1].bounds[2] + 0.5  # previous Xmax of bounding box (bounds property) plus 0.5 space
        shifted[i] = shapely.affinity.translate(shifted[i], xshift)
    plotShapelyPoly(ax, shifted)
    ax.relim()
    ax.autoscale_view()
    ax.set_aspect('equal')
    # plt.show()


# Plots one or more shapely polygons in the provided axes ax. The named parameter values **kwargs are passed into
# PlotPatchHelper's constructor, e.g. you can write plotShapelyPoly(ax, poly, LineWidth=3, Alpha=1.0). Returns a list
# with the drawn patches objects even for a single polygon, for common handling
def plotShapelyPoly(ax, poly, **kwargs):
    return [ax.add_patch(p) for p in PlotPatchHelper(**kwargs).get_patches(poly)]


# %% Fitness Function

def ObjectiveFcn(particle, nVars, Stock, Order):
    f = 0
    remaining = Stock

    newOrder = [shapely.affinity.rotate(shapely.affinity.translate(Order[j],
                                                                   xoff=particle[j * 3],
                                                                   yoff=particle[j * 3 + 1]),
                                        particle[j * 3 + 2],
                                        origin='centroid')
                for j in range(len(Order))]

    # This  fitness  component is used to prevent cutting of polygons outside the boundaries of each stock
    union = shapely.ops.cascaded_union(newOrder)  # the union of shapes with new positions and rotations
    f_OUT = union.difference(Stock)  # the difference of union with stock
    f_OUT = f_OUT.area

    # the goal is to avoid overlapping the polygons cut
    # calculate the area of ​​the shapes overlapped by many shapes
    areaSum = sum([newOrder[w].area for w in range(0, len(newOrder))])

    # the sum of the areas of the shapes of each order
    # Overlap area is the difference of the sum of the areas of the shapes of each order form
    # the UNION area of the individual shapes of the order with the placements of the proposed solution
    f_OVERLAP = areaSum - union.area  # if there is no overlap, the difference must be zero, and
    # if such a difference expresses the overlapping portion

    # Attraction of shapes to each other
    # The aim is to reduce the distances between the shapes in descending order by area
    sortedOrder = np.argsort(np.array([newOrder[i].area for i in range(0, len(newOrder))]))
    sortedM = [newOrder[w] for w in (-sortedOrder)]
    # This distance is the shortest and the final is the sum of all this distances
    f_DIST = sum([sortedM[i].distance(sortedM[i + 1]) for i in range(0, len(sortedM) - 1)])
    # f_DIST = sum([(sortedM[i].distance(sortedM[i + 1]) / sortedM[i].hausdorff_distance(sortedM[i + 1])) for i in range(0, len(sortedM) - 1)])

    # Attraction of shapes to the x and y axis(0,0) using areas
    # Calculte the sum of the x's and the centroid of the shapes multiplied by the area of ​​the figure
    f_ATTR_x = sum([newOrder[i].area * (newOrder[i].centroid.x) for i in range(0, len(newOrder))])
    # f_ATTR_x = sum([newOrder[i].area * (newOrder[i].centroid.x) for i in range(0, len(newOrder))]) / (Stock.area * Stock.centroid.x)

    # Calculte the sum of the y's and the centroid of the shapes multiplied by the area of ​​the figure
    f_ATTR_y = sum([newOrder[i].area * (newOrder[i].centroid.y) for i in range(0, len(newOrder))])
    # _ATTR_y = sum([newOrder[i].area * (newOrder[i].centroid.y) for i in range(0, len(newOrder))]) / (Stock.area * Stock.centroid.y)
    # term will be its summarise
    f_ATTR = f_ATTR_x + f_ATTR_y

    # This  fitness  component  quantifies the  smoothness  of the  object  by  evaluating  the  shape  of its external  borders.
    # Objects  with  strongly irregular  shape  are  penalized,
    # to  avoid  the  simultaneous extraction of spatially distant regions of the same label. Initially, we compute the following ratio
    remaining = Stock.difference(union)
    hull = remaining.convex_hull

    l = hull.area / remaining.area - 1  # Objects with small λare nearly convex (𝜆=0for ideally convex) which is considered as the ideal shape of an object.
    #l = (hull.area - remaining.area) / hull.area
    # f_SMO = np.arctan(l)
    a = 1.1
    f_SMO = 1 / (1 + a * l)
    # f_SMO = np.exp(l + 2) - 7
    # print(f"f_SM01: {1 / (1 + a * l)}")
    # print(f"f_SM02: {np.arctan(l)}")

    # Normalization
    # f_OUT = f_OUT / Stock.area
    # f_OVERLAP = f_OVERLAP / areaSum
    # The overall fitness function is obtained by combining the above criteria
    f = (f_OUT * w_f_OUT) + (f_OVERLAP * w_f_OVERLAP) + (f_DIST * w_f_DIST) + (f_ATTR * w_f_ATTR) + (f_SMO * w_f_SMO)
    # print('f_OUT', f_OUT)
    # print('f_OVERLAP', f_OVERLAP)
    # print('f_DIST', f_DIST)
    # print('f_ATTR', f_ATTR)
    # print('f_SMO', f_SMO)
    return f


# %% Class for storing and updating the figure's objects
class FigureObjects:
    """ Class for storing and updating the figure's objects.

        The initializer creates the figure given only the lower and upper bounds (scalars, since the bounds are
        typically equal in both dimensions).

        The update member function accepts a DynNeighborPSO object and updates all elements in the figure.

        The figure has a top row of 1 subplots. This shows the best-so-far global finess value .
        The bottom row shows the global best-so-far solution achieved by the algorithm and the remaining current stock after placement.
    """

    def __init__(self, LowerBound, UpperBound):
        """ Creates the figure that will be updated by the update member function.

        All line objects (best solution, swarm, global fitness line) are initialized with NaN values, as we only
        setup the style. Best-so-far fitness

        The input arguments LowerBound & UpperBound must be scalars, otherwise an assertion will fail.
        """

        # figure
        self.fig = plt.figure()
        self.ax = [1, 2, 3]
        self.ax[0] = plt.subplot(211)

        self.ax[0].set_title('Best-so-far global best fitness: {:g}'.format(np.nan))
        self.lineBestFit, = self.ax[0].plot([], [])

        # auto-arrange subplots to avoid overlappings and show the plot
        # 3 subplots : 1: fitness , 2: newOrder, 3: Remaining (for current fitness and positions)

        self.ax[1] = plt.subplot(223)
        self.ax[1].set_title('Rotated & translated order')
        self.ax[2] = plt.subplot(224)
        self.ax[2].set_title('Remaining after set difference')
        self.fig.tight_layout()

    def update(self, pso):
        """ Updates the figure in each iteration provided a PSODynNeighborPSO object. """
        # pso.Iteration is the PSO initialization; setup the best-so-far fitness line xdata and ydata, now that
        # we know MaxIterations

        if pso.Iteration == -1:
            xdata = np.arange(pso.MaxIterations + 1) - 1
            self.lineBestFit.set_xdata(xdata)
            self.lineBestFit.set_ydata(pso.GlobalBestSoFarFitnesses)

        # update the global best fitness line (remember, -1 is for initialization == iteration 0)
        self.lineBestFit.set_ydata(pso.GlobalBestSoFarFitnesses)
        self.ax[0].relim()
        self.ax[0].autoscale_view()
        self.ax[0].title.set_text('Best-so-far global best fitness: {:g}'.format(pso.GlobalBestFitness))

        # because of title and particles positions changing, we cannot update specific artists only (the figure
        # background needs updating); redrawing the whole figure canvas is expensive but we have to

        newOrder = pso.newOrder
        remaining = pso.remaining
        # NOTE: the above operation is perhaps faster if we perform a cascade union first as below, check it on your code:
        # remaining = Stock[6].difference(shapely.ops.cascaded_union(newOrder))
        # self.fig2, ax = plt.subplots(ncols=2)
        # self.fig2.canvas.set_window_title('Stock[6] cutting Order3 (translated & rotated)')
        self.ax[1].cla()
        self.ax[2].cla()
        self.ax[1].set_title('Rotated & translated order')
        self.ax[2].set_title('Remaining after set difference')
        pp = plotShapelyPoly(self.ax[1], [pso.Stock] + newOrder)
        pp[0].set_facecolor([1, 1, 1, 1])
        plotShapelyPoly(self.ax[2], remaining)
        self.ax[1].relim()
        self.ax[1].autoscale_view()
        self.ax[2].set_xlim(self.ax[1].get_xlim())
        self.ax[2].set_ylim(self.ax[1].get_ylim())
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()


def OutputFcn(pso, figObj):
    """ Our output function: updates the figure object and prints best fitness on terminal.

        Always returns False (== don't stop the iterative process)
    """
    if pso.Iteration == -1:
        print('Iter.    Global best')
    print('{0:5d}    {1:.5f}'.format(pso.Iteration, pso.GlobalBestFitness))

    figObj.update(pso)

    return False


# %% Main

def run_PSO():
    plot_shapes(Order1)
    plot_shapes(Order2)
    plot_shapes(Order3)
    plot_shapes(Stock)
    # in case someone tries to run it from the command-line...
    plt.ion()
    # np.random.seed(1)

    # Start calculating time in order to calculate converge time
    start_time = time.time()

    orders = [Order1, Order2, Order3]  # Store all orders into a list
    shapesTotal = sum([len(Order1), len(Order2), len(Order3)])  # get number of polygons

    resList = []
    resListPerStock = []
    nonFitted = []

    orderN = len(orders)
    # Copy Stock into remainning varaible
    remaining = Stock.copy()
    remainingN = len(remaining)
    count = 0
    shapesF = 0
    iterationsList = []
    # runs as long as the order list is not empty
    while (orders):
        # a flag indicating whether the order has been fulfilled
        flag = False
        count = count + 1
        tolerance = 1e-4

        # place the 1st order as current and starting calculations
        currentOrder = orders[0]

        # Calculate the sum of the areas of the order shapes
        currentOrderArea = sum([currentOrder[w].area for w in range(0, len(currentOrder))])

        # table with the size of the stock(remainings)
        remainingsArea = np.array([remaining[k].area for k in range(0, len(remaining))])

        # upper and lower bounds of variables ([x, y, theta]) based on current stock
        nVars = len(currentOrder) * 3  # for each part

        # a list of stocks that have a larger area than the order and the order of the smallest,
        # meaning that if the order eventually fits, it will leave less unused space in the stock for the larger
        shapeIdx = (np.where(remainingsArea > currentOrderArea))[0]
        # the stocks are sorted in ascending order by area
        indexes = np.argsort(remainingsArea[shapeIdx])
        shapeIdx = shapeIdx[indexes]
        # print("Shape Indexes\n")
        # print(shapeIdx)

        # this for scans the stocks shapeIdx list
        for stockIdx in shapeIdx:

            print("Current Stock Index=%d   and testing order num=%d" % (stockIdx, count))
            # Define PEAKS
            # set currentStock for pso the stocks-remainings from the local list
            currentStock = remaining[stockIdx]
            # Set lower and upper bounds for the 3 variables for each particle
            # as the bounds of stocks
            (minx, miny, maxx, maxy) = currentStock.bounds
            LowerBounds = np.ones(nVars)
            w1 = [b for b in range(0, nVars, 3)]
            w2 = [b for b in range(1, nVars, 3)]
            w3 = [b for b in range(2, nVars, 3)]

            LowerBounds[w1] = minx
            LowerBounds[w2] = miny
            LowerBounds[w3] = 0

            UpperBounds = np.ones(nVars)
            UpperBounds[w1] = maxx
            UpperBounds[w2] = maxy
            UpperBounds[w3] = 360

            figObj = FigureObjects(minx, maxx)
            outFun = lambda x: OutputFcn(x, figObj)

            pso = DynNeighborPSO(ObjectiveFcn, nVars, LowerBounds=LowerBounds, UpperBounds=UpperBounds,
                                 OutputFcn=outFun, UseParallel=False, MaxStallIterations=15,
                                 SelfAdjustmentWeight=1.49, SocialAdjustmentWeight=1.49,
                                 Stock=currentStock, Order=currentOrder, remaining=currentStock, newOrder=currentOrder)

            while True:
                try:
                    pso.optimize()
                    break
                except:
                    print("\nAn unexcpected error occured. Program will terminate.\nPlease try running again...")
                    time.sleep(2)
                    sys.exit()

            # the possible locations of the order shapes
            # the implementation of the transformations results in the ordering of new positions
            pos = pso.GlobalBestPosition
            newOrder = [shapely.affinity.rotate(
                shapely.affinity.translate(currentOrder[k], xoff=pos[k * 3], yoff=pos[k * 3 + 1]),  # ring pattern
                pos[k * 3 + 2], origin='centroid') for k in range(len(currentOrder))]
            iterationsList.append(pso.Iteration)

            # first check if the order is in stock.
            union = shapely.ops.cascaded_union(newOrder)

            myPolugo = gpd.GeoSeries(union)
            myPolugo.plot()
            # plt.show()

            # take newOrder out of stock - inverse of remaining
            difunion = union.difference(currentStock)
            # if this area is larger than the tolerance
            # then the current solution is not acceptable and the resume continues for the same order as the next stock in the list
            if difunion.area > tolerance:
                continue

            # secondly check if there is an overlap and skip
            # overlap area is equal with sumOfArea - areaOfUnion
            areaSum = sum([newOrder[w].area for w in range(0, len(newOrder))])
            # the difference of the area (sum of areas) of the shapes of the order minus the area of ​​the union of the shapes of the order
            difArea = areaSum - union.area
            # if this area is larger than the tolerance
            # then the current solution is not acceptable and the resume continues for the same order as the next stock in the list
            if difArea > tolerance:
                continue

            # if both of the two conditions are fullfilled (if the order is in stock and not overalaping)
            flag = True
            for p in newOrder:
                # parts of the order are removed from stock
                remaining[stockIdx] = remaining[stockIdx].difference(p)
            # plot_shapes(newOrder)
            # plot_shapes(remaining)

            #plt.show()
            break

        # if the order has not fit (in any of the possible stocks)
        if not flag:
            objectArea = ([currentOrder[w].area for w in range(0, len(currentOrder))])
            objectArea, currentOrder = (list(t) for t in zip(*sorted(zip(objectArea, currentOrder))))
            if currentOrder:
                temp1 = (currentOrder[0:int((len(currentOrder) / 2))])
                temp2 = (currentOrder[int((len(currentOrder) / 2)):len(currentOrder)])
                orders = [temp1] + [temp2] + orders[1:]
            else:
                # If the placements are not correct then an order with a shape may not fit
                # then it is placed in a list of non-matching shapes and is removed from the orders
                # Them continue to next order
                # cases where stocks are not sufficient for an order so they must be reinforced with new stocks
                nonFitted.append(orders[0])
                orders.remove(currentOrder)
        # If we have a positive result and is placed correctly this current order will be stored
        # in a list of the positions that gave the correct result for each shape as well as in which stock
        else:
            # if polygons of current order is flag,
            # then increase the number of flag polygons, ,
            # append the stockIdx and remove the flag order
            shapesF = shapesF + len(currentOrder)
            resList.append(newOrder)  # append the parts of order in resList
            resListPerStock.append(stockIdx)
            orders.remove(currentOrder)
            print("Current order: %d fitted in stock num=%d " % (count, stockIdx))

    print("\n\n =================== RESULTS ===================\n\n")
    print("\n---- Time taken: %s seconds ----" % (time.time() - start_time))
    # The overall fitness function is obtained by combining the above criteria
    #    f = f_OUT.area*w_f_OUT + f_OVERLAP*w_f_OVERLAP  +f_ATTR*w_f_ATTR + f_SMO*w_f_SMO

    print(
        'w_f_OUT:{:0.2f}, w_f_OVERLAP={:0.2f}, w_f_ATTR={:0.6f}, w_f_SMO={:0.2f}'.format(w_f_OUT, w_f_OVERLAP, w_f_ATTR,
                                                                                         w_f_SMO))

    print("\nPolygons fitted=%d out of %d." % (shapesF, shapesTotal))
    print("\nNumber of Iterations (avg) = (%f)" % (np.mean(iterationsList)))

    print("\n")

    # =================== STORE RESULTS OF EXPERIMENTS ==========================
    import os
    MYDIR = ("results_PSOx4")
    CHECK_FOLDER = os.path.isdir(MYDIR)

    # If folder doesn't exist, then create it.
    if not CHECK_FOLDER:
        os.makedirs(MYDIR)
        print("created folder : ", MYDIR)

    # Write Results on file and append on each execution
    fname = "results_PSOx4/results_PSO.csv"
    f = open(fname, "a+")
    # datetime object containing current date and time
    now = datetime.now()

    # dd/mm/YY H:M:S
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    f.write("Experiment on:" + dt_string)
    f.write("\n")
    f.write("\nWeights of fitness function criteria:\n")
    f.write('w_f_OUT:{:0.2f}, w_f_OVERLAP={:0.2f}, w_f_ATTR={:0.6f}, w_f_SMO={:0.2f}, w_f_DIST={:0.2f}'.format(w_f_OUT,
                                                                                                               w_f_OVERLAP,
                                                                                                               w_f_ATTR,
                                                                                                               w_f_SMO,
                                                                                                               w_f_DIST))
    f.write("\n")
    f.write(f"Analysis Duration: {time.time() - start_time} \n")
    f.write(f"Fitted {shapesF} out of {shapesTotal} Polygons. \n")
    f.write(f"\nNumber of Iterations (avg): {np.mean(iterationsList)}")
    f.write("\n=========================================================")
    f.write("\n\n")
    f.close()
    print(f"Results will be stored in: {fname}")

    # Plot remainings
    idx = 0
    # plt_label = 'w_f_OUT:{:0.2f}, w_f_OVERLAP={:0.2f}, w_f_ATTR={:0.6f}, w_f_SMO={:0.2f}'.format(w_f_OUT, w_f_OVERLAP, w_f_ATTR, w_f_SMO)

    fig, ax = plt.subplots(ncols=4, nrows=7, figsize=(16, 9))
    #  plt.title(plt_label)
    fig.canvas.set_window_title('Polygons flag=%d from %d polygons' % (shapesF, shapesTotal))
    for i in range(0, len(Stock)):
        if i >= 24:
            idx = 1
        elif i>=20:
            idx = 2
        elif i>=16:
            idx = 3
        elif i>=12:
            idx = 4
        elif i>=8:
            idx = 5
        elif i>=4:
            idx = 6
        else:
            idx = 0

        plotShapelyPoly(ax[idx][i % 4], remaining[i])
        ax[idx][i % 4].set_title('Stock[%d]' % i)
        (minx, miny, maxx, maxy) = Stock[i].bounds
        ax[idx][i % 4].set_ylim(bottom=miny, top=maxy)
        ax[idx][i % 4].set_xlim(left=minx, right=maxx)

    # Save figure with remainings
    import os

    name = "results_PSOx4/result_PSO.png"
    if os.path.isfile(name):
        expand = 1
        while True:
            expand += 1
            new_file_name = name.split(".png")[0] + "(" + str(expand) + ")" + ".png"
            if os.path.isfile(new_file_name):
                continue
            else:
                name = new_file_name
                break
    print("This image will be saved as:" + name)
    fig.tight_layout()
    fig.savefig(name)


if __name__ == '__main__':
    for i in range(3):
        run_PSO()
