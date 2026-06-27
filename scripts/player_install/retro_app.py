"""Retro 90s RTS-style tkinter installer wizard."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
from pathlib import Path

from campaign_branding import resolve_commander_logo, resolve_crest_image, warcraft_commander_crest

from player_install import checks, core, ops

# Late 90s RTS palette — dark stone, brass trim, parchment text
COLORS = {
    "bg": "#141820",
    "panel": "#1e2430",
    "panel_edge": "#4a4030",
    "text": "#d4c4a0",
    "muted": "#8a8070",
    "accent": "#c9a227",
    "ok": "#6a9a5a",
    "warn": "#b85c38",
    "btn": "#2a3040",
    "btn_hi": "#3a4558",
}


class RetroButton(tk.Frame):
    def __init__(self, master, text: str, command, **kwargs):
        super().__init__(master, bg=COLORS["panel_edge"], padx=2, pady=2)
        self._cmd = command
        inner = tk.Label(
            self,
            text=text,
            font=("Chicago", 12) if "Chicago" in tkfont.families() else ("Helvetica", 11, "bold"),
            bg=COLORS["btn"],
            fg=COLORS["text"],
            padx=14,
            pady=6,
            cursor="hand2",
        )
        inner.pack()
        for w in (self, inner):
            w.bind("<Enter>", lambda _e: inner.configure(bg=COLORS["btn_hi"]))
            w.bind("<Leave>", lambda _e: inner.configure(bg=COLORS["btn"]))
            w.bind("<Button-1>", lambda _e: self._cmd())


class InstallerWizard(tk.Tk):
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root.resolve()
        self.install_root = core.detect_install_root(self.project_root) or self.project_root
        self.paths = core.resolve_paths(self.install_root)
        self.log_lines: list[str] = []
        self._crest_photo = None
        self._icon_photo = None

        self.title("Warcraft: Commander — Install Commander")
        self.configure(bg=COLORS["bg"])
        self.geometry("720x520")
        self.minsize(640, 480)
        self._apply_window_icon()

        self._build_chrome()
        self.show_splash()

    def _apply_window_icon(self) -> None:
        logo = resolve_commander_logo(self.project_root)
        if not logo or not logo.is_file():
            return
        try:
            from PIL import Image, ImageTk

            img = Image.open(logo).convert("RGBA")
            img.thumbnail((64, 64))
            self._icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _build_chrome(self) -> None:
        top = tk.Frame(self, bg=COLORS["panel_edge"], padx=3, pady=3)
        top.pack(fill="x", padx=10, pady=(10, 4))
        inner = tk.Frame(top, bg=COLORS["panel"])
        inner.pack(fill="x", padx=2, pady=2)
        tk.Label(
            inner,
            text="WARCRAFT : COMMANDER",
            font=("Courier", 16, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["accent"],
        ).pack(pady=(8, 0))
        tk.Label(
            inner,
            text="Player Install Wizard v1.0",
            font=("Courier", 10),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(pady=(0, 8))

        self.body = tk.Frame(self, bg=COLORS["bg"])
        self.body.pack(fill="both", expand=True, padx=12, pady=6)

        log_frame = tk.Frame(self, bg=COLORS["panel_edge"], padx=2, pady=2)
        log_frame.pack(fill="x", padx=12, pady=(0, 10))
        self.log = tk.Text(
            log_frame,
            height=5,
            font=("Courier", 9),
            bg="#0c1018",
            fg=COLORS["muted"],
            relief="flat",
            wrap="word",
        )
        self.log.pack(fill="x", padx=4, pady=4)
        self.log.configure(state="disabled")

    def _clear_body(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

    def _log(self, msg: str) -> None:
        self.log_lines.append(msg)
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def show_splash(self) -> None:
        self._clear_body()
        frame = tk.Frame(self.body, bg=COLORS["bg"])
        frame.pack(expand=True, fill="both")

        crest_path = resolve_commander_logo(self.project_root) or resolve_crest_image(self.project_root)
        if crest_path and crest_path.is_file():
            try:
                from PIL import Image, ImageTk

                img = Image.open(crest_path).convert("RGBA")
                img.thumbnail((280, 200))
                self._crest_photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(frame, image=self._crest_photo, bg=COLORS["bg"], cursor="hand2")
                lbl.pack(pady=12)
                lbl.bind("<Button-1>", lambda _e: self.show_checks())
            except Exception:
                self._ascii_crest(frame, click=True)
        else:
            self._ascii_crest(frame, click=True)

        tk.Label(
            frame,
            text="Click the crest to begin installation",
            font=("Courier", 11),
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(pady=8)

    def _ascii_crest(self, parent, *, click: bool = False) -> None:
        txt = tk.Text(
            parent,
            height=12,
            width=52,
            font=("Courier", 8),
            bg=COLORS["bg"],
            fg=COLORS["accent"],
            relief="flat",
            cursor="hand2" if click else "arrow",
        )
        txt.insert("1.0", warcraft_commander_crest())
        txt.configure(state="disabled")
        txt.pack(pady=8)
        if click:
            txt.bind("<Button-1>", lambda _e: self.show_checks())

    def show_checks(self) -> None:
        self._clear_body()
        self._log("Running system checks…")
        frame = tk.Frame(self.body, bg=COLORS["bg"])
        frame.pack(fill="both", expand=True)

        results = [
            checks.check_python(),
            checks.check_google_earth(),
            checks.check_install_layout(self.install_root),
        ]
        for row in results:
            color = COLORS["ok"] if row["ok"] else COLORS["warn"]
            line = f"{'[OK]' if row['ok'] else '[--]'} {row['label']}: {row['detail']}"
            self._log(line)
            tk.Label(frame, text=line, font=("Courier", 9), bg=COLORS["bg"], fg=color, anchor="w").pack(
                fill="x", pady=2
            )
            if row["id"] == "google_earth" and not row["ok"]:
                link = tk.Label(
                    frame,
                    text="→ Download Google Earth Pro",
                    font=("Courier", 9, "underline"),
                    bg=COLORS["bg"],
                    fg=COLORS["accent"],
                    cursor="hand2",
                )
                link.pack(anchor="w")
                link.bind(
                    "<Button-1>",
                    lambda _e: __import__("webbrowser").open(checks.GE_DOWNLOAD_URL),
                )

        warn = checks.opened_from_zip_warning(self.paths["entry_kml"])
        if warn:
            self._log(f"WARN: {warn}")
            tk.Label(frame, text=warn, font=("Courier", 9), bg=COLORS["bg"], fg=COLORS["warn"]).pack(
                fill="x", pady=6
            )

        btn_row = tk.Frame(frame, bg=COLORS["bg"])
        btn_row.pack(pady=16)
        RetroButton(btn_row, "Continue →", self.show_install_tools).pack(side="left", padx=6)
        RetroButton(btn_row, "Choose install folder…", self._pick_install_root).pack(side="left", padx=6)

    def _pick_install_root(self) -> None:
        chosen = filedialog.askdirectory(title="Select WoW Commander install folder")
        if chosen:
            self.install_root = Path(chosen)
            self.paths = core.resolve_paths(self.install_root)
            self._log(f"Install folder: {self.install_root}")
            self.show_checks()

    def show_install_tools(self) -> None:
        self._clear_body()
        frame = tk.Frame(self.body, bg=COLORS["bg"])
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="INSTALL & MAINTENANCE",
            font=("Courier", 12, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["accent"],
        ).pack(anchor="w", pady=(0, 10))

        tools = [
            ("Extract / join release zip", self._tool_extract),
            ("Scan duplicate installs", self._tool_dupes),
            ("Clean reinstall (wipe tiles/cache)", self._tool_clean),
            ("Import icons from Downloads", self._tool_icons),
            ("Import icon pack (.zip)", self._tool_import_pack),
            ("Create desktop app (CommanderLogo icon)", self._tool_shortcut),
            ("Open game KML in Google Earth", self._tool_open_kml),
            ("Launch player menu", self._tool_menu),
        ]
        for label, cmd in tools:
            RetroButton(frame, label, cmd).pack(anchor="w", pady=4)

        RetroButton(frame, "Finish", self.show_done).pack(anchor="w", pady=(20, 0))

    def _tool_extract(self) -> None:
        dl = core.downloads_dir()
        split = checks.find_split_zip_parts(dl)
        if split:
            out = split["folder"] / "wowcommander-player-joined.zip"
            ok, msg = ops.join_split_zip(split["main"], out)
            self._log(msg)
            if ok:
                dest = filedialog.askdirectory(title="Extract joined zip to…", initialdir=str(dl))
                if dest:
                    ok2, msg2 = ops.extract_zip(out, Path(dest))
                    self._log(msg2)
            return
        zips = checks.find_release_zips(dl)
        if not zips:
            path = filedialog.askopenfilename(filetypes=[("Zip", "*.zip")])
            if path:
                dest = filedialog.askdirectory(title="Extract to…")
                if dest:
                    ok, msg = ops.extract_zip(Path(path), Path(dest))
                    self._log(msg)
            return
        dest = filedialog.askdirectory(title=f"Extract {zips[0].name} to…", initialdir=str(dl))
        if dest:
            ok, msg = ops.extract_zip(zips[0], Path(dest))
            self._log(msg)

    def _tool_dupes(self) -> None:
        roots = [core.downloads_dir(), Path.home() / "Documents", self.project_root.parent]
        dupes = checks.scan_duplicate_installs(roots)
        if not dupes:
            self._log("No duplicate installs found.")
            messagebox.showinfo("Duplicates", "No duplicate installs detected.")
            return
        for d in dupes:
            self._log(f"Duplicate: {d['path']} (newest: {d['newest']})")
        messagebox.showwarning(
            "Duplicates",
            f"Found {len(dupes)} older install(s).\nKeep newest: {dupes[0]['newest']}\n"
            "Use Clean reinstall on the copy you want to keep, or delete old folders manually.",
        )

    def _tool_clean(self) -> None:
        if not messagebox.askyesno(
            "Clean reinstall",
            "Remove tiles, kml cache, and build artifacts?\n\n"
            "Custom icons can be kept. You will need to re-extract or rebuild tiles.",
        ):
            return
        removed = ops.clean_install_artifacts(self.install_root, keep_icons=True)
        self._log(f"Cleaned {len(removed)} paths")

    def _tool_icons(self) -> None:
        pngs = ops.scan_downloads_for_icons()
        if not pngs:
            messagebox.showinfo("Icons", "No PNG files found in Downloads.")
            return
        copied = ops.import_pngs_from_folder(core.downloads_dir(), self.paths["icons_dir"])
        self._log(f"Imported {len(copied)} icon(s) → {self.paths['icons_dir']}")

    def _tool_import_pack(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Icon pack", "*.zip")])
        if not path:
            return
        import subprocess

        script = self.paths["scripts"] / "import_icon_pack.py"
        if not script.is_file():
            script = core.scripts_dir() / "import_icon_pack.py"
        result = subprocess.run(
            [core.python_cmd(), str(script), "--zip", path],
            cwd=str(self.paths["root"]),
            capture_output=True,
            text=True,
        )
        self._log(result.stdout.strip() or result.stderr.strip() or "Import finished")

    def _tool_shortcut(self) -> None:
        ok, msg = ops.create_desktop_shortcut(self.paths["entry_kml"], self.paths["scripts"])
        self._log(msg)

    def _tool_open_kml(self) -> None:
        ok, msg = ops.open_entry_kml(self.paths["entry_kml"])
        self._log(msg)

    def _tool_menu(self) -> None:
        ok, msg = ops.launch_player_menu(self.paths["scripts"])
        self._log(msg)

    def show_done(self) -> None:
        self._clear_body()
        frame = tk.Frame(self.body, bg=COLORS["bg"])
        frame.pack(expand=True)
        tk.Label(
            frame,
            text="READY FOR BATTLE",
            font=("Courier", 14, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["ok"],
        ).pack(pady=20)
        tk.Label(
            frame,
            text=(
                f"Entry KML:\n{self.paths['entry_kml']}\n\n"
                "Fully unzip before opening in Google Earth.\n"
                "Share icon packs with your opponent before turn 1."
            ),
            font=("Courier", 10),
            bg=COLORS["bg"],
            fg=COLORS["text"],
            justify="center",
        ).pack(pady=10)
        btn_row = tk.Frame(frame, bg=COLORS["bg"])
        btn_row.pack(pady=16)
        RetroButton(btn_row, "Open Google Earth", self._tool_open_kml).pack(side="left", padx=6)
        RetroButton(btn_row, "Player menu", self._tool_menu).pack(side="left", padx=6)
        RetroButton(btn_row, "Quit", self.destroy).pack(side="left", padx=6)


def run_wizard(project_root: Path | None = None) -> None:
    root = project_root or core.project_root_from_scripts()
    app = InstallerWizard(root)
    app.mainloop()