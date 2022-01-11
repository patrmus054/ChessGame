# coding=utf-8
import collections

Vector = collections.namedtuple('Vector', ['dx', 'dy'])

Square = collections.namedtuple('Square', ['x', 'y'])


class Unit(object):
    def __init__(self, owner):
        self.owner = owner  
        self.has_been_moved = None  


class GameArena:
    

    class PlayerID(int):
        pass

    class UnitID(int):
        pass

    def __init__(self, width, ranks):
        
        self.__unit_info_list = []  # 按单位的编码顺序存储所有战斗单位的信息(其中并不包括该单位所在位置), 初始状态为空列表, 通过编码查找. 单位死亡后仍然保留记录
        # 二维数组共 width*ranks 个格子, 记录每个空格被哪一个棋子占领, 全部初始化置零表示所有格子均无人占领:
        self.__battlefield = [[self.UnitID(0)] * width for y in range(ranks)]

    @property
    def size(self):
        ymax = len(self.__battlefield)
        xmax = len(self.__battlefield[0])
        return xmax, ymax

    def new_unit_recruited_by_player(self, player_id, square, unit_type):
        unit = unit_type(owner=player_id)
        self.__unit_info_list.append(unit)
        unit_id = self.UnitID(len(self.__unit_info_list))
        unit.has_been_moved = False
        if square:
            x, y = square[0], square[1]
            xmax, ymax = self.size
            if x < 0 or y < 0 or x >= xmax or y >= ymax:
                raise ValueError('invalid square:{}'.format(square))
            self.__battlefield[y][x] = unit_id
        return unit_id

    def owner_of_unit(self, unit_id):
        if not self.is_valid_unit_id(unit_id):
            raise ValueError('unit_id:{} not exists'.format(unit_id))
        return self.__unit_info_list[unit_id - 1].owner

    def __place_unit_on_square(self, unit_id, square):
        x, y = square[0], square[1]
        try:
            square_before_move = self.find_square_from_unit_id(unit_id)
        except ValueError:
            pass
        else: 
            self.__battlefield[square_before_move.y][square_before_move.x] = self.UnitID(0)
     
        self.__battlefield[y][x] = unit_id
        
        unit = self.__unit_info_list[unit_id-1]
        if isinstance(unit,AbstractPawnUnit):
            unit.check_bottom(y)

    def move_unit_to_somewhere(self, unit_id, square):
        
        if not self.is_valid_unit_id(unit_id):
            raise ValueError('unit_id:{} does not exist'.format(unit_id))
        x, y = square[0], square[1]
        xmax, ymax = self.size
        if x < 0 or y < 0 or x >= xmax or y >= ymax:
            raise ValueError('invalid square:{}'.format(square))
        self.__place_unit_on_square(unit_id, square)
        self.__unit_info_list[unit_id - 1].has_been_moved = True

    def is_valid_unit_id(self, unit_id):
        
        return 1 <= unit_id <= len(self.__unit_info_list)

    def retrieve_valid_moves_of_unit(self, unit_id):
        
        result = {}
        if not self.is_valid_unit_id(unit_id):
            return result
        square = self.find_square_from_unit_id(unit_id)  # 找不到则会向上传递 ValueError 异常
        unit = self.__unit_info_list[unit_id - 1]
        return unit.retrieve_valid_moves(starting_square=square, snapshot=self.__take_snapshot())

    def find_square_from_unit_id(self, unit_id):
        
        if not self.is_valid_unit_id(unit_id):
            raise ValueError('Error: invalid unit_id:{}'.format(unit_id))
        for y in range(len(self.__battlefield)):
            rank = self.__battlefield[y]
            for x in range(len(rank)):
                if unit_id == rank[x]:
                    return Square(x, y)
        raise ValueError('Note: unit_id:{} is not on chessboard'.format(unit_id))

    def is_occupied_square(self, square):
        x, y = square[0], square[1]
        xmax, ymax = self.size
        if x < 0 or y < 0 or x >= xmax or y >= ymax:
            return False
        return self.__battlefield[y][x] > 0

    def __take_snapshot(self):
        builder = SnapshotBuilder(self.size)
        for y in range(len(self.__battlefield)):
            rank = self.__battlefield[y]
            for x in range(len(rank)):
                unit_id = rank[x]
                if unit_id > 0:
                    unit = self.__unit_info_list[unit_id - 1]
                else:
                    unit = None
                builder.set_node(x, y, unit_id, unit_instance=unit)
        return builder.snapshot


