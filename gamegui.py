#!/usr/bin/env python27
# -*-encoding:utf8;-*-
from __future__ import print_function

import sys
import math
import panda3d.core
import direct.showbase.ShowBase
import direct.gui.OnscreenText
import direct.task.Task
import direct.interval.LerpInterval
import direct.gui.DirectCheckButton
import gamearena


class IllegalMoveException(Exception):
    pass


class MyChessboard(direct.showbase.ShowBase.ShowBase):
    def __init__(self, fStartDirect=True, windowType=None):
        direct.showbase.ShowBase.ShowBase.__init__(self, fStartDirect=fStartDirect, windowType=windowType)
        self.disableMouse()

        self.__picker = panda3d.core.CollisionTraverser()
        self.__handler = panda3d.core.CollisionHandlerQueue()
        # Make a collision node for our picker ray
        self.__pickerNode = panda3d.core.CollisionNode('mouseRay')
        # Attach that node to the camera since the ray will need to be positioned relative to it
        self.__pickerNP = self.camera.attachNewNode(self.__pickerNode)
        # Everything to be picked will use bit 1. This way if we were doing other collision we could separate it
        self.__pickerNode.setFromCollideMask(panda3d.core.BitMask32.bit(1))
        # Make our ray and add it to the collision node
        self.__pickerRay = panda3d.core.CollisionRay()
        self.__pickerNode.addSolid(self.__pickerRay)
        # Register the ray as something that can cause collisions
        self.__picker.addCollider(self.__pickerNP, self.__handler)

        self.__labels = self.__defaultLabels()
        self.__chessboardTopCenter = self.render.attachNewNode("chessboardTopCenter")  # 定位棋盘顶面的中心位置
        self.__pieceRoot = self.__chessboardTopCenter.attachNewNode("pieceRoot")  # 虚拟根节点用于归纳棋子对象
        self.__chessboard = self.__defaultChessboard(self.__chessboardTopCenter, self.__pieceRoot)
        squares = self.__chessboard['squares']  # 后面会通过变量 squares[i] 查询 64 个棋盘方格空间位置并挂载全部棋子模型

        # 载入棋子模型
        white_piece_model = self.__selectChessPieceModelSytle('models/default')
        black_piece_model = self.__selectChessPieceModelSytle('models/default')
        name_order = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook']
        colors = {
            'WHITE': (1.000, 1.000, 1.000, 1),  # RGB color for WHITE pieces
            'BLACK': (0.150, 0.150, 0.150, 1),  # RGB color for BLACK pieces
        }

        # 利用 GameArena() 进行沙盘推演，是为了检查每个棋子的走法是否符合国际象棋规则
        self.arena = gamearena.GameArena(8, 8)
        unit_types_without_pawn = [
            ('king', gamearena.KingUnit),
            ('queen', gamearena.QueenUnit),
            ('rook', gamearena.RookUnit),
            ('knight', gamearena.KnightUnit),
            ('bishop', gamearena.BishopUnit),
        ]
        white_unit_type_list = dict(unit_types_without_pawn + [('pawn', gamearena.WhitePawnUnit)])
        black_unit_type_list = dict(unit_types_without_pawn + [('pawn', gamearena.BlackPawnUnit)])
        white_player = gamearena.GameArena.PlayerID(1)
        black_player = gamearena.GameArena.PlayerID(2)

        # 创建模型实例
        # 双方各 16 个棋子: 白棋棋子位于 _square[0]~[15], 黑棋位于 _square[48]~[63]
        pieces_sorted_by_square = [None] * 64
        piece_id_sorted_by_square = [0] * 64
        pieces_sorted_by_id = {}
        for i, name in zip(range(16), name_order + ['pawn'] * 8):
            # 实例化棋子的 3D 模型(初始定位到棋盘方格模型的上方)
            piece_holder = squares[i].attachNewNode("pieceInstanceHolder")
            piece_holder.setColor(colors['WHITE'])
            white_piece_model[name].instanceTo(piece_holder)
            # Arena 中的对应点位建立相同的棋子:
            point = (i % 8, i // 8)
            pid = self.arena.new_unit_recruited_by_player(white_player, point, white_unit_type_list[name])
            piece_id_sorted_by_square[i] = pid
            piece = CustomizedPiece(piece_holder, mask=panda3d.core.BitMask32.bit(1))
            piece.setTag('piece', str(pid))
            pieces_sorted_by_square[i] = piece
            pieces_sorted_by_id[pid] = piece
        for i, name in zip(range(64 - 16, 64), ['pawn'] * 8 + name_order):

            piece_holder = squares[i].attachNewNode("pieceInstanceHolder")
            piece_holder.setColor(colors['BLACK'])
            piece_holder.setH(180)  
            black_piece_model[name].instanceTo(piece_holder)

            point = (i % 8, i // 8)
            pid = self.arena.new_unit_recruited_by_player(black_player, point, black_unit_type_list[name])
            piece_id_sorted_by_square[i] = pid
            piece = CustomizedPiece(piece_holder, mask=panda3d.core.BitMask32.bit(1))
            piece.setTag('piece', str(pid))
            pieces_sorted_by_square[i] = piece
            pieces_sorted_by_id[pid] = piece


        self.__pieceOnSquare = pieces_sorted_by_square
        self.__pieces = pieces_sorted_by_id
        self.__pidOnSquare = piece_id_sorted_by_square

        self.__graveyard = self.__defaultGraveyard() 
        self.__pointingTo = 0 
        self.__dragging = 0 
        self.__finger = self.__pieceRoot.attachNewNode('fingerTouching')
        self.__mouse3 = None 
        self.__hsymbol = 1

        self.taskMgr.add(self.mouseTask, 'MouseTask')
        self.accept('escape', sys.exit) 
        self.accept("mouse1", self.onMouse1Pressed)  
        self.accept("mouse1-up", self.onMouse1Released) 
        self.accept("mouse3", self.onMouse3Pressed)
        self.accept("mouse3-up", self.onMouse3Released)

        self.axisCameraPitching = self.render.attachNewNode("axisCameraPitching")  
        self.axisCameraPitching.setHpr(h=0, p=-45, r=0)  
        self.camera.reparentTo(self.axisCameraPitching)
        self.camera.setPos(x=0, y=-15.0, z=0)
        self.accept('page_up', self.onKeyboardPageUpPressed)
        self.accept('page_down', self.onKeyboardPageDownPressed)  
        self.accept('wheel_up', self.onMouseWheelRolledUpwards)  
        self.accept('wheel_down', self.onMouseWheelRolledDownwards)  

    def __defaultLabels(self):
        labels = [
            direct.gui.OnscreenText.OnscreenText(
                text="Powered by Panda3D",
                parent=self.a2dBottomRight, align=panda3d.core.TextNode.A_right,
                style=1, fg=(1, 1, 1, 1), pos=(-0.1, 0.1), scale=.07)
            ,
            direct.gui.OnscreenText.OnscreenText(
                text="ESC: Quit",
                parent=self.a2dTopLeft, align=panda3d.core.TextNode.ALeft,
                style=1, fg=(1, 1, 1, 1), pos=(0.06, -0.1), scale=.05)
            ,
            direct.gui.OnscreenText.OnscreenText(
                text="Mouse wheel: Zoom in/out the camera",
                parent=self.a2dTopLeft, align=panda3d.core.TextNode.ALeft,
                style=1, fg=(1, 1, 1, 1), pos=(0.06, -0.15), scale=.05)
            ,
            direct.gui.OnscreenText.OnscreenText(
                text="PageUp/PageDown: Camera orientation",
                parent=self.a2dTopLeft, align=panda3d.core.TextNode.ALeft,
                style=1, fg=(1, 1, 1, 1), pos=(0.06, -0.2), scale=.05)
        ]
        return labels

    def mouseTask(self, task):
        """mouseTask deals with the highlighting and dragging based on the mouse"""

        marks = self.__chessboard['marks']
        squareRoot = self.__chessboard['squareRoot']


        if self.__pointingTo:
            i = self.__pointingTo - 1
            marks[i].setScale(0.75)
            if not self.__marksAlwaysVisible or not (i in self.__validMarks):
                marks[i].hide()
            if self.__hasPieceOnSquare(i):
                self.__pieceOnSquare[i].hideBounds()
            self.__pointingTo = False


        if not self.mouseWatcherNode.hasMouse():
            return direct.task.Task.cont


        mpos = self.mouseWatcherNode.getMouse()

        self.__pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())

        p = self.render.getRelativePoint(self.camera, self.__pickerRay.getOrigin())
        v = self.render.getRelativeVector(self.camera, self.__pickerRay.getDirection())
        z = 0
        t = - p.getZ() / v.getZ()  
        x = p.getX() + v.getX() * t
        y = p.getY() + v.getY() * t
        self.__finger.setPos(x, y, z)

        if self.__dragging:

            i = self.__dragging - 1
            piece = self.__pieceOnSquare[i]
            piece.picker.traverse(squareRoot) 
            if piece.handler.getNumEntries() > 0:
                piece.handler.sortEntries()
                entry = piece.handler.getEntry(0)
                tag = 'square'
                value = entry.getIntoNode().getTag(tag)
                i = int(value)
                self.__pointingTo = i + 1
        else:
            self.__picker.traverse(self.__pieceRoot)  
            if self.__handler.getNumEntries() > 0:
                self.__handler.sortEntries()
                entry = self.__handler.getEntry(0)
                tag = 'piece'
                value = entry.getIntoNode().getTag(tag)
                try:
                    piece_id = int(value)
                except ValueError:
                    pass  # Ignore this case
                else:
                    for i, pid in enumerate(self.__pidOnSquare):
                        if pid == piece_id:
                            self.__pointingTo = i + 1
                            break
            else:
                self.__picker.traverse(squareRoot)
                if self.__handler.getNumEntries() > 0:
                    self.__handler.sortEntries()
                    entry = self.__handler.getEntry(0)
                    tag = 'square'
                    value = entry.getIntoNode().getTag(tag)
                    i = int(value)
                    self.__pointingTo = i + 1

        if self.__pointingTo:
            i = self.__pointingTo - 1
            if self.__dragging:
                marks[i].setScale(1.02)
                marks[i].show()
            if self.__hasPieceOnSquare(i):
                if not self.__dragging or (self.__dragging and self.__pointingTo != self.__dragging):
                    self.__pieceOnSquare[i].showBounds()
        if self.__mouse3:
            fold = 50
            h = self.__mouse3[2] + self.__hsymbol*fold*(self.__mouse3[0] - mpos.getX())
            p = self.__mouse3[3] - fold*(self.__mouse3[1] - mpos.getY())
            self.axisCameraPitching.setH(h)
            if p < 0 and p > -90:
                self.axisCameraPitching.setP(p)
            h_symbol =  1 if mpos.getY() <=0 else -1
            if h_symbol!=self.__hsymbol:
                self.__mouse3 = (mpos.getX(),mpos.getY(),self.axisCameraPitching.getH(),self.axisCameraPitching.getP())
                self.__hsymbol = h_symbol
        return direct.task.Task.cont

    def __defaultChessboard(self, chessboardTopCenter, pieceRoot):
        squareRoot = chessboardTopCenter.attachNewNode("squareRoot")

        white = (1, 1, 1, 1)
        black = (0.3, 0.3, 0.3, 1)
        colors = {1: white, 0: black}

        # For each square
        squares = []
        for i in range(64):
            row = i // 8
            color = colors[(row + i) % 2]
            square = self.loader.loadModel("models/square")
            square.setColor(color)
            square.reparentTo(squareRoot)
            square.setPos(MyChessboard.__squarePos(i))
            square.find("**/polygon").node().setIntoCollideMask(panda3d.core.BitMask32.bit(1))
            square.find("**/polygon").node().setTag('square', str(i))
        self.__marksAlwaysVisible = True  
        self.__checkButton = direct.gui.DirectCheckButton.DirectCheckButton(
            pos=(1.0, 0.0, 0.85),
            scale=0.03,
            text_scale=2,
            text='Show Moves',
            borderWidth=(0.5, 0.5),
            pad=(0.5, 1),
            boxPlacement='left',
            boxImage=('models/maps/checkbox_unchecked.png', 'models/maps/checkbox_checked.png', None),
            indicatorValue=self.__marksAlwaysVisible,
            command=self.toggleChessboardMarksBehavior
        )
        self.__validMarks = set()
        mark = self.loader.loadModel("models/square")
        mark.setTransparency(panda3d.core.TransparencyAttrib.MDual)
        marks = []
        for i in range(64):
            pos = MyChessboard.__squarePos(i)
            holder = chessboardTopCenter.attachNewNode("markInstanceHolder")
            mark.instanceTo(holder)
            pos.setZ(pos.getZ() + 1E-2)  
            holder.setPos(pos)
            holder.setColor(MarkColor['UNACCEPTABLE_MOVE'])
            holder.setScale(0.75)
            holder.hide()
            marks.append(holder)
            square = pieceRoot.attachNewNode("square")
            square.setPos(pos)
            squares.append(square)  

        return {'squares': squares, 'marks': marks, 'squareRoot': squareRoot}

    def __hasPieceOnSquare(self, i):
        """检查编号为 i 的方格上当前是否有棋子

        :param i: 格子编号, 有效范围: 0<=i<64
        :rtype : bool
        """
        assert 0 <= i < 64
        return bool(self.__pieceOnSquare[i])

    def onMouse1Pressed(self):

        if not self.__pointingTo: 
            if not self.__dragging:
                return

            i = self.__dragging - 1
            self.__pieceOnSquare[i].reparentTo(self.__chessboard['squares'][i]) 
            self.__pieceOnSquare[i].setX(0)
            self.__pieceOnSquare[i].setY(0)
            self.__pieceOnSquare[i].stop('hovering')
            self.__pieceOnSquare[i].play('landing')
            self.__dragging = False
            if self.__marksAlwaysVisible:
                marks = self.__chessboard['marks']
                for i in self.__validMarks:
                    marks[i].hide()
            return
        if not self.__dragging:
            if self.__hasPieceOnSquare(self.__pointingTo - 1): 
                self.__dragging = self.__pointingTo
                i = self.__dragging - 1
                squarePos = self.__chessboard['squares'][i].getPos()
                x = squarePos.getX() - self.__finger.getX()
                y = squarePos.getY() - self.__finger.getY()
                self.__pieceOnSquare[i].reparentTo(self.__finger)  
                self.__pieceOnSquare[i].setPos(x, y, 0)
                self.__pieceOnSquare[i].play('hovering')
                destinations = mark_indexes_from_coordinates(
                    self.arena.retrieve_valid_moves_of_unit(unit_id=self.__pidOnSquare[i])
                )
                current = {i}
                previous = self.__validMarks
                self.__validMarks = set(destinations) | current
                marks = self.__chessboard['marks']
                marks[i].setColor(MarkColor['STARTING_POINT'])
                for tmp in previous - self.__validMarks:
                    marks[tmp].setColor(MarkColor['UNACCEPTABLE_MOVE'])
                for tmp in destinations:
                    marks[tmp].setColor(MarkColor['ACCEPTABLE_MOVE'])
                if self.__marksAlwaysVisible:
                    for tmp in self.__validMarks:
                        marks[tmp].show()
            return

        if self.__pointingTo != self.__dragging:
            i2 = self.__pointingTo - 1
            if self.__hasPieceOnSquare(i2):
                piece2_id = self.__pidOnSquare[i2]
                owner2 = self.arena.owner_of_unit(piece2_id)
                i1 = self.__dragging - 1
                piece1_id = self.__pidOnSquare[i1]
                owner1 = self.arena.owner_of_unit(piece1_id)
                if owner2 == owner1:  
                    k1 = self.__dragging - 1
                    self.__pieceOnSquare[k1].reparentTo(self.__chessboard['squares'][k1])  
                    self.__pieceOnSquare[k1].setX(0)
                    self.__pieceOnSquare[k1].setY(0)
                    self.__pieceOnSquare[k1].stop('hovering')
                    self.__pieceOnSquare[k1].play('landing')
                    if self.__marksAlwaysVisible:
                        marks = self.__chessboard['marks']
                        for i in self.__validMarks:
                            marks[i].hide()
                    self.__dragging = self.__pointingTo
                    k2 = self.__dragging - 1
                    squarePos = self.__chessboard['squares'][k2].getPos()
                    x = squarePos.getX() - self.__finger.getX()
                    y = squarePos.getY() - self.__finger.getY()
                    self.__pieceOnSquare[k2].setPos(x, y, 0)
                    self.__pieceOnSquare[k2].play('hovering')
                    destinations = mark_indexes_from_coordinates(
                        self.arena.retrieve_valid_moves_of_unit(unit_id=self.__pidOnSquare[k2])
                    )
                    current = {k2}
                    previous = self.__validMarks
                    self.__validMarks = set(destinations) | current
                    marks = self.__chessboard['marks']
                    marks[k2].setColor(MarkColor['STARTING_POINT'])
                    for tmp in previous - self.__validMarks:
                        marks[tmp].setColor(MarkColor['UNACCEPTABLE_MOVE'])
                    for tmp in destinations:
                        marks[tmp].setColor(MarkColor['ACCEPTABLE_MOVE'])
                    if self.__marksAlwaysVisible:
                        for tmp in self.__validMarks:
                            marks[tmp].show()
            j = self.__dragging - 1
            self.__pieceOnSquare[j].reparentTo(self.__finger) 
            return

        k = self.__dragging - 1
        self.__pieceOnSquare[k].reparentTo(self.__chessboard['squares'][k])
        self.__pieceOnSquare[k].setX(0)
        self.__pieceOnSquare[k].setY(0)
        self.__pieceOnSquare[k].stop('hovering')
        self.__pieceOnSquare[k].play('landing')
        self.__dragging = False
        if self.__marksAlwaysVisible:
            marks = self.__chessboard['marks']
            for i in self.__validMarks:
                marks[i].hide()
        return

    def onMouse1Released(self):
    
        if not self.__pointingTo:  
            return

        if not self.__dragging: 
            return

        if self.__pointingTo != self.__dragging:
            try: 
                self.__movePiece(self.__dragging - 1, self.__pointingTo - 1)
            except IllegalMoveException:
                pass
            else:
                self.__dragging = False
                if self.__marksAlwaysVisible:
                    marks = self.__chessboard['marks']
                    for i in self.__validMarks:
                        marks[i].hide()
            return

        return

    def onMouse3Pressed(self):
        mpos = self.mouseWatcherNode.getMouse()
        self.hsymbol = 1 if mpos.getY() <=0 else -1
        self.__mouse3 = (mpos.getX(),mpos.getY(),self.axisCameraPitching.getH(),self.axisCameraPitching.getP())

    def onMouse3Released(self):
        self.__mouse3 = None

    def __isLegalMove(self, fr, to):
        pid = self.__pidOnSquare[fr]
        if not pid:
            return False
        valid_moves = self.arena.retrieve_valid_moves_of_unit(pid)
        destination = gamearena.Square(x=to % 8, y=to // 8)
        return destination in valid_moves

    def __movePiece(self, fr, to):

        if to == fr: 
            return
        elif not self.__isLegalMove(fr, to):
            raise IllegalMoveException()

        piece1 = self.__pieceOnSquare[fr]
        piece2 = self.__pieceOnSquare[to]
        self.__pieceOnSquare[to] = piece1
        self.__pieceOnSquare[fr] = None  
        pid1 = self.__pidOnSquare[fr]
        pid2 = self.__pidOnSquare[to]  
        piece1 = self.__pieces[pid1]
        square2 = self.__chessboard['squares'][to]
        piece1.reparentTo(square2)
        piece1.setX(0)
        piece1.setY(0)
        piece1.stop('hovering')
        piece1.play('landing')
        self.__pidOnSquare[to] = pid1
        self.__pidOnSquare[fr] = 0 
        if pid2:
            self.__sendToGraveyard(piece=piece2, gid=pid2)

        destination = gamearena.Square(x=to % 8, y=to // 8)
        self.arena.move_unit_to_somewhere(pid1, destination)

    def __sendToGraveyard(self, piece, gid):
        grave = self.__graveyard['graves'][gid]
        piece.reparentTo(grave)
        piece.setX(0)
        piece.setY(0)
        piece.stop('hovering')
        piece.play('landing')
        piece.hideBounds()

    def __defaultGraveyard(self):

        max_pieces = 32 
        max_graves = max_pieces
        graves = {}
        graveyard = self.render.attachNewNode("graveyard")
        for i in range(max_graves):
            grave = graveyard.attachNewNode("grave")
            grave.reparentTo(graveyard)
            x = -4.5 if i < 16 else 4.5  
            y = 0.4 * ((i % 16) - 7.5)
            grave.setPos(x, y, 0)
            grave.setScale(0.75)
            gid = i + 1
            graves[gid] = grave  # 让 graves[] 的下标 gid 从 1 开始
        return {'graves': graves, 'graveyard': graveyard}

    def __selectChessPieceModelSytle(self, path='models/default'):
        """查找载入路径 path 指定风格样式的棋子模型套件"""
        # Models:
        king = self.loader.loadModel("{}/king".format(path))
        queen = self.loader.loadModel("{}/queen".format(path))
        rook = self.loader.loadModel("{}/rook".format(path))
        knight = self.loader.loadModel("{}/knight".format(path))
        bishop = self.loader.loadModel("{}/bishop".format(path))
        pawn = self.loader.loadModel("{}/pawn".format(path))
        # Actors
        king_actor = None
        queen_actor = None
        rook_actor = None
        knight_actor = None
        bishop_actor = None
        pawn_actor = None
        # # TODO: 为棋子添加动画效果
        # # 可以用 self.__have_animations = True 或 False 进行设置
        # if self.__have_animations:
        #     import direct.actor.Actor
        #     king_actor = direct.actor.Actor.Actor("{}/king".format(style), anims=None)
        #     queen_actor = direct.actor.Actor.Actor("{}/queen".format(style), anims=None)
        #     rook_actor = direct.actor.Actor.Actor("{}/rook".format(style), anims=None)
        #     knight_actor = direct.actor.Actor.Actor("{}/knight".format(style), anims=None)
        #     bishop_actor = direct.actor.Actor.Actor("{}/bishop".format(style), anims=None)
        #     pawn_actor = direct.actor.Actor.Actor("{}/pawn".format(style), anims=None)
        return {
            'king': king,
            'queen': queen,
            'rook': rook,
            'knight': knight,
            'bishop': bishop,
            'pawn': pawn,
            'king_actor': king_actor,
            'queen_actor': queen_actor,
            'rook_actor': rook_actor,
            'knight_actor': knight_actor,
            'bishop_actor': bishop_actor,
            'pawn_actor': pawn_actor,
        }

    @staticmethod
    def __squarePos(i):
        """A handy little function for getting the proper position for a given square"""
        return panda3d.core.LPoint3((i % 8) - 3.5, (i // 8) - 3.5, 0)

    def onKeyboardPageUpPressed(self):
        delta = -14.5
        p = self.axisCameraPitching.getP() + delta
        if p + 10.0 < -90.0:  # p=-90 度时摄像机从顶端垂直向正下方俯视, 初始值 p=-45 度时向斜下方俯视
            return
        self.axisCameraPitching.setP(p)

    def onKeyboardPageDownPressed(self):
        delta = 14.5
        p = self.axisCameraPitching.getP() + delta
        if p - 10.0 > 0.0:  # p=0 度时摄像机为水平视角, 0<p<90 则代表从地平面下方向上仰视
            return
        self.axisCameraPitching.setP(p)

    def onMouseWheelRolledUpwards(self):
        scale = 1.04  # Zoom out
        y = self.camera.getY() * scale
        if math.fabs(y) > 25.0:
            return
        self.camera.setY(y)

    def onMouseWheelRolledDownwards(self):
        scale = 0.96  # Zoom in
        y = self.camera.getY() * scale
        if math.fabs(y) < 12.0:
            return
        self.camera.setY(y)

    def __makeMarksAlwaysVisible(self):
        self.__marksAlwaysVisible = True
        if self.__dragging:
            marks = self.__chessboard['marks']
            for i in self.__validMarks:
                marks[i].show()

    def __makeMarksVisibleOnlyWhenSquareIsPointed(self):
        self.__marksAlwaysVisible = False
        marks = self.__chessboard['marks']
        for i in self.__validMarks:
            marks[i].hide()

    def toggleChessboardMarksBehavior(self, isChecked):
        if isChecked:
            self.__makeMarksAlwaysVisible()
        else:
            self.__makeMarksVisibleOnlyWhenSquareIsPointed()


MarkColor = {
    'STARTING_POINT': panda3d.core.LVecBase4f(0.5, 0.5, 0.5, 0.25),
    'ACCEPTABLE_MOVE': panda3d.core.LVecBase4f(0, 1, 1, 0.75),
    'UNACCEPTABLE_MOVE': panda3d.core.LVecBase4f(1, 0, 0, 0.25),
}


def mark_indexes_from_coordinates(coordinates):
    result = []
    for (x, y) in coordinates:
        result.append(x + 8 * y)
    return tuple(result)


class CustomizedPiece(object):
    def __init__(self, node_path, mask):
        self.__np = node_path
        b = node_path.getTightBounds()
        solid = panda3d.core.CollisionBox(b[0], b[1])
        self.__cb = panda3d.core.CollisionNode('pieceCollisionBox')
        self.__cb.addSolid(solid)
        self.__cb.setIntoCollideMask(mask)
        self.__box = node_path.attachNewNode(self.__cb)

        hovering_interval = direct.interval.LerpInterval.LerpFunc(
            self._vertical_oscillating_motion,  # function to call
            duration=0.4,  # duration (in seconds)
            fromData=0,  # starting value (in radians)
            toData=math.pi,  # ending value
            # Additional information to pass to self._osllicat
            extraArgs=[self.__np, 0.25]
        )
        landing_interval = direct.interval.LerpInterval.LerpFunc(
            self._vertical_oscillating_motion,  # function to call
            duration=0.125,  # duration (in seconds)
            fromData=-math.pi,  # starting value (in radians)
            toData=0,  # ending value
            # Additional information to pass to self._osllicat
            extraArgs=[self.__np, 0.25]
        )
        self.__animations = {
            'hovering': hovering_interval,
            'landing': landing_interval,
        }

        self.pickerRay = panda3d.core.CollisionRay()
        self.pickerRay.setOrigin(0.0, 0.0, 0.0)
        self.pickerRay.setDirection(0, 0, -1)
        self.collisionNode = panda3d.core.CollisionNode('pieceCollisionNode')
        self.collisionNode.setFromCollideMask(mask)  # 注意是碰撞源(From)
        self.collisionNode.setIntoCollideMask(panda3d.core.BitMask32.allOff())
        self.collisionNode.addSolid(self.pickerRay)
        self.collisionNP = self.__np.attachNewNode(self.collisionNode)
        self.collisionNP.setPos(0, 0, 0)
        self.picker = panda3d.core.CollisionTraverser()
        self.handler = panda3d.core.CollisionHandlerQueue()
        self.picker.addCollider(self.collisionNP, self.handler)

    @staticmethod
    def _vertical_oscillating_motion(rad, piece, height):
        """垂直方向上震荡往复运动

        :param rad: 弧度值
        :param piece: 棋子对象的 NodePath
        :param height: 运动轨迹顶点高度, 数值上等于振幅的两倍
        """
        wave_amplitude = height * 0.5
        piece.setZ(wave_amplitude * (1.0 - math.cos(rad)))

    def loop(self, animName, restart=True):
        try:
            interval = self.__animations[animName]
        except KeyError:
            pass
        else:
            if restart:
                interval.loop()  # restart from the beginning
            else:
                interval.resume()  # continue from last position

    def play(self, animName, restart=True):
        try:
            interval = self.__animations[animName]
        except KeyError:
            pass
        else:
            if restart:
                interval.start()  # start play from the beginning
            else:
                interval.resume()  # continue from last position

    def stop(self, animName=None):
        if not animName:
            for interval in self.__animations.values():
                interval.finish()
            return
        try:
            interval = self.__animations[animName]
        except KeyError:
            pass
        else:
            interval.finish()

    def pause(self, animName=None):
        intervals = self.__animations.values()
        if not animName:
            for interval in intervals:
                interval.pause()
        if animName in intervals:
            interval = self.__animations[animName]
            interval.pause()

    def setPos(self, *args, **kwargs):
        self.__np.setPos(*args, **kwargs)

    def setX(self, *args, **kwargs):
        self.__np.setX(*args, **kwargs)

    def setY(self, *args, **kwargs):
        self.__np.setY(*args, **kwargs)

    def setZ(self, *args, **kwargs):
        self.__np.setZ(*args, **kwargs)

    def setTag(self, tagName, tagValue):
        self.__cb.setTag(tagName, tagValue)

    def reparentTo(self, *args, **kwargs):
        self.__np.reparentTo(*args, **kwargs)

    def showBounds(self):
        self.__box.show()

    def hideBounds(self):
        self.__box.hide()


def main():
    ambientLight = panda3d.core.AmbientLight("ambientLight")
    ambientLight.setColor((.8, .8, .8, 1))
    directionalLight = panda3d.core.DirectionalLight("directionalLight")
    directionalLight.setDirection(panda3d.core.LVector3(0, 45, -45))
    directionalLight.setColor((0.2, 0.2, 0.2, 1))

    base = MyChessboard()
    base.render.setLight(base.render.attachNewNode(ambientLight)) 
    base.render.setLight(base.render.attachNewNode(directionalLight)) 
    base.run()


if '__main__' == __name__:
    main()
