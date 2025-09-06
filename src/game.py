import numpy as np

EMPTY, BLACK, WHITE = 0, 1, -1
DIRS = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]

def init_board():
    b = np.zeros((8,8), dtype=np.int8)
    b[3,3] = WHITE; b[3,4] = BLACK
    b[4,3] = BLACK; b[4,4] = WHITE
    return b

def in_bounds(r, c): return 0 <= r < 8 and 0 <= c < 8

def legal_moves(board, player):
    moves = []
    for r in range(8):
        for c in range(8):
            if board[r,c] != EMPTY: continue
            if any(_captures_dir(board, r, c, player, dr, dc) for dr, dc in DIRS):
                moves.append((r,c))
    return moves

def _captures_dir(board, r, c, player, dr, dc):
    i, j = r + dr, c + dc
    seen_opp = False
    while in_bounds(i,j) and board[i,j] == -player:
        seen_opp = True
        i += dr; j += dc
    return seen_opp and in_bounds(i,j) and board[i,j] == player

def apply_move(board, r, c, player):
    if board[r,c] != EMPTY: return board
    flips = []
    for dr, dc in DIRS:
        line = []
        i, j = r + dr, c + dc
        while in_bounds(i,j) and board[i,j] == -player:
            line.append((i,j))
            i += dr; j += dc
        if line and in_bounds(i,j) and board[i,j] == player:
            flips.extend(line)
    if not flips:
        return board
    nb = board.copy()
    nb[r,c] = player
    for i,j in flips: nb[i,j] = player
    return nb

def is_game_over(board):
    return len(legal_moves(board, BLACK)) == 0 and len(legal_moves(board, WHITE)) == 0

def score(board):
    black = int(np.sum(board == BLACK))
    white = int(np.sum(board == WHITE))
    return black, white
