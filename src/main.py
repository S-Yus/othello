# src/main.py
from js import console
from src.game import Game
from src.ui import UI
import asyncio

def boot():
    try:
        game = Game(mode="AI_WHITE")
        ui = UI(game)
        ui.render()
        asyncio.ensure_future(ui._step_ai_loop(force=True))
        console.log("[Othello] Boot OK")
    except Exception as e:
        console.error("[Othello] Boot FAILED:", e)
        # 例外の詳細（スタックトレース）も吐く
        import traceback
        console.error(traceback.format_exc())

boot()
