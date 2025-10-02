# src/main.py
from js import console
from src.game import Game
from src.ui import UI
import asyncio, traceback

def boot():
    try:
        game = Game(mode="AI_WHITE")
        ui = UI(game)
        ui.render()
        asyncio.ensure_future(ui._step_ai_loop(force=True))
        console.log("[Othello] Boot OK")
    except Exception as e:
        console.error("[Othello] Boot FAILED:", e)
        console.error(traceback.format_exc())

boot()
