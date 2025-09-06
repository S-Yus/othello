import time, math
import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from .game import Game, BLACK, WHITE, EMPTY

# 位置評価（よく使われる盤面重み・微調整）
W = np.array([
    [120,-20, 20,  5,  5, 20,-20,120],
    [-20,-40,-5, -5, -5, -5,-40,-20],
    [ 20, -5, 15,  3,  3, 15, -5, 20],
    [  5, -5,  3,  3,  3,  3, -5,  5],
    [  5, -5,  3,  3,  3,  3, -5,  5],
    [ 20, -5, 15,  3,  3, 15, -5, 20],
    [-20,-40,-5, -5, -5, -5,-40,-20],
    [120,-20, 20,  5,  5, 20,-20,120],
], dtype=np.int16)

CORNERS = {(0,0),(7,0),(0,7),(7,7)}
ADJ_CORNERS = {(1,0),(0,1),(6,0),(7,1),(0,6),(1,7),(6,7),(7,6)}

# トランスポジションテーブル
TT: Dict[Any, Dict[str,Any]] = {}

def reset_tt():
    TT.clear()

def board_key(board: np.ndarray, player: int) -> Any:
    # 簡易ハッシュ（ラン変だが同一実行内でOK）
    return (player, board.tobytes())

def stable_frontier_penalty(board: np.ndarray, player:int)->int:
    """空白に接する石（frontier）を数え、少し減点。"""
    opp = -player
    frontier_p = frontier_o = 0
    for y in range(8):
        for x in range(8):
            v = board[y,x]
            if v == EMPTY: continue
            # 空白隣接？
            emptyn = False
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                nx,ny = x+dx,y+dy
                if 0<=nx<8 and 0<=ny<8 and board[ny,nx]==EMPTY:
                    emptyn = True; break
            if emptyn:
                if v == player: frontier_p += 1
                elif v == opp: frontier_o += 1
    return frontier_o - frontier_p  # 相対（相手-自分）→自分視点で減点

def evaluate(board: np.ndarray, player: int) -> float:
    """自分視点の評価値（高いほど自分有利）"""
    opp = -player
    empties = (board == EMPTY).sum()

    # 位置重み
    posv = int((board * W).sum()) * (1 if player==BLACK else -1)

    # 角
    corner = 0
    for (x,y) in CORNERS:
        if board[y,x]==player: corner += 1
        elif board[y,x]==opp:  corner -= 1

    # 角隣（危険）
    danger = 0.0
    for (x,y) in ADJ_CORNERS:
        if board[y,x]==player: danger -= 0.5
        elif board[y,x]==opp:  danger += 0.5

    # 可動性
    mob = len(Game.legal_moves(board, player)) - len(Game.legal_moves(board, opp))

    # フロンティア（空白隣接石）
    frontier = stable_frontier_penalty(board, player)

    # ゲーム進行度で重みを変える（序盤は位置/可動性、中盤は可動性/フロンティア、終盤は石差）
    phase = (64 - empties) / 64.0
    early = max(0.0, 1.0 - 2.0*phase)
    mid   = max(0.0, 2.0*phase*(1.0 - phase))
    late  = max(0.0, 2.0*phase - 1.0)

    val = ( early * (0.9*posv + 3.0*mob + 8.0*corner + 1.0*danger)
          + mid   * (0.6*posv + 4.0*mob + 8.0*corner - 1.2*frontier)
          + late  * ( (board.sum()) * (1 if player==BLACK else -1) * 2.0 + 10.0*corner )
          )
    return float(val)

def order_moves(moves: List[Tuple[int,int]])->List[Tuple[int,int]]:
    # 角最優先、X/Squaresは後回し（重み付けソート）
    def score(m):
        x,y = m
        if (x,y) in CORNERS: return -100
        if (x,y) in ADJ_CORNERS: return 20
        # 良さげ中央寄り
        cx,cy = abs(3.5-x), abs(3.5-y)
        return cx+cy
    return sorted(moves, key=score)

def search(board: np.ndarray, player:int, depth:int,
           alpha:float, beta:float,
           start:float, time_limit:Optional[float],
           out_best: Dict[str,Any]) -> float:
    """Negamax with alpha-beta + TT。時間制限があれば途中打ち切り。"""
    if time_limit is not None and (time.monotonic() - start) > time_limit:
        raise TimeoutError

    # TT lookup
    key = board_key(board, player)
    entry = TT.get(key)
    if entry and entry["depth"] >= depth:
        flag = entry["flag"]; val = entry["value"]
        if flag == "EXACT": return val
        if flag == "LOWER" and val > alpha: alpha = val
        elif flag == "UPPER" and val < beta: beta = val
        if alpha >= beta: return val

    # 終端
    legal = Game.legal_moves(board, player)
    opp_moves = None
    if depth <= 0 or (not legal and not Game.legal_moves(board, -player)):
        return evaluate(board, player)

    if not legal:
        # パス
        val = -search(board, -player, depth-1, -beta, -alpha, start, time_limit, out_best)
        TT[key] = {"value": val, "flag":"EXACT", "depth":depth, "best": None}
        return val

    best_val = -math.inf
    best_mv = None

    # move ordering
    if entry and entry.get("best"):
        mv0 = entry["best"]
        legal = [mv0] + [m for m in legal if m != mv0]
    else:
        legal = order_moves(legal)

    for (x,y) in legal:
        nb = Game.apply_move(board, x, y, player)
        v = -search(nb, -player, depth-1, -beta, -alpha, start, time_limit, out_best)
        if v > best_val:
            best_val = v; best_mv = (x,y)
        if best_val > alpha: alpha = best_val
        if alpha >= beta: break

    # TT store
    flag = "EXACT"
    if best_val <= alpha: flag = "UPPER"
    if best_val >= beta:  flag = "LOWER"
    TT[key] = {"value": best_val, "flag": flag, "depth": depth, "best": best_mv}

    # 一番上の呼び出しに最善手を返すため
    if depth == out_best.get("root_depth", -1):
        out_best["move"] = best_mv

    return best_val

def choose_move(board: np.ndarray, player:int, depth:int,
                time_limit_ms: Optional[int]=None) -> Optional[Tuple[int,int]]:
    legal = Game.legal_moves(board, player)
    if not legal: return None
    start = time.monotonic()
    out_best: Dict[str,Any] = {"move": None, "root_depth": depth}
    time_limit = None if time_limit_ms is None else (time_limit_ms/1000.0)

    # 反復深化：1..depth で深める（時間制限あれば途中で打切り）
    best = legal[0]
    try:
        for d in range(1, depth+1):
            out_best["root_depth"] = d
            val = search(board, player, d, -math.inf, math.inf, start, time_limit, out_best)
            if out_best.get("move") is not None:
                best = out_best["move"]
            if time_limit is not None and (time.monotonic() - start) > time_limit:
                break
    except TimeoutError:
        pass
    return best
