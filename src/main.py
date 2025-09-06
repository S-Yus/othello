from .game import Game
from .ui import UI

game = Game(mode="AI_WHITE")  # 初期モード
ui = UI(game)
ui.render()

# 初手がAIなら自動開始
import asyncio
asyncio.ensure_future(ui._step_ai_loop(force=True))
