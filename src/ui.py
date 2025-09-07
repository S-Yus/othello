import asyncio, json
from js import document, window, console, navigator
from pyodide.ffi import create_proxy
from typing import Tuple, Optional
from src.game import Game, BLACK, WHITE, EMPTY
from src import ai as AI

Coord = Tuple[int,int]
LS_KEY = "othello_advanced_save_v1"

PASS_OVERLAY_MS   = 750   # パス演出の表示時間
RESULT_DELAY_MS   = 500   # ★ 終局時、盤面を見せる遅延（ms）

class UI:
    def __init__(self, game: Game):
        self.game = game

        # DOM
        self.board_el   = document.getElementById("board")
        self.status_el  = document.getElementById("status")
        self.eval_fill  = document.getElementById("evalFill")
        self.white_count_el = document.getElementById("whiteCount")
        self.black_count_el = document.getElementById("blackCount")

        self.overlay = document.getElementById("overlay")
        self.overlay_content = document.getElementById("overlayContent")

        self.mode_select   = document.getElementById("modeSelect")
        self.depth_select  = document.getElementById("depthSelect")
        self.delay_range   = document.getElementById("delayRange")
        self.delay_value   = document.getElementById("delayValue")
        self.hints_toggle  = document.getElementById("hintsToggle")
        self.autosave_toggle = document.getElementById("autosaveToggle")

        self.hint_btn   = document.getElementById("hintBtn")
        self.undo_btn   = document.getElementById("undoBtn")
        self.redo_btn   = document.getElementById("redoBtn")
        self.pass_btn   = document.getElementById("passBtn")
        self.reset_btn  = document.getElementById("resetBtn")

        self.moves_list = document.getElementById("movesList")
        self.copy_moves_btn = document.getElementById("copyMovesBtn")
        self.clear_moves_btn = document.getElementById("clearMovesBtn")

        # 状態
        self.busy = False
        self.ai_delay = int(self.delay_range.value) / 1000.0
        self.time_limit_ms: Optional[int] = None

        # ★ リザルト表示の遅延タスク
        self._result_task: Optional[asyncio.Task] = None

        self._init_board_dom()
        self._bind_events()
        self._try_restore()
        self._sync_controls_from_state()

    # 初期DOM
    def _init_board_dom(self):
        for y in range(8):
            for x in range(8):
                btn = document.createElement("button")
                btn.classList.add("cell")
                btn.dataset.x = str(x)
                btn.dataset.y = str(y)
                btn.addEventListener("click", create_proxy(self._on_cell_click))
                self.board_el.appendChild(btn)

    # イベント
    def _bind_events(self):
        self.mode_select.addEventListener("change", create_proxy(self._on_mode_change))
        self.depth_select.addEventListener("change", create_proxy(self._on_depth_change))
        self.delay_range.addEventListener("input", create_proxy(self._on_delay_change))
        self.hints_toggle.addEventListener("change", create_proxy(self._on_toggle_change))
        self.autosave_toggle.addEventListener("change", create_proxy(self._on_toggle_change))

        self.hint_btn.addEventListener("click", create_proxy(self._on_hint))
        self.undo_btn.addEventListener("click", create_proxy(self._on_undo))
        self.redo_btn.addEventListener("click", create_proxy(self._on_redo))
        self.pass_btn.addEventListener("click", create_proxy(self._on_pass))
        self.reset_btn.addEventListener("click", create_proxy(self._on_reset))

        self.copy_moves_btn.addEventListener("click", create_proxy(self._on_copy_moves))
        self.clear_moves_btn.addEventListener("click", create_proxy(self._on_clear_moves))

        document.addEventListener("keydown", create_proxy(self._on_keydown))

    # 保存/復元
    def _try_restore(self):
        try:
            s = window.localStorage.getItem(LS_KEY)
            if s:
                data = json.loads(s)
                self.game.load_dict(data)
                AI.reset_tt()
        except Exception as e:
            console.warn("restore failed", e)

    def _autosave(self):
        if not self.autosave_toggle.checked: return
        try:
            d = self.game.to_dict()
            window.localStorage.setItem(LS_KEY, json.dumps(d))
        except Exception as e:
            console.warn("autosave failed", e)

    # 共通UI更新
    def _sync_controls_from_state(self):
        for i in range(self.mode_select.options.length):
            if self.mode_select.options.item(i).value == self.game.mode:
                self.mode_select.selectedIndex = i; break
        self.delay_value.textContent = f"{int(self.ai_delay*1000)}ms"
        self.undo_btn.disabled = not self.game.can_undo()
        self.redo_btn.disabled = not self.game.can_redo()
        # 打てる手があるときはパス不可（ボタンを無効に）
        self.pass_btn.disabled = len(self.game.get_legal_moves()) > 0

    def render(self):
        # 盤
        for y in range(8):
            for x in range(8):
                idx = y*8 + x
                cell = self.board_el.children.item(idx)
                while cell.firstChild: cell.removeChild(cell.firstChild)
                cell.classList.remove("lastmove")

                v = int(self.game.board[y,x])
                if v != EMPTY:
                    st = document.createElement("div")
                    st.classList.add("stone")
                    st.classList.add("black" if v==BLACK else "white")
                    cell.appendChild(st)

        if self.game.last_move is not None:
            lx,ly = self.game.last_move
            self.board_el.children.item(ly*8+lx).classList.add("lastmove")

        # 合法手ヒント
        if self.hints_toggle.checked:
            for (x,y) in self.game.get_legal_moves():
                cell = self.board_el.children.item(y*8+x)
                dot = document.createElement("div"); dot.classList.add("hint")
                cell.appendChild(dot)

        # ステータス・バー
        sc = self.game.score()
        turn = "黒" if self.game.current_player==BLACK else "白"
        mode_jp = {"PVP":"2人","AI_WHITE":"vs AI（白）","AI_BLACK":"vs AI（黒）","AI_VS_AI":"AI vs AI"}[self.game.mode]
        self.status_el.textContent = f"手番：{turn}｜石数 B {sc['black']} - W {sc['white']}｜モード：{mode_jp}"

        total = max(1, sc['black'] + sc['white'])
        h = int(100 * sc['black'] / total)
        self.eval_fill.style.height = f"{h}%"
        if self.white_count_el is not None: self.white_count_el.textContent = str(sc['white'])
        if self.black_count_el is not None: self.black_count_el.textContent = str(sc['black'])

        self._render_moves()
        self._sync_controls_from_state()
        self._autosave()

        # 自動パス／終局チェック（ここでのみスケジュール）
        asyncio.ensure_future(self._check_auto_pass_and_result())

    def _render_moves(self):
        while self.moves_list.firstChild: self.moves_list.removeChild(self.moves_list.firstChild)
        for i in range(0, len(self.game.move_history), 2):
            li = document.createElement("li")
            one = self.game.move_history[i] if i < len(self.game.move_history) else ""
            two = self.game.move_history[i+1] if (i+1) < len(self.game.move_history) else ""
            li.textContent = f"{(i//2)+1}. {one or '-'} {two or ''}".strip()
            self.moves_list.appendChild(li)
        self.moves_list.scrollTop = self.moves_list.scrollHeight

    # オーバーレイ
    def _hide_overlay(self):
        self.overlay.classList.add("hidden")
        self.overlay.classList.remove("show")
        self.overlay_content.innerHTML = ""

    def _show_pass_overlay(self, who:str):
        self.overlay_content.innerHTML = f"<h2>パス</h2><p>{who} は着手可能手がありません。</p>"
        self.overlay.classList.remove("hidden"); self.overlay.classList.add("show")

    def _show_result_overlay(self):
        sc = self.game.score()
        b, w = sc["black"], sc["white"]
        if b > w: title = "黒の勝ち"
        elif w > b: title = "白の勝ち"
        else: title = "引き分け"
        self.overlay_content.innerHTML = f"""
          <h2>結果</h2>
          <p><strong>黒 {b} - 白 {w}</strong></p>
          <p>{title}</p>
          <div class="overlay-actions">
            <button id="overlayNew" class="danger">New Game</button>
            <button id="overlayClose">Close</button>
          </div>
        """
        self.overlay.classList.remove("hidden"); self.overlay.classList.add("show")
        document.getElementById("overlayNew").addEventListener("click", create_proxy(self._on_reset))
        document.getElementById("overlayClose").addEventListener("click", create_proxy(lambda e: self._hide_overlay()))

    # ★ リザルト表示の遅延スケジュール（重複防止つき）
    def _cancel_result_task(self):
        if self._result_task is not None and not self._result_task.done():
            self._result_task.cancel()
        self._result_task = None

    def _schedule_result_overlay(self, delay_ms:int=RESULT_DELAY_MS):
        self._cancel_result_task()
        async def runner():
            # まず規定の遅延（最終盤面を見せる）
            await asyncio.sleep(delay_ms / 1000.0)
            # パス演出がまだ出ているなら、消えるまで待つ（最大 PASS_OVERLAY_MS ちょい超え）
            waited = 0.0
            while self.overlay.classList.contains("show") and "パス" in str(self.overlay_content.textContent):
                await asyncio.sleep(0.05)
                waited += 0.05
                if waited > (PASS_OVERLAY_MS/1000.0) + 0.3:
                    break
            # まだ終局状態なら結果を表示
            if self.game.is_game_over():
                self._show_result_overlay()
            self._result_task = None
        self._result_task = asyncio.ensure_future(runner())

    # 自動パス／終局
    async def _check_auto_pass_and_result(self):
        # 終局なら：0.5秒見せてから結果
        if self.game.is_game_over():
            self._schedule_result_overlay(RESULT_DELAY_MS)
            return

        # 現手番に合法手なし → 自動パス（演出つき）
        if len(Game.legal_moves(self.game.board, self.game.current_player)) == 0:
            who = "黒" if self.game.current_player == BLACK else "白"
            self._show_pass_overlay(who)
            self.busy = True
            try:
                await asyncio.sleep(PASS_OVERLAY_MS / 1000.0)
                if self.game.pass_turn():
                    self.render()   # ここで終局した場合、render() 内のチェックでリザルトがスケジュールされる
            finally:
                self.busy = False
                self._hide_overlay()

    # ハンドラ
    def _on_cell_click(self, evt):
        if self.busy: return
        x = int(evt.currentTarget.dataset.x); y = int(evt.currentTarget.dataset.y)
        if self.game.make_move(x,y):
            self.render()
            asyncio.ensure_future(self._step_ai_loop())

    def _on_pass(self, evt):
        if self.busy: return
        if self.game.pass_turn():  # 打てるなら False で何もしない
            self.render()
            asyncio.ensure_future(self._step_ai_loop())

    def _on_reset(self, evt):
        if self.busy: return
        self._hide_overlay()
        self._cancel_result_task()  # ★ 予約表示をキャンセル
        self.game.reset()
        AI.reset_tt()
        self.render()
        asyncio.ensure_future(self._step_ai_loop(force=True))

    def _on_undo(self, evt):
        if self.busy: return
        steps = 2 if self.game.mode in ("AI_WHITE","AI_BLACK") else 1
        if self.game.undo(steps):
            self._hide_overlay()
            self._cancel_result_task()
            self.render()

    def _on_redo(self, evt):
        if self.busy: return
        steps = 2 if self.game.mode in ("AI_WHITE","AI_BLACK") else 1
        if self.game.redo(steps):
            self._hide_overlay()
            self._cancel_result_task()
            self.render()

    def _on_hint(self, evt):
        if self.busy: return
        mv = AI.choose_move(self.game.board, self.game.current_player, int(self.depth_select.value), self.time_limit_ms)
        if mv is None: return
        self.game.last_move = mv
        self.render()

    def _on_mode_change(self, evt):
        self.game.mode = str(self.mode_select.value)
        self._hide_overlay()
        self._cancel_result_task()
        self.render()
        asyncio.ensure_future(self._step_ai_loop(force=True))

    def _on_depth_change(self, evt):
        self.render()

    def _on_delay_change(self, evt):
        self.ai_delay = int(self.delay_range.value)/1000.0
        self.delay_value.textContent = f"{int(self.ai_delay*1000)}ms"

    def _on_toggle_change(self, evt):
        self.render()

    def _on_copy_moves(self, evt):
        text = " ".join(self.game.move_history)
        try:
            navigator.clipboard.writeText(text)
        except Exception:
            ta = document.createElement("textarea")
            ta.value = text; document.body.appendChild(ta)
            ta.select(); document.execCommand("copy")
            document.body.removeChild(ta)

    def _on_clear_moves(self, evt):
        self.game.move_history.clear()
        self.render()

    def _on_keydown(self, e):
        if e.repeat: return
        key = (e.key or "").lower()
        if key == "u": self._on_undo(e)
        elif key == "y": self._on_redo(e)
        elif key == "p": self._on_pass(e)
        elif key == "n": self._on_reset(e)
        elif key == "h": self._on_hint(e)

    # AI制御
    async def _step_ai_loop(self, force:bool=False):
        if self.game.is_game_over():
            self._schedule_result_overlay(RESULT_DELAY_MS)
            return

        async def ai_once(ai_player:int):
            # 合法手なし → 自動パス
            if len(Game.legal_moves(self.game.board, ai_player)) == 0:
                who = "黒" if ai_player == BLACK else "白"
                self._show_pass_overlay(who)
                self.busy = True
                try:
                    await asyncio.sleep(PASS_OVERLAY_MS / 1000.0)
                    if self.game.pass_turn():
                        self.render()
                finally:
                    self.busy = False
                    self._hide_overlay()
                return

            self.busy = True
            try:
                await asyncio.sleep(self.ai_delay)
                mv = AI.choose_move(self.game.board, ai_player, int(self.depth_select.value), self.time_limit_ms)
                if mv is not None and self.game.current_player == ai_player:
                    self.game.make_move(mv[0], mv[1])
                    self.render()
            finally:
                self.busy = False

        if self.game.mode == "AI_VS_AI":
            while not self.game.is_game_over() and self.game.mode == "AI_VS_AI":
                ai_player = BLACK if self.game.current_player==BLACK else WHITE
                await ai_once(ai_player)
                await asyncio.sleep(0)
            if self.game.is_game_over():
                self._schedule_result_overlay(RESULT_DELAY_MS)
            return

        ai_player = None
        if self.game.mode == "AI_WHITE": ai_player = WHITE
        elif self.game.mode == "AI_BLACK": ai_player = BLACK

        if ai_player is None: return
        if not force and self.game.current_player != ai_player: return

        await ai_once(ai_player)
        if self.game.is_game_over():
            self._schedule_result_overlay(RESULT_DELAY_MS)
