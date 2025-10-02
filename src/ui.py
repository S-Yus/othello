# src/ui.py
import asyncio, json
from typing import Tuple, Optional, Dict, Any
from js import document, window, console, navigator
from pyodide.ffi import create_proxy

from src.game import Game, BLACK, WHITE, EMPTY
from src import ai as AI

Coord = Tuple[int, int]
LS_KEY = "othello_advanced_save_v1"

# 表示/演出まわり
PASS_OVERLAY_MS = 750
RESULT_DELAY_MS = 500
THINKING_TEXT   = "AIが考えています…"


class UI:
    def __init__(self, game: Game):
        self.game = game

        # ===== DOM参照（index.html のIDと一致させる） =====
        self.board_el         = document.getElementById("board")
        self.status_el        = document.getElementById("status")
        self.eval_fill        = document.getElementById("evalFill")
        self.white_count_el   = document.getElementById("whiteCount")
        self.black_count_el   = document.getElementById("blackCount")

        self.overlay          = document.getElementById("overlay")
        self.overlay_content  = document.getElementById("overlayContent")

        self.mode_select      = document.getElementById("modeSelect")
        self.depth_select     = document.getElementById("depthSelect")
        self.delay_range      = document.getElementById("delayRange")
        self.delay_value      = document.getElementById("delayValue")
        self.hints_toggle     = document.getElementById("hintsToggle")
        self.autosave_toggle  = document.getElementById("autosaveToggle")

        self.hint_btn         = document.getElementById("hintBtn")
        self.undo_btn         = document.getElementById("undoBtn")
        self.redo_btn         = document.getElementById("redoBtn")
        self.pass_btn         = document.getElementById("passBtn")
        self.reset_btn        = document.getElementById("resetBtn")

        self.moves_list       = document.getElementById("movesList")
        self.copy_moves_btn   = document.getElementById("copyMovesBtn")
        self.clear_moves_btn  = document.getElementById("clearMovesBtn")

        # ===== ランタイム状態 =====
        self.busy: bool = False
        self.ai_delay: float = (int(self.delay_range.value) / 1000.0) if self.delay_range else 0.3
        self.time_limit_ms: Optional[int] = None
        self._result_task: Optional[asyncio.Task] = None

        # 必須DOMが取れているか検証（足りないとここで詳細エラー）
        self._assert_dom()

        # 盤セルを生成 → 各種イベントをバインド → セーブ復元 → UIを同期
        self._init_board_dom()
        self._bind_events()
        self._try_restore()
        self._sync_controls_from_state()

    # -------------------------------------------------------------------------
    # 安全装置：必要なDOMが無いとき即座に原因を出す
    # -------------------------------------------------------------------------
    def _assert_dom(self):
        required: Dict[str, Any] = {
            "board": self.board_el,
            "status": self.status_el,
            "evalFill": self.eval_fill,
            "whiteCount": self.white_count_el,
            "blackCount": self.black_count_el,
            "overlay": self.overlay,
            "overlayContent": self.overlay_content,
            "modeSelect": self.mode_select,
            "depthSelect": self.depth_select,
            "delayRange": self.delay_range,
            "hintsToggle": self.hints_toggle,
            "autosaveToggle": self.autosave_toggle,
            "hintBtn": self.hint_btn,
            "undoBtn": self.undo_btn,
            "redoBtn": self.redo_btn,
            "passBtn": self.pass_btn,
            "resetBtn": self.reset_btn,
            "movesList": self.moves_list,
            "copyMovesBtn": self.copy_moves_btn,
            "clearMovesBtn": self.clear_moves_btn,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            console.error("[Othello] Missing DOM ids:", missing)
            raise RuntimeError(f"Missing DOM ids: {missing}")

    # -------------------------------------------------------------------------
    # 盤セル生成（button.cell × 64）
    #  - クリックで着手
    #  - ホバー/フォーカスでプレビュー石（PC向け）
    # -------------------------------------------------------------------------
    def _init_board_dom(self):
        for y in range(8):
            for x in range(8):
                btn = document.createElement("button")
                btn.classList.add("cell")
                btn.dataset.x = str(x)
                btn.dataset.y = str(y)

                # click: 着手
                btn.addEventListener("click", create_proxy(self._on_cell_click))

                # hover preview（スマホはpointerenterが来ないので実質PC用）
                def on_enter(ev, xx=x, yy=y):
                    if int(self.game.board[yy, xx]) != EMPTY:
                        return
                    if (xx, yy) not in self.game.get_legal_moves():
                        return
                    pv = document.createElement("div")
                    pv.classList.add("stone", "preview")
                    pv.classList.add("black" if self.game.current_player == BLACK else "white")
                    ev.currentTarget.appendChild(pv)

                def on_leave(ev):
                    p = ev.currentTarget.querySelector(".stone.preview")
                    if p:
                        ev.currentTarget.removeChild(p)

                btn.addEventListener("pointerenter", create_proxy(on_enter))
                btn.addEventListener("pointerleave", create_proxy(on_leave))

                self.board_el.appendChild(btn)
                
    console.log("[Othello] cells:", self.board_el.children.length)
    if self.board_el.children.length != 64:
        console.error("[Othello] cell build failed")
    # -------------------------------------------------------------------------
    # イベント束ね
    # -------------------------------------------------------------------------
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

        # キーボードショートカット
        document.addEventListener("keydown", create_proxy(self._on_keydown))
        # レイアウト変化で評価バー向きを再反映
        window.addEventListener("resize", create_proxy(lambda e: self._update_evalbar(self.game.score())))

    # -------------------------------------------------------------------------
    # セーブ/ロード
    # -------------------------------------------------------------------------
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
        if not self.autosave_toggle.checked:
            return
        try:
            d = self.game.to_dict()
            window.localStorage.setItem(LS_KEY, json.dumps(d))
        except Exception as e:
            console.warn("autosave failed", e)

    # -------------------------------------------------------------------------
    # 共通UI同期
    # -------------------------------------------------------------------------
    def _sync_controls_from_state(self):
        # モード反映
        for i in range(self.mode_select.options.length):
            if self.mode_select.options.item(i).value == self.game.mode:
                self.mode_select.selectedIndex = i
                break

        # 遅延
        self.delay_value.textContent = f"{int(self.ai_delay * 1000)}ms"

        # ボタン状態
        self.undo_btn.disabled = not self.game.can_undo()
        self.redo_btn.disabled = not self.game.can_redo()
        self.pass_btn.disabled = len(self.game.get_legal_moves()) > 0

    def _is_mobile(self) -> bool:
        try:
            return bool(window.matchMedia("(max-width: 720px)").matches)
        except Exception:
            return False

    def _update_evalbar(self, sc: dict):
        """PCは縦（height%）、スマホは横（width%）へ反映。"""
        total = max(1, sc["black"] + sc["white"])
        pct = int(100 * sc["black"] / total)
        if self._is_mobile():
            self.eval_fill.style.width = f"{pct}%"
            self.eval_fill.style.height = "100%"
        else:
            self.eval_fill.style.height = f"{pct}%"
            self.eval_fill.style.width = "100%"

    # -------------------------------------------------------------------------
    # メイン描画
    #  - 反転アニメ：self.game.last_flips に .flip を付与
    # -------------------------------------------------------------------------
    def render(self):
        # 盤面
        flips_set = set(tuple(rc) for rc in self.game.last_flips)
        for y in range(8):
            for x in range(8):
                idx = y * 8 + x
                cell = self.board_el.children.item(idx)
                while cell.firstChild:
                    cell.removeChild(cell.firstChild)
                cell.classList.remove("lastmove")

                v = int(self.game.board[y, x])
                if v != EMPTY:
                    st = document.createElement("div")
                    st.classList.add("stone")
                    st.classList.add("black" if v == BLACK else "white")
                    if (x, y) in flips_set:
                        st.classList.add("flip")  # ← 反転アニメ
                    cell.appendChild(st)

        if self.game.last_move is not None:
            lx, ly = self.game.last_move
            self.board_el.children.item(ly * 8 + lx).classList.add("lastmove")

        # 合法手ヒント
        if self.hints_toggle.checked:
            for (x, y) in self.game.get_legal_moves():
                cell = self.board_el.children.item(y * 8 + x)
                dot = document.createElement("div")
                dot.classList.add("hint")
                cell.appendChild(dot)

        # ステータス
        sc = self.game.score()
        turn = "黒" if self.game.current_player == BLACK else "白"
        mode_jp = {
            "PVP": "2人",
            "AI_WHITE": "vs AI（白）",
            "AI_BLACK": "vs AI（黒）",
            "AI_VS_AI": "AI vs AI",
        }.get(self.game.mode, "—")
        self.status_el.textContent = f"手番：{turn}｜石数 B {sc['black']} - W {sc['white']}｜モード：{mode_jp}"

        # 評価バーとバッジ
        self._update_evalbar(sc)
        if self.white_count_el is not None:
            self.white_count_el.textContent = str(sc["white"])
        if self.black_count_el is not None:
            self.black_count_el.textContent = str(sc["black"])

        # 手順リスト
        self._render_moves()

        # ボタン活性など
        self._sync_controls_from_state()

        # 自動保存
        self._autosave()

        # 自動パス/結果
        asyncio.ensure_future(self._check_auto_pass_and_result())

    def _render_moves(self):
        while self.moves_list.firstChild:
            self.moves_list.removeChild(self.moves_list.firstChild)
        for i in range(0, len(self.game.move_history), 2):
            li = document.createElement("li")
            one = self.game.move_history[i] if i < len(self.game.move_history) else ""
            two = self.game.move_history[i + 1] if (i + 1) < len(self.game.move_history) else ""
            li.textContent = f"{(i // 2) + 1}. {one or '-'} {two or ''}".strip()
            self.moves_list.appendChild(li)
        self.moves_list.scrollTop = self.moves_list.scrollHeight

    # -------------------------------------------------------------------------
    # オーバーレイ
    # -------------------------------------------------------------------------
    def _hide_overlay(self):
        self.overlay.classList.add("hidden")
        self.overlay.classList.remove("show")
        self.overlay_content.innerHTML = ""

    def _show_pass_overlay(self, who: str):
        self.overlay_content.innerHTML = f"<h2>パス</h2><p>{who} は着手可能手がありません。</p>"
        self.overlay.classList.remove("hidden")
        self.overlay.classList.add("show")

    def _show_result_overlay(self):
        sc = self.game.score()
        b, w = sc["black"], sc["white"]
        if b > w:
            title = "黒の勝ち"
        elif w > b:
            title = "白の勝ち"
        else:
            title = "引き分け"
        self.overlay_content.innerHTML = f"""
          <h2>結果</h2>
          <p><strong>黒 {b} - 白 {w}</strong></p>
          <p>{title}</p>
          <div class="overlay-actions">
            <button id="overlayNew" class="danger">New Game</button>
            <button id="overlayClose">Close</button>
          </div>
        """
        self.overlay.classList.remove("hidden")
        self.overlay.classList.add("show")
        document.getElementById("overlayNew").addEventListener("click", create_proxy(self._on_reset))
        document.getElementById("overlayClose").addEventListener(
            "click", create_proxy(lambda e: self._hide_overlay())
        )

    def _show_thinking(self):
        self.overlay_content.innerHTML = f"""
          <div class="spinner"></div>
          <p class="muted">{THINKING_TEXT}</p>
        """
        self.overlay.classList.remove("hidden")
        self.overlay.classList.add("show")

    # -------------------------------------------------------------------------
    # 結果表示の遅延スケジュール
    # -------------------------------------------------------------------------
    def _cancel_result_task(self):
        if self._result_task is not None and not self._result_task.done():
            self._result_task.cancel()
        self._result_task = None

    def _schedule_result_overlay(self, delay_ms: int = RESULT_DELAY_MS):
        self._cancel_result_task()

        async def runner():
            await asyncio.sleep(delay_ms / 1000.0)
            if self.game.is_game_over():
                self._show_result_overlay()
            self._result_task = None

        self._result_task = asyncio.ensure_future(runner())

    # -------------------------------------------------------------------------
    # 自動パス／終局チェック
    # -------------------------------------------------------------------------
    async def _check_auto_pass_and_result(self):
        if self.game.is_game_over():
            self._schedule_result_overlay(RESULT_DELAY_MS)
            return

        if len(Game.legal_moves(self.game.board, self.game.current_player)) == 0:
            who = "黒" if self.game.current_player == BLACK else "白"
            self._show_pass_overlay(who)
            self.busy = True
            try:
                await asyncio.sleep(PASS_OVERLAY_MS / 1000.0)
                if self.game.pass_turn():
                    self.render()
            finally:
                self.busy = False
                self._hide_overlay()

    # -------------------------------------------------------------------------
    # ハンドラ類
    # -------------------------------------------------------------------------
    def _on_cell_click(self, evt):
        if self.busy:
            return
        x = int(evt.currentTarget.dataset.x)
        y = int(evt.currentTarget.dataset.y)
        if self.game.make_move(x, y):
            self.render()
            asyncio.ensure_future(self._step_ai_loop())

    def _on_pass(self, evt):
        if self.busy:
            return
        if self.game.pass_turn():
            self.render()
            asyncio.ensure_future(self._step_ai_loop())

    def _on_reset(self, evt):
        if self.busy:
            return
        self._hide_overlay()
        self._cancel_result_task()
        self.game.reset()
        AI.reset_tt()
        self.render()
        asyncio.ensure_future(self._step_ai_loop(force=True))

    def _on_undo(self, evt):
        if self.busy:
            return
        steps = 2 if self.game.mode in ("AI_WHITE", "AI_BLACK") else 1
        if self.game.undo(steps):
            self._hide_overlay()
            self._cancel_result_task()
            self.render()

    def _on_redo(self, evt):
        if self.busy:
            return
        steps = 2 if self.game.mode in ("AI_WHITE", "AI_BLACK") else 1
        if self.game.redo(steps):
            self._hide_overlay()
            self._cancel_result_task()
            self.render()

    def _on_hint(self, evt):
        if self.busy:
            return
        mv = AI.choose_move(
            self.game.board, self.game.current_player, int(self.depth_select.value), self.time_limit_ms
        )
        if mv is None:
            return
        # 最終着手の枠だけ示す（着手はしない）
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
        self.ai_delay = int(self.delay_range.value) / 1000.0
        self.delay_value.textContent = f"{int(self.ai_delay * 1000)}ms"

    def _on_toggle_change(self, evt):
        self.render()

    def _on_copy_moves(self, evt):
        text = " ".join(self.game.move_history)
        try:
            navigator.clipboard.writeText(text)
        except Exception:
            ta = document.createElement("textarea")
            ta.value = text
            document.body.appendChild(ta)
            ta.select()
            document.execCommand("copy")
            document.body.removeChild(ta)

    def _on_clear_moves(self, evt):
        self.game.move_history.clear()
        self.render()

    def _on_keydown(self, e):
        if e.repeat:
            return
        key = (e.key or "").lower()
        if key == "u":
            self._on_undo(e)
        elif key == "y":
            self._on_redo(e)
        elif key == "p":
            self._on_pass(e)
        elif key == "n":
            self._on_reset(e)
        elif key == "h":
            self._on_hint(e)

    # -------------------------------------------------------------------------
    # AI制御
    # -------------------------------------------------------------------------
    async def _step_ai_loop(self, force: bool = False):
        if self.game.is_game_over():
            self._schedule_result_overlay(RESULT_DELAY_MS)
            return

        async def ai_once(ai_player: int):
            # パス
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

            # 考え中…
            self._show_thinking()
            self.busy = True
            try:
                await asyncio.sleep(self.ai_delay)
                mv = AI.choose_move(
                    self.game.board, ai_player, int(self.depth_select.value), self.time_limit_ms
                )
                if mv is not None and self.game.current_player == ai_player:
                    self.game.make_move(mv[0], mv[1])
                    self.render()
            finally:
                self.busy = False
                self._hide_overlay()

        # AI vs AI
        if self.game.mode == "AI_VS_AI":
            while not self.game.is_game_over() and self.game.mode == "AI_VS_AI":
                ai_player = BLACK if self.game.current_player == BLACK else WHITE
                await ai_once(ai_player)
                await asyncio.sleep(0)
            if self.game.is_game_over():
                self._schedule_result_overlay(RESULT_DELAY_MS)
            return

        # 片側AI
        ai_player = None
        if self.game.mode == "AI_WHITE":
            ai_player = WHITE
        elif self.game.mode == "AI_BLACK":
            ai_player = BLACK

        if ai_player is None:
            return
        if not force and self.game.current_player != ai_player:
            return

        await ai_once(ai_player)
        if self.game.is_game_over():
            self._schedule_result_overlay(RESULT_DELAY_MS)
