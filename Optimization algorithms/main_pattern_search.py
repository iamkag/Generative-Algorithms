from pip import main
from WoodProblemDefinition import Stock, Order1, Order2, Order3
import time
import os 
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import shapely
import shapely.ops
from descartes import PolygonPatch
from noisyopt import minimizeCompass
import sys

#weights of fitness function
w_f_OUT = 500
w_f_OVERLAP = 500
w_f_ATTR = 0.01
w_f_SMO = 500
w_f_DIST = 1.0

# %% Simple helper class for getting matplotlib patches from shapely polygons with different face colors 
class PlotPatchHelper:
    # a colormap with 41 colors
    CMapColors = np.array([
            [0,0.447,0.741,1],
            [0.85,0.325,0.098,1],
            [0.929,0.694,0.125,1],
            [0.494,0.184,0.556,1],
            [0.466,0.674,0.188,1],
            [0.301,0.745,0.933,1],
            [0.635,0.078,0.184,1],
            [0.333333333,0.333333333,0,1],
            [0.333333333,0.666666667,0,1],
            [0.666666667,0.333333333,0,1],
            [0.666666667,0.666666667,0,1],
            [1,0.333333333,0,1],
            [1,0.666666667,0,1],
            [0,0.333333333,0.5,1],
            [0,0.666666667,0.5,1],
            [0,1,0.5,1],
            [0.333333333,0,0.5,1],
            [0.333333333,0.333333333,0.5,1],
            [0.333333333,0.666666667,0.5,1],
            [0.333333333,1,0.5,1],
            [0.666666667,0,0.5,1],
            [0.666666667,0.333333333,0.5,1],
            [0.666666667,0.666666667,0.5,1],
            [1,0,0.5,1],
            [1,0.333333333,0.5,1],
            [1,0.666666667,0.5,1],
            [1,1,0.5,1],
            [0,0.333333333,1,1],
            [0,0.666666667,1,1],
            [0,1,1,1],
            [0.333333333,0,1,1],
            [0.333333333,0.333333333,1,1],
            [0.333333333,0.666666667,1,1],
            [0.333333333,1,1,1],
            [0.666666667,0,1,1],
            [0.666666667,0.333333333,1,1],
            [0.666666667,0.666666667,1,1],
            [0.666666667,1,1,1],
            [1,0,1,1],
            [1,0.333333333,1,1],
            [1,0.666666667,1,1]
            ])
    
    
    # Alpha controls the opaqueness, Gamma how darker the edge line will be and LineWidth its weight
    def __init__(self, Gamma=1.3, Alpha=0.9, LineWidth=2.0):
        self.count = 0
        self.Gamma = Gamma          # darker edge color if Gamma>1 -> faceColor ** Gamma; use np.inf for black
        self.Alpha = Alpha          # opaqueness level (1-transparency)
        self.LineWidth = LineWidth  # edge weight
    
    # circles through the colormap and returns the FaceColor and the EdgeColor (as FaceColor^Gamma)
    def nextcolor(self):
        col = self.CMapColors[self.count,:].copy()
        self.count = (self.count+1) % self.CMapColors.shape[0]
        return (col, col**self.Gamma)
    
    # returns a list of matplotlib.patches.PathPatch from the provided shapely polygons, using descartes; a list is 
    # returned even for a single polygon for common handling
    def get_patches(self, poly):
        if not isinstance(poly, list): # single polygon, make it a one element list for common handling
            poly = [poly]
        patchList = []
        for p in poly:
            fCol, eCol = self.nextcolor()
            patchList.append(PolygonPatch(p, alpha=self.Alpha, fc=fCol, ec=eCol, 
                                          lw=self.LineWidth))
        return patchList


# Plots one or more shapely polygons in the provided axes ax. The named parameter values **kwargs are passed into
# PlotPatchHelper's constructor, e.g. you can write plotShapelyPoly(ax, poly, LineWidth=3, Alpha=1.0). Returns a list
# with the drawn patches objects even for a single polygon, for common handling
def plotShapelyPoly(ax, poly, **kwargs):
    return [ax.add_patch(p) for p in PlotPatchHelper(**kwargs).get_patches(poly)]

# %% Fitness Function 

