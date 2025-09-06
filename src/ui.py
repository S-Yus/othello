from js import document  # type: ignore
from pyodide.ffi import create_proxy  # type: ignore
from src.game import EMPTY, BLACK, WHITE

_CELL_PROXIES = []
_BUTTON_PROXIES = []

def _clear_cell_proxies():
    global _CELL_PROXIES
    for p in _CELL_PROXIES:
        try:
            p.destroy()
        except Exception:
            pass
    _CELL_PROXIES = []

def _add_cell_event(element, event_name, pyfunc):
    proxy = create_proxy(pyfunc)
    element.addEventListener(event_name, proxy)
    _CELL_PROXIES.append(proxy)

def _add_button_event(element, event_name, pyfunc):
    proxy = create_proxy(pyfunc)
    element.addEventListener(event_name, proxy)
    _BUTTON_PROXIES.append(proxy)

def render_board(board, legal_moves_set, on_click):
    _clear_cell_proxies()

    root = document.getElementById("board")
    root.innerHTML = ""

    for r in range(8):
        for c in range(8):
            cell = document.createElement("div")
            cell.classList.add("cell")
            if (r, c) in legal_moves_set:
                cell.classList.add("legal")

            v = int(board[r, c])
            if v != EMPTY:
                disk = document.createElement("div")
                disk.classList.add("disk", "black" if v == BLACK else "white")
                cell.appendChild(disk)

            def make_handler(rr=r, cc=c):
                def handler(evt):
                    on_click(rr, cc)
                return handler

            _add_cell_event(cell, "click", make_handler())
            root.appendChild(cell)

def set_status(text):
    document.getElementById("status").innerText = text

def bind_button(id_str, cb):
    el = document.getElementById(id_str)
    _add_button_event(el, "click", lambda evt: cb())

def bind_change(id_str, cb):
    el = document.getElementById(id_str)
    _add_button_event(el, "change", lambda evt: cb())

def set_pass_enabled(enabled: bool):
    btn = document.getElementById("passBtn")
    if btn:
        btn.disabled = (not enabled)

def get_mode() -> str:
    el = document.getElementById("modeSelect")
    return (el.value if el else "PVP").upper()


def get_depth() -> int:
    el = document.getElementById("depthSelect")
    try:
        return int(el.value)
    except Exception:
        return 2