class Snapshot(dict):
    xmax = 0
    ymax = 0

    def get_node(self, x, y):
        try:
            return self[Square(x, y)]
        except KeyError:
            if 0 <= x < self.xmax and 0 <= y < self.ymax:
                return Snapshot.Node(unit_id=0, unit_instance=None)
            # 否则上报一个 ValueError 异常:
            raise ValueError('Error: x,y: get_node(x={},y={})'.format(x, y))

    class Node:
        def __init__(self, unit_id, unit_instance=None):
            self.unit_id = unit_id
            self.unit = unit_instance


class SnapshotBuilder:
    def __init__(self, size):
        self.__xmax, self.__ymax = size[0], size[1]
        self.__nodes = {}

    @property
    def snapshot(self):
        s = Snapshot(self.__nodes.items())
        s.xmax = self.__xmax
        s.ymax = self.__ymax
        return s

    def set_node(self, x, y, unit_id, unit_instance):
        if 0 <= x < self.__xmax and 0 <= y < self.__ymax:
            self.__nodes[Square(x, y)] = Snapshot.Node(unit_id, unit_instance)
        else:
            raise ValueError('Error: 坐标越界: set_node(x={},y={})'.format(x, y))


import abc


class AbstractPawnUnit(Unit):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def pawn_charge_direction(self):
        return Vector(0, 0)

    def __init__(self, owner):
        
        super(AbstractPawnUnit, self).__init__(owner)
        self.has_been_moved = False  # 是否被移动过(兵第一次移动时可以进行冲锋走两格,之后只能沿棋盘纵列每步走一格)
        self.has_been_queen = False

    def retrieve_valid_moves(self, starting_square, snapshot):
        
        if self.has_been_queen:
            return self.retrieve_valid_moves_queen(starting_square, snapshot)
        result = []

        dx, dy = self.pawn_charge_direction
        x, y = starting_square.x + dx, starting_square.y + dy
        max_steps = 1
        if not self.has_been_moved:
            max_steps = 2
        step = 1
        squares = []
        while step <= max_steps:
            step += 1
            if y < 0 or y >= snapshot.ymax:
                break  
            other_unit_id = snapshot.get_node(x, y).unit_id
            if not other_unit_id:
                squares.append(Square(x, y))
                y += dy
        result += squares


        dy = self.pawn_charge_direction.dy
        squares = []
        for x, y in self.retrieve_squares_within_shooting_range(starting_square, snapshot):
            node = snapshot.get_node(x, y)
            if not node.unit_id:
                continue  
            unit = node.unit
            if unit.owner == self.owner:
                continue 
            squares.append(Square(x, y))
        result += squares
        return tuple(result)

    def retrieve_valid_moves_queen(self, starting_square, snapshot):
        squares = []
        for x, y in self.retrieve_squares_within_shooting_range_queen(starting_square, snapshot):
            node = snapshot.get_node(x, y)
            if not node.unit_id or node.unit.owner != self.owner:
                squares.append(Square(x, y))
        return tuple(squares)

    def retrieve_squares_within_shooting_range(self, starting_square, snapshot):
        
        result = []
        dy = self.pawn_charge_direction.dy
        for dx in {-1, 1}:
            x, y = starting_square.x + dx, starting_square.y + dy
            if x < 0 or x >= snapshot.xmax or y < 0 or y >= snapshot.ymax:
                continue 
            result.append(Square(x, y))
        return tuple(result)

    def retrieve_squares_within_shooting_range_queen(self, starting_square, snapshot):
        
        result = []
        for dx, dy in self.directions:  
            squares = []
            step_count = 1
            x, y = starting_square[0] + dx, starting_square[1] + dy
            while step_count <= self.limited_move_range if self.limited_move_range > 0 else True:
                step_count += 1
                if x < 0 or x >= snapshot.xmax or y < 0 or y >= snapshot.ymax:
                    break
                node = snapshot.get_node(x, y)
                if node.unit_id > 0:
                    squares.append(Square(x, y))
                    break  
                squares.append(Square(x, y))
                x, y = x + dx, y + dy
            result += squares
        return tuple(result)

    def check_bottom(self,y):
        t = self.pawn_charge_direction.dy,y
        if t == (1,7) or t == (-1,0):
            self.has_been_queen=True
            self.directions = \
                [Vector(1, 0), Vector(1, 1), Vector(0, 1), Vector(-1, 1),
                 Vector(-1, 0), Vector(-1, -1), Vector(0, -1), Vector(1, -1)]
            self.limited_move_range = 0  # 0 for no limit

class WhitePawnUnit(AbstractPawnUnit):
    @property
    def pawn_charge_direction(self):
        return Vector(0, 1)


class BlackPawnUnit(AbstractPawnUnit):
    @property
    def pawn_charge_direction(self):
        return Vector(0, -1)