def ObjectiveFcn(particle,nVars,Stock,Order):

    f=0
    remaining = Stock  
    
    newOrder = [ shapely.affinity.rotate(shapely.affinity.translate(Order[j], 
                                                                    xoff=particle[j*3], 
                                                                    yoff=particle[j*3+1]),
                                                                    particle[j*3+2], 
                                                                    origin='centroid')
                                                                    for j in range(len(Order))]
    
   
    # This  fitness  component is used to prevent cutting of polygons outside the boundaries of each stock
    union=shapely.ops.cascaded_union(newOrder) # the union of shapes with new positions and rotations
    f_OUT=union.difference(Stock) # the difference of union with stock
    f_OUT = f_OUT.area
    
    # the goal is to avoid overlapping the polygons cut
    # calculate the area of ​​the shapes overlapped by many shapes
    areaSum = sum([newOrder[w].area for w in range(0,len(newOrder))])

    #the sum of the areas of the shapes of each order
    # Overlap area is the difference of the sum of the areas of the shapes of each order form
    # the UNION area of the individual shapes of the order with the placements of the proposed solution
    f_OVERLAP = areaSum-union.area # if there is no overlap, the difference must be zero, and
                                             #if such a difference expresses the overlapping portion
        
    
    
    
    # Attraction of shapes to each other
    # The aim is to reduce the distances between the shapes in descending order by area
    sortedOrder = np.argsort(np.array([newOrder[i].area for i in range(0, len(newOrder))]))
    sortedM = [newOrder[w] for w in sortedOrder]
    #This distance is the shortest and the final is the sum of all this distances
    f_DIST = sum([sortedM[i].distance(sortedM[i + 1]) for i in range(0, len(sortedM) -1)]) 
                             
                                             
    # Attraction of shapes to the x and y axis(0,0) using areas
    # Calculte the sum of the x's and the centroid of the shapes multiplied by the area of ​​the figure
    f_ATTR_x = sum([newOrder[i].area*(newOrder[i].centroid.x) for i in range(0,len(newOrder))])
    # Calculte the sum of the y's and the centroid of the shapes multiplied by the area of ​​the figure
    f_ATTR_y = sum([newOrder[i].area*(newOrder[i].centroid.y) for i in range(0,len(newOrder))])
    # term will be its summarise
    f_ATTR = f_ATTR_x + f_ATTR_y


    # This  fitness  component  quantifies the  smoothness  of the  object  by  evaluating  the  shape  of its external  borders.  
    # Objects  with  strongly irregular  shape  are  penalized, 
    # to  avoid  the  simultaneous extraction of spatially distant regions of the same label. Initially, we compute the following ratio
    remaining = Stock.difference(union)
    hull = remaining.convex_hull 
    l = hull.area/remaining.area-1 # Objects with small λare nearly convex (𝜆=0for ideally convex) which is considered as the ideal shape of an object.
    # Parameter αcontrols the slope of the function.
    a = 1.11
    # To obtain normalized fitness values in the range [0,1], the smoothness fitness is defined as follows
    f_SMO = 1/(1+a*l)
    
    
    # The overall fitness function is obtained by combining the above criteria
    f = (f_OUT*w_f_OUT) + (f_OVERLAP*w_f_OVERLAP) + (f_DIST*w_f_DIST) + (f_ATTR*w_f_ATTR) + (f_SMO*w_f_SMO)
   # print(f)
    return f
# %% This wrapper created as helper around the objective function and using the callback function. 
# No additional function evaluations are performed here, so this should be an efficient way
# Eventually I found another way to get the data of the results and i didnt use it
class Simulator:
    def __init__(self, function):
        self.f = function # actual objective function
        self.num_calls = 0 # how many times f has been called
        self.callback_count = 0 # number of times callback has been called, also measures iteration count
        self.list_calls_inp = [] # input of all calls
        self.list_calls_res = [] # result of all calls
        self.decreasing_list_calls_inp = [] # input of calls that resulted in decrease
        self.decreasing_list_calls_res = [] # result of calls that resulted in decrease
        self.list_callback_inp = [] # only appends inputs on callback, as such they correspond to the iterations
        self.list_callback_res = [] # only appends results on callback, as such they correspond to the iterations
    
    def simulate(self, x):
        """Executes the actual simulation and returns the result, while
        updating the lists too. Pass to optimizer without arguments or
        parentheses."""
        result = self.f(x) # the actual evaluation of the function
        if not self.num_calls: # first call is stored in all lists
            self.decreasing_list_calls_inp.append(x)
            self.decreasing_list_calls_res.append(result)
            self.list_callback_inp.append(x)
            self.list_callback_res.append(result)
        elif result < self.decreasing_list_calls_res[-1]:
            self.decreasing_list_calls_inp.append(x)
            self.decreasing_list_calls_res.append(result)
        self.list_calls_inp.append(x)
        self.list_calls_res.append(result)
        self.num_calls += 1
        return result
    
    def callback(self, xk, *_):
        """Callback function that can be used by optimizers of scipy.optimize.
        The third argument "*_" makes sure that it still works when the
        optimizer calls the callback function with more than one argument. Pass
        to optimizer without arguments or parentheses."""
        s1 = ""
        xk = np.atleast_1d(xk)
        # search backwards in input list for input corresponding to xk
        for i, x in reversed(list(enumerate(self.list_calls_inp))):
            x = np.atleast_1d(x)
            if np.allclose(x, xk):
                break
    
        for comp in xk:
            s1 += f"{comp:10.5e}\t"
        s1 += f"{self.list_calls_res[i]:10.5e}"
    
        self.list_callback_inp.append(xk)
        self.list_callback_res.append(self.list_calls_res[i])
    
        if not self.callback_count:
            s0 = ""
            for j, _ in enumerate(xk):
                tmp = f"Comp-{j+1}"
                s0 += f"{tmp:10s}\t"
            s0 += "Objective"
            print(s0)
        print(s1)
        self.callback_count += 1

