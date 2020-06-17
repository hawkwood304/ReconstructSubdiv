# noinspection PyPep8Naming
from __builtin__ import xrange
import maya.api.OpenMaya as Om2
import pymel.core as pm
import maya.cmds as cm
import time


# noinspection SpellCheckingInspection,PyCallByClass,PyAttributeOutsideInit,PyMethodMayBeStatic,PyUnusedLocal
class ReconstructSubdiv(object):

    def __init__(self):
        self.mayaVersion = cm.about(version=True)
        self.mayaOldVersions = ['2014' , '2015' , '2016' , '2017' , '2018' , '2019']
        self.reverse = False
        self.keepOrig = True
        self.curvature = True
        self.sharpCorners = True
        self.showProgress = True
        self.clrs = {
            'orange': (0.85882 , 0.58039 , 0.33725) ,
            'red': (1 , 0.353 , 0.353) ,
            'grey': (0.25 , 0.25 , 0.25)
        }

        if pm.window('RecostructWin' , exists=True):
            pm.deleteUI('RecostructWin')
        self.RecostructUI()

    def checkForNonQuad(self , Dag):
        badFaces = Om2.MSelectionList()
        meshIt = Om2.MItMeshPolygon(Dag)
        if self.mayaVersion not in self.mayaOldVersions:
            while not meshIt.isDone():
                if meshIt.polygonVertexCount() != 4:
                    badFaces.add((Dag , meshIt.currentItem()))
                meshIt.next()
        else:
            while not meshIt.isDone():
                if meshIt.polygonVertexCount() != 4:
                    badFaces.add((Dag , meshIt.currentItem()))
                meshIt.next(None)

        if badFaces.isEmpty():
            return True
        else:
            Om2.MGlobal.setActiveSelectionList(badFaces)
            pm.textField('meshes' , edit=True , ip=1 , bgc=self.clrs['red'] ,
                         text='Unable to reconstruct! Found non quad face(s) in mesh: "{0}"!'.format(Dag))
            cm.error('Unable to reconstruct! Found non quad face(s) in "{0}"!'.format(Dag))
            return False

    def getVtxPositions(self):
        vtxComponent = Om2.MFnSingleIndexedComponent()
        vtxComponent.create(Om2.MFn.kMeshVertComponent)
        vtxComponent.addElements(self.vtxIdArray)
        vtxIterator = Om2.MItMeshVertex(self.mDag , vtxComponent.object())
        while not vtxIterator.isDone():
            self.vtxPositions[int(vtxIterator.index())] = vtxIterator.position(Om2.MSpace.kWorld)
            vtxIterator.next()
        return self.vtxPositions

    def getStartVertex(self , vtxIdArray):

        vtxComponent = Om2.MFnSingleIndexedComponent()
        vtxComponent.create(Om2.MFn.kMeshVertComponent)
        vtxComponent.addElements(vtxIdArray)

        vtxIterator = Om2.MItMeshVertex(self.mDag , vtxComponent.object())

        vtxValence_2 = -1
        vtxValence_n = -1
        vtxValence_3 = -1
        vtxBorderValence_3 = -1

        while not vtxIterator.isDone():
            vtxId = int(vtxIterator.index())
            numEdges = vtxIterator.numConnectedEdges()
            onBoundary = vtxIterator.onBoundary()
            if onBoundary:
                self.vtxBoundary = self.vtxBoundary.union([vtxId])

            if vtxValence_2 == -1 and numEdges == 2:
                vtxValence_2 = vtxId

            elif vtxValence_n == -1 and numEdges > 4:
                vtxValence_n = vtxId

            elif vtxValence_3 == -1 and numEdges == 3 and not onBoundary:
                vtxValence_3 = vtxId

            elif vtxBorderValence_3 == -1 and numEdges == 3 and onBoundary:
                vtxBorderValence_3 = vtxId

            vtxIterator.next()

        if vtxValence_2 != -1:
            return vtxValence_2

        elif vtxValence_n != -1:
            return vtxValence_n

        elif vtxValence_3 != -1:
            return vtxValence_3

        elif vtxBorderValence_3 != -1:
            return vtxBorderValence_3

        else:
            return 0

    def getNearComponents(self , vtxId , diagonal=0 , edgesConnected=0):
        vtxComponent = Om2.MFnSingleIndexedComponent()
        vtxComponent.create(Om2.MFn.kMeshVertComponent)
        vtxComponent.addElement(vtxId)

        vtxIterator = Om2.MItMeshVertex(self.mDag , vtxComponent.object())

        if edgesConnected:
            return set(vtxIterator.getConnectedEdges())

        vtxConnected = set(vtxIterator.getConnectedVertices())

        if not diagonal:
            return vtxConnected

        facesConnected = vtxIterator.getConnectedFaces()

        vtxAround = set()
        for f in facesConnected:
            faceComponent = Om2.MFnSingleIndexedComponent()
            faceComponent.create(Om2.MFn.kMeshPolygonComponent)
            faceComponent.addElement(f)

            faceIterator = Om2.MItMeshPolygon(self.mDag , faceComponent.object())
            vtxOfFace = faceIterator.getVertices()
            for vf in vtxOfFace:
                vtxAround.add(vf)

        vtxAround.remove(vtxId)
        vtxDiagonal = vtxAround - vtxConnected
        return vtxDiagonal

    def getOverVertices(self , vtxIds):
        result = set()
        for vtxId in vtxIds:
            vtxGrow = set()
            vtxConnected = self.getNearComponents(vtxId)
            self.vtxDict[vtxId] = {
                'connected': {
                    k: None for k in vtxConnected
                }
            }
            vtxDiagonal = self.getNearComponents(vtxId , diagonal=True)
            self.vtxDict[vtxId]['diagonal'] = vtxDiagonal

            for v in vtxConnected:
                vtxConnected2 = self.getNearComponents(v)
                self.vtxDict[vtxId]['connected'][v] = vtxConnected2
                vtxGrow = vtxGrow.union(vtxConnected2)

            vtxOver = vtxGrow - vtxDiagonal
            result = result.union(vtxOver)

        return result

    def vtxSearch(self , vtxStart):
        vtxPrev = [vtxStart]
        while True:
            vtxNext = (self.getOverVertices(vtxPrev) - set(self.vtxDict))
            if not vtxNext:
                return
            vtxPrev = vtxNext

    def vtxSearchProgress(self , vtxStart):
        vtxPrev = [vtxStart]
        while True:
            vtxNext = (self.getOverVertices(vtxPrev) - set(self.vtxDict))
            if not vtxNext:
                return
            vtxPrev = vtxNext

            for v in vtxPrev:
                self.progress_current += self.progress_step
                pm.progressBar('progress' , edit=True , progress=round(self.progress_current))

    # noinspection PyTypeChecker
    def getAvaraveragePositions(self , points , plus=False):
        vector = Om2.MVector()
        for p in points:
            vector += Om2.MVector(self.vtxPositions[p])
        if plus:
            return vector
        return vector / len(points)

    # noinspection PyTypeChecker
    def getCurvature(self):
        # Calculate boundary vtx
        vtxBoundary = self.vtxBoundary & set(self.vtxDict)
        for v in list(vtxBoundary):
            n = len(self.vtxDict[v]['connected'])
            if self.sharpCorners:
                if n == 2:
                    continue
            ek1 = tuple(set(self.vtxDict[v]['connected']) & self.vtxBoundary)
            e0k1 = Om2.MVector(self.vtxPositions[ek1[0]])
            e1k1 = Om2.MVector(self.vtxPositions[ek1[1]])
            vk1 = Om2.MVector(self.vtxPositions[v])

            vk = -(0.5 * e0k1) + (2 * vk1) - (0.5 * e1k1)
            self.vtxPositionsNew[v] = vk

        # Calculate not boundary vtx with connected edges n >= 4
        vtxNotBoundary = list(set(self.vtxDict) - vtxBoundary)
        for v in vtxNotBoundary:
            n = len(self.vtxDict[v]['connected'])
            if n >= 4:
                A = n / (n - 3.0)
                B = -4.0 / (n * (n - 3.0))
                Y = 1.0 / (n * (n - 3.0))

                vk1 = Om2.MVector(self.vtxPositions[v])
                Average_ek1 = self.getAvaraveragePositions(self.vtxDict[v]['connected'] , plus=True)
                Average_fk1 = self.getAvaraveragePositions(self.vtxDict[v]['diagonal'] , plus=True)

                vk = A * vk1 + B * Average_ek1 + Y * Average_fk1
                self.vtxPositionsNew[v] = vk

        # Calculate not boundary vtx with connected edges n == 3
        for v in vtxNotBoundary:
            n = len(self.vtxDict[v]['connected'])
            if n == 3:
                for v1 in self.vtxDict[v]['connected']:
                    vk_near = (self.vtxDict[v]['connected'][v1] - self.vtxDict[v]['diagonal'] - {v})
                    if vk_near:
                        vk_near = int(vk_near.pop())

                        if vk_near in self.vtxPositionsNew and vk_near not in self.vtxBoundary:
                            ek = Om2.MVector(self.vtxPositionsNew[vk_near])
                            ek1 = Om2.MVector(self.vtxPositions[v1])
                            fk1 = tuple(self.vtxDict[v]['connected'][v1] & self.vtxDict[v]['diagonal'])
                            f0k1 = Om2.MVector(self.vtxPositions[fk1[0]])
                            f1k1 = Om2.MVector(self.vtxPositions[fk1[1]])

                            vk = 4 * ek1 - ek - f1k1 - f0k1
                            self.vtxPositionsNew[v] = vk
                            break

        # Calculate one more time not boundary vtx with connected edges n == 3
        for v in set(vtxNotBoundary) - set(self.vtxPositionsNew):
            n = len(self.vtxDict[v]['connected'])
            if n == 3:
                for v1 in self.vtxDict[v]['connected']:
                    vk_near = (self.vtxDict[v]['connected'][v1] - self.vtxDict[v]['diagonal'] - [v])
                    if vk_near:
                        vk_near = int(vk_near.pop())

                        if vk_near in self.vtxPositionsNew and vk_near not in self.vtxBoundary:
                            ek = Om2.MVector(self.vtxPositionsNew[vk_near])
                            ek1 = Om2.MVector(self.vtxPositions[v1])
                            fk1 = tuple(self.vtxDict[v]['connected'][v1] & self.vtxDict[v]['diagonal'])
                            f0k1 = Om2.MVector(self.vtxPositions[fk1[0]])
                            f1k1 = Om2.MVector(self.vtxPositions[fk1[1]])

                            vk = 4 * ek1 - ek - f1k1 - f0k1
                            self.vtxPositionsNew[v] = vk
                            break

        vtxPositionsUpdated = self.vtxPositions
        for k , v in self.vtxPositionsNew.iteritems():
            vtxPositionsUpdated[k] = v
        self.vtxPositionsNew = vtxPositionsUpdated

    def moveVtx(self):
        mfnMesh = Om2.MFnMesh(self.mDag)
        array = Om2.MFloatPointArray()
        for k in sorted(self.vtxPositionsNew):
            array.append(Om2.MFloatPoint(self.vtxPositionsNew[k]))
        mfnMesh.setPoints(array , space=Om2.MSpace.kWorld)

    def edgeDelete(self , vtxs):
        edgeIds = []
        for v in vtxs:
            for e in self.getNearComponents(v , edgesConnected=1):
                edgeIds.append(e)

        edgeIds = set(edgeIds)

        edgeComponent = Om2.MFnSingleIndexedComponent()
        components = edgeComponent.create(Om2.MFn.kMeshEdgeComponent)
        map(edgeComponent.addElement , edgeIds)

        edgeSel = Om2.MSelectionList()
        edgeSel.add((self.mDag , components))
        Om2.MGlobal.setActiveSelectionList(edgeSel)
        cm.polyDelEdge(cv=True , ch=False)

    def makeDuplicates(self):
        duplicates = []
        for i in range(len(self.mDags)):
            dup = cm.duplicate(self.mDags[i] , name='{0}_recon'.format(self.mDags[i]))[0]
            duplicates.append(dup)
            tmpSel = Om2.MSelectionList()
            tmpSel.add(dup)
            newDag = tmpSel.getDagPath(0)
            self.mSel.replace(i , newDag)
            self.mDags[i] = self.mSel.getDagPath(i)

        bbox = cm.exactWorldBoundingBox(duplicates)
        translate = (bbox[3] - bbox[0]) * 1.1
        cm.move(translate , 0 , 0 , duplicates , r=1)

    def reconstruct(self):
        self.vtxDict = {

        }
        self.vtxPositions = {

        }
        self.vtxPositionsNew = {

        }
        self.vtxBoundary = set()
        self.vtxCount = cm.polyEvaluate(self.mDag , v=True)
        self.vtxIdArray = xrange(self.vtxCount)
        self.vtxMax = self.vtxCount / 4.0
        self.progress_step = 1.0 / self.vtxMax * 100
        self.progress_current = 0

        self.getVtxPositions()

        if not self.reverse:
            vtxStart = self.getStartVertex(self.vtxIdArray)
        else:
            vtxStart = self.getNearComponents(self.getStartVertex(self.vtxIdArray) , diagonal=True).pop()

        print('Searching vertices...')

        if self.showProgress:
            self.vtxSearchProgress(vtxStart)
        else:
            self.vtxSearch(vtxStart)

        if self.curvature:
            print('Recostructing curvature...')
            self.getCurvature()
            self.moveVtx()

        print('Deleting edges...')

        self.edgeDelete(j for i in self.vtxDict for j in self.vtxDict[i]['diagonal'])

    def separate(self):
        for i in range(len(self.mDags)):
            shellCount = cm.polyEvaluate(self.mDags[i] , shell=True)
            if shellCount > 1:
                separatedObj = cm.polySeparate(self.mDags[i] , ch=False)
                tmpSel = Om2.MSelectionList()
                self.mDags[i] = [self.mDags[i]]
                for obj in separatedObj:
                    tmpSel.clear()
                    tmpSel.add(obj)
                    self.mDags[i].append(tmpSel.getDagPath(0))

    def getObjects(self):
        shapes = [i.split('|')[:-1] for i in cm.ls(sl=True , dag=True , l=True , s=True)]
        objects = []
        for i in shapes:
            string = ''
            for j in i[1:]:
                string += '|{0}'.format(j)
            objects.append(string)
        if objects:
            return objects
        else:
            return False

    def Main(self):
        start = time.time()
        print('Preparing...')
        self.mSel = Om2.MSelectionList()
        objects = self.getObjects()
        if not objects:
            self.uiClear()
            pm.textField('meshes' , edit=True , bgc=self.clrs['red'] , text='No object(s) selected!')
            cm.error('No object(s) selected!')
            return
        else:
            self.mDags = []
            mDagBackup = []
            for i in range(len(objects)):
                self.mSel.add(objects[i])
                self.mDags.append(self.mSel.getDagPath(i))
                mDagBackup.append(self.mSel.getDagPath(i))
                if not self.checkForNonQuad(self.mDags[i]):
                    return

        if self.keepOrig:
            self.makeDuplicates()

        self.separate()

        for id_vtx , obj in enumerate(self.mDags):
            if isinstance(obj , list):
                for id2 , subObj in enumerate(obj[1:]):
                    self.mDag = subObj
                    pm.textField('meshes' , edit=True , bgc=self.clrs['grey'] ,
                                 text='Recostrucing: "{0}"'.format(mDagBackup[id_vtx]))
                    pm.text('meshesNum' , edit=True ,
                            label='Submesh: {2}/{3}\nMesh: {0}/{1}'.format(id_vtx + 1 , len(self.mDags) , id2 + 1 ,
                                                                           len(obj[1:])))
                    self.reconstruct()
            else:
                self.mDag = obj
                pm.textField('meshes' , edit=True , bgc=self.clrs['grey'] ,
                             text='Recostrucing: "{0}"'.format(mDagBackup[id_vtx]))
                pm.text('meshesNum' , edit=True , label='Mesh: {0}/{1}'.format(id_vtx + 1 , len(self.mDags)))
                self.reconstruct()

        Om2.MGlobal.setActiveSelectionList(self.mSel)

        end = time.time() - start
        self.uiClear()
        pm.text('meshesNum' , edit=True , label='Time spent: {0} sec'.format(round(end , 4)))
        pm.textField('meshes' , edit=True , bgc=self.clrs['orange'] , text='Done!')
        print('Done!')

    def reverse_True(self):
        self.reverse = True

    def reverse_False(self):
        self.reverse = False

    def keepOrig_True(self):
        self.keepOrig = True

    def keepOrig_False(self):
        self.keepOrig = False

    def sharpCorners_True(self):
        self.sharpCorners = True

    def sharpCorners_False(self):
        self.sharpCorners = False

    def curvature_True(self):
        self.curvature = True
        pm.checkBoxGrp('sharpCorners' , edit=True , en=True)

    def curvature_False(self):
        self.curvature = False
        pm.checkBoxGrp('sharpCorners' , edit=True , en=False)

    def progress_True(self):
        self.showProgress = True

    def progress_False(self):
        self.showProgress = False

    def expand(self):
        pm.frameLayout('more' , edit=True , l='Less')
        pm.window('RecostructWin' , edit=True , height=312)

    def collapse(self):
        pm.frameLayout('more' , edit=True , l='More')
        pm.window('RecostructWin' , edit=True , height=172)

    def uiClear(self):
        pm.textField('meshes' , edit=True , text='')
        pm.text('meshesNum' , edit=True , label='')
        pm.progressBar('progress' , edit=True , progress=0)

    def RecostructUI(self):

        template = pm.uiTemplate()
        template.define(pm.frameLayout , mh=6 , mw=5)
        template.define(pm.columnLayout , adj=1 , rs=2)

        with pm.window('RecostructWin' , title='Recostruct Subdiv v1.3' , menuBar=True , menuBarVisible=True) as win:
            pm.window('RecostructWin' , edit=True , width=420 , height=172)
            with pm.frameLayout(lv=False , bv=False , mh=2 , mw=7):
                with template:
                    with pm.columnLayout():
                        pm.button(label='Recostruct Subdiv' , c=pm.Callback(self.Main) , h=40 , bgc=self.clrs['orange'])
                        with pm.frameLayout('more' , l='More' , cll=True , cl=True , ec=pm.Callback(self.expand) ,
                                            cc=pm.Callback(self.collapse)):
                            with pm.columnLayout(cat=('left' , -20)):
                                pm.checkBoxGrp(
                                    numberOfCheckBoxes=1 ,
                                    columnAlign=(1 , 'right') ,
                                    label='Settings: ' ,
                                    label1='Keep original (Recostructing is not undoable)' ,
                                    v1=True ,
                                    on1=pm.Callback(self.keepOrig_True) ,
                                    of1=pm.Callback(self.keepOrig_False)
                                )
                                pm.checkBoxGrp(
                                    numberOfCheckBoxes=1 ,
                                    columnAlign=(1 , 'right') ,
                                    label='' , label1='Recostruct vertex positions' ,
                                    v1=True ,
                                    on1=pm.Callback(self.curvature_True) ,
                                    of1=pm.Callback(self.curvature_False) ,
                                )
                                pm.checkBoxGrp(
                                    'sharpCorners' ,
                                    numberOfCheckBoxes=1 ,
                                    columnAlign=(1 , 'right') ,
                                    label='' , label1='Sharp corners' ,
                                    v1=True ,
                                    on1=pm.Callback(self.sharpCorners_True) ,
                                    of1=pm.Callback(self.sharpCorners_False) ,
                                )
                                pm.checkBoxGrp(
                                    numberOfCheckBoxes=1 ,
                                    columnAlign=(1 , 'right') ,
                                    label='' ,
                                    label1='Turn Off progress bar (Increase speed)' ,
                                    v1=False ,
                                    on1=pm.Callback(self.progress_False) ,
                                    of1=pm.Callback(self.progress_True)
                                )
                                rb = pm.radioButtonGrp(numberOfRadioButtons=1 , on1=pm.Callback(self.reverse_False) ,
                                                       label='' , sl=1 ,
                                                       label1='Default starting point (For most cases)')
                                pm.radioButtonGrp(numberOfRadioButtons=1 , on1=pm.Callback(self.reverse_True) ,
                                                  shareCollection=rb , label='' ,
                                                  label1='Reverse starting point (For special cases)')
                    with pm.frameLayout(l='Progress'):
                        pm.progressBar('progress' , h=25 , ii=True)
                        with pm.rowColumnLayout(
                                numberOfColumns=2 ,
                                cal=[(1 , 'left') ,
                                     (2 , 'right')] ,
                                columnWidth=[(1 , 275) , (2 , 125)]
                        ):
                            pm.textField('meshes' , text='' , ed=False , width=200)
                            pm.text('meshesNum' , label='' , height=25)