class StraightMovingAndAttackingUnit(Unit):

    def __init__(self, owner):
        super(StraightMovingAndAttackingUnit, self).__init__(owner)
        self.directions = [] 
        self.limited_move_range = 0  
    def retrieve_valid_moves(self, starting_square, snapshot):
        squares = []
        for x, y in self.retrieve_squares_within_shooting_range(starting_square, snapshot):
            node = snapshot.get_node(x, y)
            if not node.unit_id or node.unit.owner != self.owner:
                squares.append(Square(x, y))
        return tuple(squares)

    def retrieve_squares_within_shooting_range(self, starting_square, snapshot):
        result = []
        for dx, dy in self.directions:  
            squares = []
            step_count = 1
            x, y = starting_square[0] + dx, starting_square[1] + dy
            while step_count <= self.limited_move_range if self.limited_move_range > 0 else True:
                step_count += 1
                if x < 0 or x >= snapshot.xmax or y < 0 or y >= snapshot.ymax:
                    break
                node = snapshot.get_node(x, y)
                if node.unit_id > 0:
                    squares.append(Square(x, y))
                    break  
                squares.append(Square(x, y))
                x, y = x + dx, y + dy
            result += squares
        return tuple(result)


class RookUnit(StraightMovingAndAttackingUnit):
   

    def __init__(self, owner):
        super(RookUnit, self).__init__(owner)
        self.directions = [Vector(1, 0), Vector(0, 1), Vector(-1, 0), Vector(0, -1)] 
        self.limited_move_range = 0 

    def retrieve_valid_moves(self, starting_square, snapshot):
        
        return super(RookUnit, self).retrieve_valid_moves(starting_square, snapshot)


class BishopUnit(StraightMovingAndAttackingUnit):
    def __init__(self, owner):
        super(BishopUnit, self).__init__(owner)
        self.directions = [Vector(1, 1), Vector(-1, 1), Vector(-1, -1), Vector(1, -1)]  
        self.limited_move_range = 0  


class QueenUnit(StraightMovingAndAttackingUnit):

    def __init__(self, owner):
        super(QueenUnit, self).__init__(owner)
        self.directions = \
            [Vector(1, 0), Vector(1, 1), Vector(0, 1), Vector(-1, 1),
             Vector(-1, 0), Vector(-1, -1), Vector(0, -1), Vector(1, -1)]
        self.limited_move_range = 0  

class KingUnit(StraightMovingAndAttackingUnit):

    def __init__(self, owner):
        super(KingUnit, self).__init__(owner)
        self.directions = \
            [Vector(1, 0), Vector(1, 1), Vector(0, 1), Vector(-1, 1),
             Vector(-1, 0), Vector(-1, -1), Vector(0, -1), Vector(1, -1)]
        self.limited_move_range = 1  

    def retrieve_valid_moves(self, starting_square, snapshot):
        regular_moves = super(KingUnit, self).retrieve_valid_moves(starting_square, snapshot)
        result = set(regular_moves)
        del snapshot[starting_square]
        for square, node in snapshot.items():
            if node.unit_id and node.unit.owner != self.owner:
                dangerous_squares = node.unit.retrieve_squares_within_shooting_range(square, snapshot)
                result -= set(dangerous_squares)
        return tuple(result)


class KnightUnit(StraightMovingAndAttackingUnit):
    def __init__(self, owner):
        super(KnightUnit, self).__init__(owner)
        self.directions = \
            [Vector(2, 1), Vector(1, 2), Vector(-1, 2), Vector(-2, 1),
             Vector(-2, -1), Vector(-1, -2), Vector(1, -2), Vector(2, -1)]
        self.limited_move_range = 1


def do_self_test():
    import sys
    log = sys.stdout
    log.write('Module:{}\n'.format(__name__))
    arena = GameArena(width=8, ranks=8)
    white = GameArena.PlayerID(1)
    black = GameArena.PlayerID(2)
    white_pawns = []
    black_pawns = []
    for x in range(8):
        unit_id = arena.new_unit_recruited_by_player(
            player_id=white,
            square=Square(x, 1),
            unit_type=WhitePawnUnit
        )
        white_pawns.append(unit_id)
        unit_id = arena.new_unit_recruited_by_player(
            player_id=black,
            square=Square(x, 6),
            unit_type=BlackPawnUnit)
        black_pawns.append(unit_id)
    m = arena.retrieve_valid_moves_of_unit(white_pawns[0])
    print(m)
    selected_destination = m[1]
    arena.move_unit_to_somewhere(white_pawns[0], selected_destination)
    white_rook = arena.new_unit_recruited_by_player(white, Square(0, 0), RookUnit)
    m = arena.retrieve_valid_moves_of_unit(white_rook)
    print(m)


if '__main__' == __name__:
    do_self_test()
    pass