def run_pattern_search():
    # in case someone tries to run it from the command-line...
    plt.ion()
    #np.random.seed(1)
    
    #Start calculating time in order to calculate converge time
    start_time = time.time()
    
    orders = [Order1, Order2, Order3] #Store all orders into a list
    shapesTotal=sum([len(Order1), len(Order2), len(Order3)]) #get number of polygons
    
    resList=[] 
    resListPerStock=[]
    nonFitted=[]
    iterationsList=[]
    orderN = len(orders)
    # Copy Stock into remainning varaible
    remaining = Stock.copy() 
    remainingN= len(remaining)
    count=0
    shapesF=0


    #runs as long as the order list is not empty
    while (orders):
        # a flag indicating whether the order has been fulfilled
        flag = False
        count=count+1
        tolerance = 1e-4
        
        # place the 1st order as current and starting calculations
        currentOrder = orders[0]
        
        #Calculate the sum of the areas of the order shapes
        currentOrderArea= sum([currentOrder[w].area for w in range(0,len(currentOrder))]) 
        
        #table with the size of the stock(remainings)
        remainingsArea = np.array([remaining[k].area for k in range(0,len(remaining))]) 
        
        # upper and lower bounds of variables ([x, y, theta]) based on current stock
        nVars = len(currentOrder) * 3 # for each part 
       
        # a list of stocks that have a larger area than the order and the order of the smallest,
        # meaning that if the order eventually fits, it will leave less unused space in the stock for the larger
        shapeIdx=(np.where(remainingsArea>currentOrderArea))[0]
        #the stocks are sorted in ascending order by area
        indexes = np.argsort(remainingsArea[shapeIdx])
        shapeIdx=shapeIdx[indexes]
       # print("Shape Indexes\n")
       # print(shapeIdx)
       
        # this for scans the stocks shapeIdx list
        for stockIdx in shapeIdx:
            print("Current Stock Index=%d   and testing order num=%d"% (stockIdx, count))
            #Define PEAKS
            # set currentStock for pso the stocks-remainings from the local list
            currentStock = remaining[stockIdx]
            # Set lower and upper bounds for the 3 variables for each particle
            # as the bounds of stocks
            (minx, miny, maxx, maxy) = currentStock.bounds
            LowerBounds = np.ones(nVars)
            w1= [b for b in range(0,nVars,3)]
            w2= [b for b in range(1,nVars,3)]
            w3= [b for b in range(2,nVars,3)]
           
            LowerBounds[w1]= minx 
            LowerBounds[w2]= miny
            LowerBounds[w3]= 0
            
            UpperBounds = np.ones(nVars)
            UpperBounds[w1] = maxx
            UpperBounds[w2] = maxy
            UpperBounds[w3] = 360

            

  
    	    # Initial swarm: randomly in [lower,upper] and if any is +-Inf in [-1000, 1000]
            lbMatrix = LowerBounds
            ubMatrix = UpperBounds
            bRangeMatrix = ubMatrix - lbMatrix
            x0= lbMatrix + np.random.rand(1,nVars) * bRangeMatrix

            res = None
            while res is None:
                try:
                    # connect
                   res = minimizeCompass(ObjectiveFcn, x0=x0[0], deltatol=0.1, paired=False,args=[nVars,currentStock,currentOrder],errorcontrol=False)
                except:
                    print("\nAn unexcpected error occured. Program will terminate.\nPlease try running again...")
                    time.sleep(2)
                    sys.exit()
            
