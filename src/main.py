from src.game import Game
from src.ui import UI

# 起動
game = Game(mode="AI_WHITE")  # 初期モードは必要に応じて変更
ui = UI(game)
ui.render()

# 初手がAIなら自動開始
import asyncio
asyncio.ensure_future(ui._step_ai_loop(force=True))
