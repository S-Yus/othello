import src.ui as ui
from js import setTimeout, clearTimeout
from pyodide.ffi import create_proxy
from src.game import init_board, legal_moves, apply_move, is_game_over, score, BLACK, WHITE
from src.ai import choose_move

AI_DELAY_MS = 600

board = init_board()
player = BLACK
_thinking = False
_ai_timer_id = None

def _has_move(b, p): return len(legal_moves(b, p)) > 0

def _ai_to_move() -> bool:
    mode = (ui.get_mode() or "PVP").upper()
    return (mode == "AI_WHITE" and player == WHITE) or (mode == "AI_BLACK" and player == BLACK)

def cancel_ai_timer():
    global _ai_timer_id, _thinking
    if _ai_timer_id is not None:
        clearTimeout(_ai_timer_id)
        _ai_timer_id = None
    _thinking = False

def refresh():
    legal = set(legal_moves(board, player))
    if hasattr(ui, "set_pass_enabled"):
        ui.set_pass_enabled(len(legal) == 0)

    b, w = score(board)
    if is_game_over(board):
        ui.set_status(f"Game Over — Black {b} : White {w}")
    else:
        turn = "Black" if player == BLACK else "White"
        thinking_note = " — Thinking..." if _ai_to_move() and _thinking else ""
        ui.set_status(f"Turn: {turn} — Black {b} : White {w}{thinking_note}")

    ui.render_board(board, legal, on_cell_click)

    if not is_game_over(board) and _ai_to_move() and not _thinking:
        ai_take_turn_after(AI_DELAY_MS)

def on_cell_click(r, c):
    global board, player
    if is_game_over(board) or _ai_to_move() or _thinking:
        return
    newb = apply_move(board, r, c, player)
    if newb is not board:
        board = newb
        player = -player
        if not _has_move(board, player) and not is_game_over(board):
            player = -player
    refresh()

def on_reset():
    global board, player
    cancel_ai_timer()
    board = init_board()
    player = BLACK
    refresh()

def on_pass():
    global player
    if not _has_move(board, player):
        player = -player
    refresh()

def ai_take_turn_after(delay_ms: int):
    global _thinking, _ai_timer_id
    _thinking = True
    refresh()
    def _run(_=None):
        ai_take_turn_sync()
    _ai_timer_id = setTimeout(create_proxy(_run), delay_ms)

def ai_take_turn_sync():
    global board, player, _thinking, _ai_timer_id
    _ai_timer_id = None
    depth = getattr(ui, "get_depth", lambda: 3)()
    mv = choose_move(board, player, depth=depth)
    if mv is None:
        player = -player
    else:
        board = apply_move(board, mv[0], mv[1], player)
        player = -player
        if not _has_move(board, player) and not is_game_over(board):
            player = -player
    _thinking = False
    refresh()

def on_mode_change():
    cancel_ai_timer()
    refresh()
def on_depth_change():
    cancel_ai_timer()
    refresh()

ui.bind_button("resetBtn", on_reset)
ui.bind_button("passBtn", on_pass)
try:
    ui.bind_change("modeSelect", on_mode_change)
    ui.bind_change("depthSelect", on_depth_change)
except Exception:
    pass

refresh()
