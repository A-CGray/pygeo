'''
# =============================================================================
DVConstraints provides a convient way of defining geometric
constrints for WINGS. This can be very convient for a constrained
aerodynamic or aerostructural optimization. Three types of
constraints are supported:

1. Thickness "tooth-pick" constraints: Thickness constraints are
enforced at specific locations. A relative or absolute
minumum/maximum thickness can be specified. Two variants are
supplied a '2d' variant for thickness constraints over an area such
as a spar box and a '1d' variant for thickness constraints along a
line 

2. Volume constraint: This computes and enforces a volume constraint
over the specified domain. The input is identical to the '2d'
thickness constraints.

3. LE/TE Constraints: These geometric constraints are required when
using FFD volumes with shape variables. The leading and trailing
edges must be fixed wrt the shape variabes so these enforce that the
coefficients on the leading edge can only move in equal and opposite
directions

Analytic sensitivity information is computed for all functions and a
facility for adding the constrints automatically to a pyOpt
optimization problem is also provided.
# =============================================================================
'''
import sys, time
import numpy
from mdo_import_helper import import_modules, mpiPrint
exec(import_modules('geo_utils', 'pySpline'))

class DVConstraints(object):

    def __init__(self):

        '''Create a (empty) DVconstrains object. Specific types of
        constraints will added individually'''
        self.nThickCon = 0
        self.thickConPtr = []
        self.thickConLower = []
        self.thickConUpper = []
        self.D0 = []
        self.thickScaled = []

        self.nVolumeCon = 0
        self.volumeConPtr = []
        self.volumeConLower = []
        self.volumeConUpper = []
        self.volumeConSizes = []
        self.V0 = []
        self.volumeScaled = []

        self.LeTeCon = []
        self.coords = numpy.zeros([0, 3], dtype='d')

        return

    def addThicknessConstraints2D(self, wing, le_list, te_list, nSpan, nChord,
                                lower=1.0, upper=3.0, scaled=True):

        '''
        Inputs:

        wing: a pyGeo object representing the wing

        le_list: A list defining the "leading edge" or start of the domain

        te_list: A list defining the "trailing edge" or end of the domain

        nChord: The number values in the chord-wise direction (between le_list and te_list)

        nSpan: The number of span-wise thickness constraints
     
        Lower: The low range for the thickness constraint
        
        Upper: The upper bound for the thickness constraint
        
        Scaled: True if constraint value is to be scaled by inital
        thickness. Scale=True and lower=1.0 will constraint to
        original thickness. If an absolute thickness is required, set
        lower to desired value and sclae=False.
        '''

        self.thickConPtr.append([len(self.coords),
                                 len(self.coords)+ nSpan*nChord*2])

        # Expand out lower and upper to make them the correct size
        temp = numpy.atleast_2d(lower)
        if temp.shape[0] == nSpan and value.shape[1] == nChord:
            lower = temp
        else:
            lower = lower*numpy.ones((nSpan, nChord))
        # end if
                        
        temp = numpy.atleast_2d(upper)
        if temp.shape[0] == nSpan and value.shape[1] == nChord:
            upper = temp
        else:
            upper = upper*numpy.ones((nSpan, nChord))
        # end if

        # Create mesh of itersections

        root_line = [le_list[0], te_list[0]]
        tip_line  = [le_list[-1], te_list[-1]]
        le_s = pySpline.curve(X=le_list, k=2)
        te_s = pySpline.curve(X=te_list, k=2)
        root_s = pySpline.curve(X=[le_list[0], te_list[0]], k=2)
        tip_s  = pySpline.curve(X=[le_list[-1], te_list[-1]], k=2)

        span_s = numpy.linspace(0, 1, nSpan)
        chord_s = numpy.linspace(0, 1, nChord)
        
        # Generate a 2D region of intersections
        X = geo_utils.tfi_2d(le_s(span_s), te_s(span_s),
                             root_s(chord_s), tip_s(chord_s))

        # Generate discrete surface data for intersections:
        p0,v1,v2 = self._generateDiscreteSurface(wing)

        # Append the new coordinates to self.coords
        coord_offset = len(self.coords)
        D0_offset    = len(self.D0)

        self.coords = numpy.append(self.coords, numpy.zeros(
                    (nSpan*nChord*2, 3)),axis=0)
        #self.D0     = numpy.append(self.D0    , numpy.zeros(
        #            (nSpan*nChord    )), axis=0)
        self.D0.extend(numpy.zeros(nSpan*nChord))

        # Generate all intersections:
        for i in xrange(nSpan): 
            for j in xrange(nChord):
                # Generate the 'up_vec' from taking the cross product
                # across a quad
                if i == 0:
                    u_vec = X[i+1, j]-X[i, j]
                elif i == nSpan - 1:
                    u_vec = X[i, j] - X[i-1, j]
                else:
                    u_vec = X[i+1, j] - X[i-1, j]
                # end if

                if j == 0:
                    v_vec = X[i, j+1]-X[i, j]
                elif j == nChord - 1:
                    v_vec = X[i, j] - X[i, j-1]
                else:
                    v_vec = X[i, j+1] - X[i, j-1]
                # end if

                up_vec = numpy.cross(u_vec, v_vec)
                
                # Project actual node:
                up, down, fail = geo_utils.projectNode(
                    X[i,j], up_vec, p0, v1, v2)

                if fail:
                    print 'DVConstraints: Project Node failed. Cannot continue'
                    sys.exit(0)
                # end if

                self.coords[coord_offset, :] = up
                coord_offset += 1

                self.coords[coord_offset, :] = down
                coord_offset += 1

                # Determine the distance between points
                self.D0[D0_offset] = geo_utils.e_dist(up, down)

                # The constraint will ALWAYS be set as a scaled value,
                # however, it is possible that the user has specified
                # individal values for each location. Therefore we
                # will convert these absolute values to an equilivant
                # scaled value. 
                
                if not scaled:
                    lower[i, j] /= self.D0[D0_offset]
                    upper[i, j] /= self.D0[D0_offset]
                #end
                D0_offset += 1
            # end for
        # end for
        
        # Finally add the thickness constraint values
        self.thickConLower.extend(lower.flatten())
        self.thickConUpper.extend(upper.flatten())
        self.nThickCon += 1
        self.thickScaled.append(scaled)

        return


    def addThicknessConstraints1D(self, wing, pt_list, nCon, axis, 
                                lower=1.0, upper=3.0, scaled=True):

        '''
        Inputs:

        wing: a pyGeo object representing the wing

        pt_list: A list defining the poly line where constraint is to
        be applied

        nCon: Number of constraints along edge
     
        axis: The axis along which to project the thickness
        constraint. Array or list of length 3

        Lower: The low range for the thickness constraint
        
        Upper: The upper bound for the thickness constraint

        Scaled: True if constraint value is to be scaled by inital
        thickness. Scale=True and lower=1.0 will constraint to
        original thickness. If an absolute thickness is required, set
        lower to desired value and sclae=False.

        '''

        self.thickConPtr.append([len(self.coords),len(self.coords) + nCon*2])

        # Expand out lower and upper to make them the correct size
        temp = numpy.atleast_1d(lower)
        if temp.shape[0] == nCon:
            lower = temp
        else:
            lower = lower*numpy.ones(nCon)
        # end if
                        
        temp = numpy.atleast_1d(upper)
        if temp.shape[0] == nCon:
            upper = temp
        else:
            upper = upper*numpy.ones(nCon)
        # end if

        # Create mesh of itersections
        constr_line = pySpline.curve(X=pt_list,k=2)
        s = numpy.linspace(0,1,nCon)
        X = constr_line(s)

        # Generate discrete surface data for intersections:
        p0,v1,v2 = self._generateDiscreteSurface(wing)

        # Append the new coordinates to self.coords
        coord_offset = len(self.coords)
        D0_offset    = len(self.D0)
        self.coords = numpy.append(self.coords, numpy.zeros((nCon*2, 3)),
                                   axis=0)
        #self.D0     = numpy.append(self.D0, numpy.zeros(nCon),axis=0)
        self.D0.extend(numpy.zeros(nCon))

        # Generate all intersections:
        for i in xrange(nCon):
            up_vec = axis

            # Project actual node:
            up, down, fail = geo_utils.projectNode(
                X[i], up_vec, p0, v1, v2)

            if fail:
                print 'DVConstraints: Project Node failed. Cannot continue'
                sys.exit(0)
            # end if

            self.coords[coord_offset, :] = up
            coord_offset += 1

            self.coords[coord_offset, :] = down
            coord_offset += 1

            # Determine the distance between points
            self.D0[D0_offset] = geo_utils.e_dist(up, down)

            # The constraint will ALWAYS be set as a scaled value,
            # however, it is possible that the user has specified
            # individal values for each location. Therefore we
            # will convert these absolute values to an equilivant
            # scaled value. 
                
            if not scaled:
                lower[i] /= self.D0[D0_offset]
                upper[i] /= self.D0[D0_offset]
            #end
            D0_offset += 1
        # end for
        
        # Finally add the thickness constraint values
        self.thickConLower.extend(lower.flatten())
        self.thickConUpper.extend(upper.flatten())
        self.nThickCon += 1
        self.thickScaled.append(scaled)

        return

    def _generateDiscreteSurface(self, wing):

        # Generate discrete surface data for intersections:
        p0 = []
        v1 = []
        v2 = []
        level = 0
        for isurf in xrange(wing.nSurf):
            surf = wing.surfs[isurf]
            ku = surf.ku
            kv = surf.kv
            tu = surf.tu
            tv = surf.tv
            
            u = geo_utils.fill_knots(tu, ku, level)
            v = geo_utils.fill_knots(tv, kv, level)

            for i in xrange(len(u)-1):
                for j in xrange(len(v)-1):
                    P0 = surf(u[i  ], v[j  ])
                    P1 = surf(u[i+1], v[j  ])
                    P2 = surf(u[i  ], v[j+1])
                    P3 = surf(u[i+1], v[j+1])

                    p0.append(P0)
                    v1.append(P1-P0)
                    v2.append(P2-P0)

                    p0.append(P3)
                    v1.append(P2-P3)
                    v2.append(P1-P3)

                # end for
            # end for
        # end for
        p0 = numpy.array(p0)
        v1 = numpy.array(v1)
        v2 = numpy.array(v2)

        return p0,v1,v2

    def addVolumeConstraint(self, wing, le_list, te_list, nSpan, nChord,
                            lower=1.0, upper=3.0, scaled=True):

        '''
        Inputs:

        wing: a pyGeo object representing the wing

        le_list: A list defining the "leading edge" or start of the domain

        te_list: A list defining the "trailing edge" or end of the domain

        nChord: The number values in the chord-wise direction (between
        le_list and te_list)

        nSpan: The number of span-wise points
     
        Lower: The low range for the thickness constraint
        
        Upper: The upper bound for the thickness constraint

        Scaled: True if constraint value is to be scaled by inital
        thickness. Scale=True and lower=1.0 will constraint to
        original volume. If an absolute volume is required, set
        lower to desired value and sclae=False.
        '''
        
        self.volumeConPtr.append([len(self.coords),
                                  len(self.coords) + nSpan*nChord*2])

        # Create mesh of itersections
        root_line = [le_list[0], te_list[0]]
        tip_line  = [le_list[-1], te_list[-1]]
        le_s = pySpline.curve(X=le_list, k=2)
        te_s = pySpline.curve(X=te_list, k=2)
        root_s = pySpline.curve(X=[le_list[0], te_list[0]], k=2)
        tip_s  = pySpline.curve(X=[le_list[-1], te_list[-1]], k=2)

        span_s = numpy.linspace(0, 1, nSpan)
        chord_s = numpy.linspace(0, 1, nChord)
        
        # Generate a 2D region of intersections
        X = geo_utils.tfi_2d(le_s(span_s), te_s(span_s),
                             root_s(chord_s), tip_s(chord_s))

        # Generate discrete surface data for intersections:
        p0,v1,v2 = self._generateDiscreteSurface(wing)

        # Append the new coordinates to self.coords
        coord_offset = len(self.coords)
        self.coords = numpy.append(self.coords, numpy.zeros(
                (nSpan*nChord*2, 3)),axis=0)

        # Generate all intersections:
        for i in xrange(nSpan): 
            for j in xrange(nChord):
                # Generate the 'up_vec' from taking the cross product
                # across a quad
                if i == 0:
                    u_vec = X[i+1, j]-X[i, j]
                elif i == nSpan - 1:
                    u_vec = X[i, j] - X[i-1, j]
                else:
                    u_vec = X[i+1, j] - X[i-1, j]
                # end if

                if j == 0:
                    v_vec = X[i, j+1]-X[i, j]
                elif j == nChord - 1:
                    v_vec = X[i, j] - X[i, j-1]
                else:
                    v_vec = X[i, j+1] - X[i, j-1]
                # end if

                up_vec = numpy.cross(u_vec, v_vec)
                
                # Project actual node:
                up, down, fail = geo_utils.projectNode(
                    X[i,j], up_vec, p0, v1, v2)

                if fail:
                    print 'DVConstraints: Project Node failed. Cannot continue'
                    sys.exit(0)
                # end if

                self.coords[coord_offset, :] = up
                coord_offset += 1

                self.coords[coord_offset, :] = down
                coord_offset += 1
            # end for
        # end for

        # Evaluate the thickness based on these points to get the
        # initial reference volume

        self.volumeConSizes.append([nSpan,nChord])
        V0_offset = len(self.V0)
        self.V0.append(self._evalVolume(V0_offset))

        # The constraint will ALWAYS be set as a scaled value,
        # however, it is possible that the user has specified
        # individal values for each location. Therefore we
        # will convert these absolute values to an equilivant
        # scaled value. 
                
        if not scaled:
            lower /= self.V0[V0_offset]
            upper /= self.V0[V0_offset]
        # end if
        
        # Finally add the thickness constraint values
        self.volumeConLower.append(lower)
        self.volumeConUpper.append(upper)
        self.nVolumeCon += 1
        self.volumeScaled.append(scaled)


        return

    def addLeTeCon(self, DVGeo, up_ind, low_ind):
        '''Add Leading Edge and Trailing Edge Constraints to the FFD
        at the indiceis defined by up_ind and low_ind'''

        assert len(up_ind) == len(low_ind),  'up_ind and low_ind are\
 not the same length'

        if DVGeo.FFD: # Only Setup for FFD's currently
            # Check to see if we have local design variables in DVGeo
            if len(DVGeo.DV_listLocal) == 0:
                mpiPrint('Warning: Trying to add Le/Te Constraint when no local variables found')
            # end if

            # Loop over each set of Local Design Variables
            for i in xrange(len(DVGeo.DV_listLocal)):
                
                # We will assume that each GeoDVLocal only moves on
                # 1,2, or 3 coordinate directions (but not mixed)
                temp = DVGeo.DV_listLocal[i].coef_list
                for j in xrange(len(up_ind)): # Try to find this index
                                              # in the coef_list
                    up = None
                    down = None
                    for k in xrange(len(temp)):
                        if temp[k][0] == up_ind[j]:
                            up = k
                        # end if
                        if temp[k][0] == low_ind[j]:
                            down = k
                        # end for
                    # end for
                    # If we haven't found up AND down do nothing
                    if up is not None and down is not None:
                        self.LeTeCon.append([i, up, down])
                    # end if
                # end for
            # end for
            
            # Finally, unique the list to parse out duplicates. Note:
            # This sort may not be stable however, the order of the
            # LeTeCon list doens't matter
            self.LeTeCon = geo_utils.unique(self.LeTeCon)
        else:
            mpiPrint('Warning: addLeTECon is only setup for FFDs')
        # end if

        return

    def writeTecplot(self, fileName): 
        ''' This function write a visualization of the constraints to
        tecplot. The thickness and volume constraints are grouped
        accordng to how they were added for easy identificaton in tecplot

        Input: fileName: Name of tecplot filename
        '''
        
        f = open(fileName,'w')
        f.write("TITLE = \"DVConstraints Data\"\n")
        f.write("VARIABLES = \"CoordinateX\" \"CoordinateY\" \"CoordinateZ\"\n")

        # Write out the thickness constraints first:
        for ii in xrange(self.nThickCon):
            nNodes = self.thickConPtr[ii][1] - self.thickConPtr[ii][0]
            nElem = nNodes/2
            # Write a fe line segment zone:
            f.write("ZONE T=\"ThickCon_%d\"\n"%(ii))
            f.write("Nodes=%d, Elements=%d, ZONETYPE=FELineSeg\n"%(
                    nNodes,nElem))
            f.write("DATAPACKING=POINT\n")

            for i in xrange(self.thickConPtr[ii][0], self.thickConPtr[ii][1]):
                f.write('%f %f %f\n'%(self.coords[i,0],
                                      self.coords[i,1],
                                      self.coords[i,2]))
            # end for
            for i in xrange(nElem):
                f.write('%d %d\n'%(2*i+1,2*i+2))
            # end for
        # end for

        # Write out the volume constraints second:
        for iVolCon in xrange(self.nVolumeCon):
            nSpan = self.volumeConSizes[iVolCon][0]
            nChord = self.volumeConSizes[iVolCon][1]
            # Extract the coordinates:
            istart = self.volumeConPtr[iVolCon][0]
            iend   = self.volumeConPtr[iVolCon][1]
            x = self.coords[istart:iend].flatten().reshape(
                [nSpan, nChord, 2, 3])
            f.write('Zone T=VolumeCon_%d I=%d J=%d K=%d\n'%(
                    iVolCon, nSpan, nChord, 2))
            f.write('DATAPACKING=POINT\n')
            for k in xrange(2):
                for j in xrange(nChord):
                    for i in xrange(nSpan):
                        f.write('%f %f %f\n'%(x[i, j, k, 0],
                                              x[i, j, k, 1],
                                              x[i, j, k, 2]))
                    # end for
                # end for
            # end for
        # end for

        # Close the file
        f.close()

        return

    def getCoordinates(self):
        ''' Return the current set of coordinates used in
        DVConstraints'''

        return self.coords

    def setCoordinates(self, coords):
        ''' Set the new set of coordinates'''

        self.coords = coords.copy()

        return

    def addConstraintsPyOpt(self, opt_prob):
        ''' Add thickness contraints to pyOpt
        
         Input: opt_prob -> optimization problem
                lower    -> Fraction of initial thickness allowed
                upper    -> Fraction of upper thickness allowed
                '''
        if self.nThickCon > 0:
            opt_prob.addConGroup(
                'thickCon', len(self.thickConLower), 'i', 
                lower=self.thickConLower, upper=self.thickConUpper)
        # end if

        if self.nVolumeCon > 0:
            opt_prob.addConGroup(
                'volumeCon', len(self.volumeConLower), 'i',
                lower=self.volumeConLower, upper=self.volumeConUpper)
        # end if

        if self.LeTeCon:
            # We can just add them individualy
            for i in xrange(len(self.LeTeCon)):
                opt_prob.addCon('LeTeCon%d'%(i), 'i', lower=0.0, upper=0.0)
            # end for
        # end if

        return 

    def getLeTeConstraints(self, DVGeo):
        '''Evaluate the LeTe constraint using the current DVGeo opject'''

        con = numpy.zeros(len(self.LeTeCon))
        for i in xrange(len(self.LeTeCon)):
            dv = self.LeTeCon[i][0]
            up = self.LeTeCon[i][1]
            down = self.LeTeCon[i][2]
            con[i] = DVGeo.DV_listLocal[dv].value[up] + \
                DVGeo.DV_listLocal[dv].value[down]
        # end for

        return con

    def getLeTeSensitivity(self, DVGeo, scaled=True):
        ndv = DVGeo._getNDV()
        nlete = len(self.LeTeCon)
        dLeTedx = numpy.zeros([nlete, ndv])

        DVoffset = [DVGeo._getNDVGlobal()]
        # Generate offset lift of the number of local variables
        for i in xrange(len(DVGeo.DV_listLocal)):
            DVoffset.append(DVoffset[-1] + DVGeo.DV_listLocal[i].nVal)

        for i in xrange(len(self.LeTeCon)):
            # Set the two values a +1 and -1 or (+range - range if scaled)
            dv = self.LeTeCon[i][0]
            up = self.LeTeCon[i][1]
            down = self.LeTeCon[i][2]
            if scaled:
                dLeTedx[i, DVoffset[dv] + up  ] = \
                    DVGeo.DV_listLocal[dv].range[up  ]
                dLeTedx[i, DVoffset[dv] + down] =  \
                    DVGeo.DV_listLocal[dv].range[down]
            else:
                dLeTedx[i, DVoffset[dv] + up  ] =  1.0
                dLeTedx[i, DVoffset[dv] + down] =  1.0
            # end if
        # end for

        return dLeTedx

    def getThicknessConstraints(self):
        '''Return the current thickness constraints. Note that all
        thickness constraints are returned together...there is no
        disctinction between how they were added'''
        D = numpy.zeros(len(self.D0))

        for ii in xrange(self.nThickCon):
            for i in xrange(self.thickConPtr[ii][0]/2, 
                            self.thickConPtr[ii][1]/2):
                D[i] = geo_utils.e_dist(
                    self.coords[2*i, :],self.coords[2*i+1, :])
                if self.thickScaled[ii]:
                    D[i]/=self.D0[i]
            # end for
        # end for

        return D

    def getThicknessSensitivity(self, DVGeo, name=None):

        '''Return the derivative of all the thickness constraints We
        pass in the DVGeo object so this function retuns the full
        appropriate jacobian.
        
        '''

        nDV = DVGeo._getNDV()
        dTdx = numpy.zeros((self.nThickCon, nDV))
        dTdpt = numpy.zeros(self.coords.shape)

        for ii in xrange(self.nThickCon):
            for i in xrange(self.thickConPtr[ii][0]/2, 
                            self.thickConPtr[ii][1]/2):

                dTdpt[:, :] = 0.0

                p1b, p2b = geo_utils.e_dist_b(
                    self.coords[2*i, :], self.coords[2*i+1, :])
        
                dTdpt[2*i, :] = p1b
                dTdpt[2*i+1, :] = p2b

                if self.thickScaled[ii]:
                    dTdpt[2*i, :] /= self.D0[i]
                    dTdpt[2*i+1, :] /= self.D0[i]
                # end if

                dTdx[i, :] = DVGeo.totalSensitivity(dTdpt, name=name)
            # end for
        # end for

        return dTdx
        
    def getVolumeConstraints(self):
        '''Return the current volume constraints. Note all volume
        constraints are lumped together and returned as a list'''

        Volume = []
        for iVolCon in xrange(self.nVolumeCon):
            V = self._evalVolume(iVolCon)
            Volume.append(V)
            if self.volumeScaled[iVolCon]:
                Volume[iVolCon]/= self.V0[iVolCon]
            # end for
        # end for

        return Volume

    def getVolumeSensitivity(self, DVGeo, name=None):

        '''Return the derivative of all the volume constraints. We pass
        in the DVGeo object so this function returns the final DV jacobian
        '''

        nDV = DVGeo._getNDV()
        dVdx = numpy.zeros((self.nVolumeCon, nDV))
        timeA = time.time()
        for iVolCon in xrange(self.nVolumeCon):
            dVdpt = self._evalVolumeDerivative(iVolCon)
            if self.volumeScaled[iVolCon]:
                dVdpt /= self.V0[iVolCon]
            # end if

            dVdx[iVolCon, :] = DVGeo.totalSensitivity(dVdpt, name=name)
        # end for
   
        return dVdx
    
    def verifyVolumeSensitivity(self):
        """ Do a FD check on the reverse mode volume sensitity calculation"""

        V0 = self.getVolumeConstraints()
        h = 1e-4

        for iVolCon in xrange(self.nVolumeCon):

            mpiPrint("----------------------------------------------")
            mpiPrint(" Checking derivative of Volume Constraint %d"%(iVolCon))
            mpiPrint("----------------------------------------------")

            dVdpt = self._evalVolumeDerivative(iVolCon)
            if self.volumeScaled[iVolCon]:
                dVdpt /= self.V0[iVolCon]

            dVdpt2 = numpy.zeros_like(dVdpt)

            # Blindy loop over coefficients:
            for i in xrange(len(self.coords)):
                for idim in xrange(3):
                    self.coords[i,idim] += h

                    Vph = self.getVolumeConstraints()
                    dVdpt2[i,idim] = (Vph[iVolCon]-V0[iVolCon])/h

                    self.coords[i,idim] -= h
                    mpiPrint('pt %d, idim %d: %f %f'%(
                            i,idim,dVdpt[i,idim],dVdpt2[i,idim]))

                # end for
            # end for
        # end for
                    
        return

    def _evalVolume(self, iVolCon):

        # Sizes
        nSpan = self.volumeConSizes[iVolCon][0]
        nChord = self.volumeConSizes[iVolCon][1]

        # Extract the coordinates:
        istart = self.volumeConPtr[iVolCon][0]
        iend   = self.volumeConPtr[iVolCon][1]

        # x is the structured set of coordinates
        x = self.coords[istart:iend].flatten().reshape(
            [nSpan, nChord, 2, 3])

        Volume = 0.0
        ind = [[0,0,0],[1,0,0],[0,1,0],[1,1,0],
               [0,0,1],[1,0,1],[0,1,1],[1,1,1]]

        coords = numpy.zeros((2,2,2,3))
        for j in xrange(nChord-1):
            for i in xrange(nSpan-1):
                # Extract coordinates
                for ii in xrange(8):
                    coords[ind[ii][0], ind[ii][1], ind[ii][2], :] = \
                        x[i+ind[ii][0], j+ind[ii][1], 0+ind[ii][2]]
                # end for
                Volume += self._evalVolumeCube(coords)
            # end for
        # end for
        if Volume < 0:
            Volume = -Volume
            self.flipVolume = True

        return Volume

    def _evalVolumeCube(self, x):
        # Evaluate the volume of a cube defined by coords:
        
        i=1; j=1; k=1;
        l=0; m=0; n=0;
        
        xp = numpy.average(x[:,:,:,0])
        yp = numpy.average(x[:,:,:,1])
        zp = numpy.average(x[:,:,:,2])
         
        vp1 = self._volpym(x[i,j,k,0], x[i,j,k,1], x[i,j,k,2], 
                           x[i,j,n,0], x[i,j,n,1], x[i,j,n,2], 
                           x[i,m,n,0], x[i,m,n,1], x[i,m,n,2], 
                           x[i,m,k,0], x[i,m,k,1], x[i,m,k,2],
                           xp, yp, zp)
                
        vp2 = self._volpym(x[l,j,k,0], x[l,j,k,1], x[l,j,k,2], 
                           x[l,m,k,0], x[l,m,k,1], x[l,m,k,2], 
                           x[l,m,n,0], x[l,m,n,1], x[l,m,n,2], 
                           x[l,j,n,0], x[l,j,n,1], x[l,j,n,2],
                           xp, yp, zp)
                
        vp3 = self._volpym(x[i,j,k,0], x[i,j,k,1], x[i,j,k,2], 
                           x[l,j,k,0], x[l,j,k,1], x[l,j,k,2], 
                           x[l,j,n,0], x[l,j,n,1], x[l,j,n,2], 
                           x[i,j,n,0], x[i,j,n,1], x[i,j,n,2],
                           xp, yp, zp)

        vp4 = self._volpym(x[i,m,k,0], x[i,m,k,1], x[i,m,k,2], 
                           x[i,m,n,0], x[i,m,n,1], x[i,m,n,2], 
                           x[l,m,n,0], x[l,m,n,1], x[l,m,n,2], 
                           x[l,m,k,0], x[l,m,k,1], x[l,m,k,2],
                           xp, yp, zp)

        vp5 = self._volpym(x[i,j,k,0], x[i,j,k,1], x[i,j,k,2], 
                           x[i,m,k,0], x[i,m,k,1], x[i,m,k,2], 
                           x[l,m,k,0], x[l,m,k,1], x[l,m,k,2], 
                           x[l,j,k,0], x[l,j,k,1], x[l,j,k,2],
                           xp, yp, zp)

        vp6 = self._volpym(x[i,j,n,0], x[i,j,n,1], x[i,j,n,2], 
                           x[l,j,n,0], x[l,j,n,1], x[l,j,n,2], 
                           x[l,m,n,0], x[l,m,n,1], x[l,m,n,2], 
                           x[i,m,n,0], x[i,m,n,1], x[i,m,n,2],
                           xp, yp, zp)                 

        Volume  = (1.0/6.0)*(vp1 + vp2 + vp3 + vp4 + vp5 + vp6)

        return Volume
 
    def _evalVolumeDerivative(self, iVolCon):
        # Generate the derivative of the volume with respect to the
        # coordinates:

        # We will use CS since its easy and exact:

        # Sizes
        nSpan = self.volumeConSizes[iVolCon][0]
        nChord = self.volumeConSizes[iVolCon][1]

        # Extract the coordinates:
        istart = self.volumeConPtr[iVolCon][0]
        iend   = self.volumeConPtr[iVolCon][1]

        # x is the structured set of coordinates
        x = self.coords[istart:iend].flatten().reshape([nSpan, nChord, 2, 3])
        xd = numpy.zeros_like(x)

        ind = [[0,0,0],[1,0,0],[0,1,0],[1,1,0],
               [0,0,1],[1,0,1],[0,1,1],[1,1,1]]
        coords = numpy.zeros((2,2,2,3),'D')

        for j in xrange(nChord-1):
            for i in xrange(nSpan-1):

                # Extract Coordinates
                for ii in xrange(8):
                    coords[ind[ii][0], ind[ii][1], ind[ii][2], :] = \
                        x[i+ind[ii][0], j+ind[ii][1], 0+ind[ii][2]]
                # end for
                    
                # CS loop over coordinates:
                for ii in xrange(8):
                    for jj in xrange(3):
                        coords[ind[ii][0], ind[ii][1], ind[ii][2],jj] += 1e-40j

                        Volume = self._evalVolumeCube(coords)

                        xd[i+ind[ii][0],j+ind[ii][1],0+ind[ii][2],jj] += \
                            numpy.imag(Volume)/1e-40

                        coords[ind[ii][0], ind[ii][1], ind[ii][2],jj] -= 1e-40j
                    # end for
                # end for
            # end for
        # end for

        if self.flipVolume:
            xd = -xd

        # Add into actual derivative array
        dVdpt = numpy.zeros_like(self.coords)
        dVdpt[istart:iend,:] = xd.reshape([nSpan*nChord*2, 3])

        return dVdpt

    def _volpym(self, xa, ya, za, xb, yb, zb, xc, yc, zc, xd, yd, zd,
                xp, yp, zp):
        fourth = 1.0/4.0

        volpym = (xp - fourth*(xa + xb  + xc + xd))  \
            * ((ya - yc)*(zb - zd) - (za - zc)*(yb - yd))   + \
            (yp - fourth*(ya + yb  + yc + yd))                \
            * ((za - zc)*(xb - xd) - (xa - xc)*(zb - zd))   + \
            (zp - fourth*(za + zb  + zc + zd))                \
            * ((xa - xc)*(yb - yd) - (ya - yc)*(xb - xd))
        
        return volpym
   
