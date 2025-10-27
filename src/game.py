import numpy as np
from typing import List, Tuple, Optional, Dict, Any

EMPTY = 0
BLACK = 1
WHITE = -1

DIRS = [(-1,-1), (0,-1), (1,-1),
        (-1, 0),         (1, 0),
        (-1, 1), (0, 1), (1, 1)]

Coord = Tuple[int, int]

def onboard(x:int, y:int)->bool:
    return 0 <= x < 8 and 0 <= y < 8

def coord_to_notation(x:int,y:int)->str:
    return f"{chr(ord('A')+x)}{y+1}"

def notation_to_coord(s:str)->Coord:
    s = s.strip().upper()
    x = ord(s[0]) - ord('A')
    y = int(s[1]) - 1
    return (x,y)

class Game:
    def __init__(self, mode: str = "AI_WHITE"):
        self.mode: str = mode
        self.board: np.ndarray = self._init_board()
        self.current_player: int = BLACK
        self.pass_streak: int = 0
        self.history: List[Dict[str,Any]] = []
        self.future: List[Dict[str,Any]] = []
        self.move_history: List[str] = []
        self.last_move: Optional[Coord] = None

    def _init_board(self) -> np.ndarray:
        b = np.zeros((8,8), dtype=np.int8)
        b[3,3] = WHITE; b[4,4] = WHITE
        b[3,4] = BLACK; b[4,3] = BLACK
        return b

    def reset(self):
        self.board = self._init_board()
        self.current_player = BLACK
        self.pass_streak = 0
        self.history.clear()
        self.future.clear()
        self.move_history.clear()
        self.last_move = None

    def snapshot(self) -> Dict[str,Any]:
        return {
            "board": self.board.copy(),
            "current_player": self.current_player,
            "mode": self.mode,
            "pass_streak": self.pass_streak,
            "move_history": list(self.move_history),
            "last_move": None if self.last_move is None else tuple(self.last_move),
        }

    def restore(self, snap: Dict[str,Any]):
        self.board = snap["board"].copy()
        self.current_player = snap["current_player"]
        self.mode = snap["mode"]
        self.pass_streak = snap["pass_streak"]
        self.move_history = list(snap["move_history"])
        self.last_move = None if snap["last_move"] is None else tuple(snap["last_move"])

    def can_undo(self)->bool: return len(self.history) > 0
    def can_redo(self)->bool: return len(self.future) > 0

    def undo(self, steps:int=1)->bool:
        ok = False
        for _ in range(steps):
            if not self.history: break
            curr = self.snapshot()
            prev = self.history.pop()
            self.future.append(curr)
            self.restore(prev)
            ok = True
        return ok

    def redo(self, steps:int=1)->bool:
        ok = False
        for _ in range(steps):
            if not self.future: break
            curr = self.snapshot()
            nxt = self.future.pop()
            self.history.append(curr)
            self.restore(nxt)
            ok = True
        return ok

    @staticmethod
    def legal_moves(board: np.ndarray, player: int) -> List[Coord]:
        opp = -player
        moves: List[Coord] = []
        for y in range(8):
            for x in range(8):
                if board[y,x] != EMPTY: continue
                for dx,dy in DIRS:
                    nx,ny = x+dx, y+dy
                    seen = False
                    while onboard(nx,ny) and board[ny,nx] == opp:
                        seen = True; nx += dx; ny += dy
                    if seen and onboard(nx,ny) and board[ny,nx] == player:
                        moves.append((x,y))
                        break
        return moves

    def get_legal_moves(self)->List[Coord]:
        return Game.legal_moves(self.board, self.current_player)

    @staticmethod
    def apply_move(board: np.ndarray, x:int, y:int, player:int) -> np.ndarray:
        out = board.copy()
        out[y,x] = player
        opp = -player
        for dx,dy in DIRS:
            nx,ny = x+dx, y+dy
            flips = []
            while onboard(nx,ny) and out[ny,nx] == opp:
                flips.append((nx,ny)); nx += dx; ny += dy
            if flips and onboard(nx,ny) and out[ny,nx] == player:
                for fx,fy in flips:
                    out[fy,fx] = player
        return out

    def make_move(self, x:int, y:int) -> bool:
        moves = self.get_legal_moves()
        if (x,y) not in moves: return False
        self.history.append(self.snapshot()); self.future.clear()
        self.board = Game.apply_move(self.board, x, y, self.current_player)
        self.last_move = (x,y)
        self.move_history.append(coord_to_notation(x,y))
        self.current_player *= -1
        self.pass_streak = 0
        return True

    def pass_turn(self) -> bool:
        """合法手が無いときだけパスを許可。成功時 True を返す。"""
        if self.get_legal_moves():
            return False  #打てるならパス不可
        self.history.append(self.snapshot()); self.future.clear()
        self.move_history.append("pass")
        self.current_player *= -1
        self.pass_streak += 1
        return True

    def is_game_over(self)->bool:
        # 盤が埋まった
        if (self.board == EMPTY).sum() == 0:
            return True
        # 双方打てない
        if len(Game.legal_moves(self.board, BLACK)) == 0 and len(Game.legal_moves(self.board, WHITE)) == 0:
            return True
        return False

    def score(self)->Dict[str,int]:
        b = int((self.board == BLACK).sum())
        w = int((self.board == WHITE).sum())
        return {"black": b, "white": w}

    def to_dict(self)->Dict[str,Any]:
        return {
            "mode": self.mode,
            "current_player": self.current_player,
            "pass_streak": self.pass_streak,
            "board": self.board.astype(int).tolist(),
            "move_history": list(self.move_history),
            "last_move": None if self.last_move is None else list(self.last_move),
        }

    def load_dict(self, d:Dict[str,Any]):
        self.mode = d.get("mode", self.mode)
        self.current_player = int(d.get("current_player", self.current_player))
        self.pass_streak = int(d.get("pass_streak", 0))
        self.board = np.array(d["board"], dtype=np.int8)
        self.move_history = list(d.get("move_history", []))
        lm = d.get("last_move", None)
        self.last_move = None if lm is None else (int(lm[0]), int(lm[1]))
        self.history.clear(); self.future.clear()
