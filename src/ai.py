import numpy as np
from src.game import legal_moves, apply_move, is_game_over, BLACK, WHITE, EMPTY

# 盤面の重み
W = np.array([
    [120,-20, 20,  5,  5, 20,-20,120],
    [-20,-40, -5, -5, -5, -5,-40,-20],
    [ 20, -5, 15,  3,  3, 15, -5, 20],
    [  5, -5,  3,  3,  3,  3, -5,  5],
    [  5, -5,  3,  3,  3,  3, -5,  5],
    [ 20, -5, 15,  3,  3, 15, -5, 20],
    [-20,-40, -5, -5, -5, -5,-40,-20],
    [120,-20, 20,  5,  5, 20,-20,120],
], dtype=np.int16)

CORNERS = [(0,0),(0,7),(7,0),(7,7)]

def evaluate(board: np.ndarray, player: int) -> float:
    """player 視点の評価値（大きいほど有利）"""
    empties = int(np.sum(board == EMPTY))
    # 盤面重み
    mat = int(np.sum(W * board)) * player

    # 隅
    my_corners = sum(1 for (r,c) in CORNERS if board[r,c] == player)
    opp_corners = sum(1 for (r,c) in CORNERS if board[r,c] == -player)
    corner_score = 100 * (my_corners - opp_corners)

    # 可動性（着手可能手数差）
    my_mob = len(legal_moves(board, player))
    opp_mob = len(legal_moves(board, -player))
    mobility = 5 * (my_mob - opp_mob)

    # 石差（終盤ほど比重を上げる）
    disc = (int(np.sum(board == player)) - int(np.sum(board == -player)))
    disc_w = 1 if empties > 12 else 6  # 終盤強め

    return 0.4*mat + corner_score + mobility + disc_w*disc

def _negamax(board: np.ndarray, player: int, depth: int, alpha: float, beta: float) -> float:
    if depth == 0 or is_game_over(board):
        return evaluate(board, player)

    moves = legal_moves(board, player)
    if not moves:
        # パス（深さは減らさない。手番だけ渡す）
        return -_negamax(board, -player, depth, -beta, -alpha)

    best = -1e18
    # 簡易ムーブ順序（隅優先）
    moves.sort(key=lambda rc: (rc in CORNERS), reverse=True)

    for r, c in moves:
        nb = apply_move(board, r, c, player)
        val = -_negamax(nb, -player, depth - 1, -beta, -alpha)
        if val > best:
            best = val
        if val > alpha:
            alpha = val
        if alpha >= beta:
            break
    return best

def choose_move(board: np.ndarray, player: int, depth: int = 3):
    """最善手を一手返す。手が無ければ None"""
    moves = legal_moves(board, player)
    if not moves:
        return None
    best_val = -1e18
    best_move = moves[0]
    alpha, beta = -1e18, 1e18

    # 同じ順序付け
    moves.sort(key=lambda rc: (rc in CORNERS), reverse=True)

    for r, c in moves:
        nb = apply_move(board, r, c, player)
        val = -_negamax(nb, -player, depth - 1, -beta, -alpha)
        if val > best_val:
            best_val = val
            best_move = (r, c)
        if val > alpha:
            alpha = val
    return best_move