#            print(f"Number of calls to Simulator instance {obj_sim.num_calls}")

            
            pos = res.x
            iterationsList.append(res.nit)
            
            # the possible locations of the order shapes
            # the implementation of the transformations results in the ordering of new positions
            newOrder = [ shapely.affinity.rotate( 
                    shapely.affinity.translate(currentOrder[k], xoff=pos[k*3], yoff=pos[k*3+1]), #ring pattern
                    pos[k*3+2], origin='centroid') for k in range(len(currentOrder))]
           
            
            # first check if the order is in stock.
            union=shapely.ops.cascaded_union(newOrder)
            # take newOrder out of stock - inverse of remaining
            difunion=union.difference(currentStock) 
            # if this area is larger than the tolerance 
            # then the current solution is not acceptable and the resume continues for the same order as the next stock in the list  
            if difunion.area >tolerance:
                continue
            
            # secondly check if there is an overlap and skip
            # overlap area is equal with sumOfArea - areaOfUnion
            areaSum = sum([newOrder[w].area for w in range(0,len(newOrder))])
            #the difference of the area (sum of areas) of the shapes of the order minus the area of ​​the union of the shapes of the order
            difArea = areaSum-union.area
            # if this area is larger than the tolerance 
            #then the current solution is not acceptable and the resume continues for the same order as the next stock in the list    
            if difArea > tolerance:
                continue
            

            # if both of the two conditions are fullfilled (if the order is in stock and not overalaping)
            flag=True
            for p in newOrder:
                #parts of the order are removed from stock
                remaining[stockIdx] = remaining[stockIdx].difference(p)
            break
        
        
        # if the order has not fit (in any of the possible stocks)
        if not flag:
            if(int((len(currentOrder)/2))!=0):
                temp1=(currentOrder[0:int((len(currentOrder)/2))])
                temp2=(currentOrder[int((len(currentOrder)/2)):len(currentOrder)])
                orders = [temp1]+[temp2] + orders[1:]
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
            shapesF=shapesF+len(currentOrder)
            resList.append( newOrder) #append the parts of order in resList
            resListPerStock.append(stockIdx)
            orders.remove(currentOrder)
            print("Current order: %d fitted in stock num=%d "% (count,stockIdx))

    print("\n\n =================== RESULTS ===================\n\n")
    print("\n---- Time taken: %s seconds ----" % (time.time() - start_time))
    print("\nNumber of Iterations (avg) = (%f)"%(np.mean(iterationsList))) 
    
   # print('w_f_OUT:{:0.2f}, w_f_OVERLAP={:0.2f}, w_f_ATTR={:0.6f}, w_f_SMO={:0.2f}'.format(w_f_OUT, w_f_OVERLAP, w_f_ATTR, w_f_SMO))
    
    print("\nPolygons fitted=%d out of %d."%(shapesF,shapesTotal))
    print("\n")

    
    #=================== STORE RESULTS OF EXPERIMENTS ==========================
    
    MYDIR = ("results_pattern_search")
    CHECK_FOLDER = os.path.isdir(MYDIR)
    
    # If folder doesn't exist, then create it.
    if not CHECK_FOLDER:
        os.makedirs(MYDIR)
        print("created folder : ", MYDIR)
    

    #Write Results on file and append on each execution
    fname = "results_pattern_search/results_pattern_search.csv"
    f= open(fname,"a+")
    # datetime object containing current date and time
    now = datetime.now()    
    # dd/mm/YY H:M:S
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    f.write("Experiment on:" + dt_string)
    f.write("\n")
    f.write("\n Weights of fitness function criteria:\n")
    f.write('w_f_OUT:{:0.2f}, w_f_OVERLAP={:0.2f}, w_f_ATTR={:0.6f}, w_f_SMO={:0.2f}, w_f_DIST={:0.2f}'.format(w_f_OUT,
                                                                                                               w_f_OVERLAP,
                                                                                                               w_f_ATTR,
                                                                                                               w_f_SMO,
                                                                                                               w_f_DIST))
    f.write("\n")
    f.write(f"Analysis Duration: {time.time() - start_time} \n")
    f.write(f"Fitted {shapesF} out of {shapesTotal} Polygons. \n")
    f.write(f"\nNumber of Iterations (avg): {np.mean(iterationsList)}")
    f.write("\n========================================================")
    f.write("\n\n")
    f.close()
    print("Results will be stored in:" +fname)  
    

    # Plot remainings
    idx=0 
    fig, ax = plt.subplots(ncols=4,nrows=2, figsize=(16,9))
    fig.canvas.set_window_title('Remainings- Polygons fitted=%d from %d polygons'%(shapesF,shapesTotal))
    for i in range(0,len(Stock)):
        if i>=4:
            idx=1
        
        plotShapelyPoly(ax[idx][i%4], remaining[i])
        ax[idx][i%4].set_title('Remaining of Stock[%d]'%i)
        (minx, miny, maxx, maxy) = Stock[i].bounds
        ax[idx][i%4].set_ylim(bottom=miny,top=maxy)
        ax[idx][i%4].set_xlim(left=minx ,right=maxx)

    #Save figure with remainings
    name = "results_pattern_search/result_pattern_search.png"

    if os.path.isfile(name):
        expand = 1
        while True:
            expand += 1
            new_file_name = name.split(".png")[0] + "(" +str(expand) + ")" + ".png"
            if os.path.isfile(new_file_name):
                continue
            else:
                name = new_file_name
                break
    print("This image will be saved as:" +name)
    fig.savefig(name)

if __name__ == '__main__':
    for i in range(5):
        run_pattern_search()