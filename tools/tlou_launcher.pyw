"""The Last of Us Remastered: game launcher (Tkinter, nothing to install).

Reads and writes the settings the game reads (analysis/tlou-user/tlou.ini, other keys stay as they
are), keeps its own switches in launcher.json beside it and starts tools/probe_tlou.py.
Usage: tlou_launcher.pyw [--seconds N] [--close-after S]   (for tests: a time limit for the game, and
for the launcher's window; default none)
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parent.parent
USER = ROOT / "analysis/tlou-user"
INI = USER / "tlou.ini"
SWITCHES = USER / "launcher.json"
LOG = ROOT / "analysis/tlou/boot.log"
RUN_LOG = ROOT / "analysis/tlou/launcher-run.log"
GAME = ROOT.parent / "CUSA00552"

FPS = ["30", "40", "45", "50", "55", "60", "75", "90", "100", "120"]
DISPLAY = {"borderless": "borderless", "fullscreen": "fullscreen", "windowed": "windowed"}   # text key: value
UPSCALERS = {"off": "off", "FSR 3": "fsr3", "TAA": "taa", "DLSS": "dlss"}
PRESETS = {"q_native": "0", "q_quality": "1", "q_balanced": "2", "q_performance": "3", "q_ultra": "4"}
RESOLUTIONS = ["1280x720", "1600x900", "1920x1080", "2560x1440", "3840x2160"]
DEFAULT_SWITCHES = {"motion_blur": False, "job_sleep": True, "profile": False}
DEFAULT_LANGUAGE = "pt"
# What Start-TLOU-Profile.cmd sets, for the "profiler" switch.
PROFILE_ENV = {"GOW3_PROFILE": "10", "GOW3_THREAD_IDS": "1", "GOW3_COMPUTE_WAIT_STATS": "1",
               "GOW3_FAULT_STATS": "1", "GOW3_FAULT_TIMES": "1", "GOW3_PROFILE_GUEST": "NdJobWorkerThread",
               "GOW3_SHARE_CHECK": "1", "GOW3_DUMP_DIR": str(ROOT / "analysis/tlou/profile-user")}

# Debug menu. Live: optimizations the game re-reads every 250 ms (gow3_toggles.h, a bit set in the
# file switches one off). The file lasts one run: probe_tlou.py deletes it at the start.
TOGGLE_FILE = USER / "disabled-optimizations.txt"
TOGGLES = [
    ("Memória", [
        ("Cache de regiões de memória", 1), ("Saída rápida do rastreio de páginas", 4),
        ("Limite de consulta de operações pendentes", 8), ("Leitura rastreada por página", 2048),
        ("Páginas quentes", 32768), ("Janela em torno da falha de escrita", 65536),
        ("Escritas de memória na gravação de draws", 1 << 42), ("Escritas do jogo em ordem", 1 << 49),
    ]),
    ("Threads e gravação", [
        ("Pipeline de draws em dois estágios", 1 << 37), ("Dispatches na thread de draws", 1 << 40),
        ("Draws indiretos na thread de draws", 1 << 46), ("Tarefas na thread de draws", 1 << 38),
        ("Gravação Vulkan em thread própria", 16), ("Preparação de draws em workers", 8192),
        ("Recursos preparados nos workers", 4096), ("Entradas de draw adiantadas", 1 << 35),
        ("Ajudante de texturas (causou bugs gráficos)", 1 << 34), ("Prefetch de gravação", 1 << 32),
    ]),
    ("Cópias e sincronização", [
        ("Uploads na thread de gravação", 256), ("Cópias curtas na thread de gravação", 16384),
        ("Cópias grandes em threads paralelas", 131072), ("Cópias curtas em lote", 524288),
        ("Fences assíncronas", 262144), ("Esperas de fence adiadas", 1 << 39), ("Fences na thread Vulkan", 1 << 41),
        ("Upload sem trava", 64), ("Anel de constantes", 1 << 36), ("Shader de cópia múltipla", 1 << 43),
    ]),
    ("Texturas e estado", [
        ("Cache de fetch shaders", 2), ("Cache de descritores de textura", 32), ("Cache de busca de imagens", 128),
        ("Memo de barreiras", 512), ("Memo de bind de texturas", 1024), ("Memo de views de textura", 1 << 33),
        ("Memo de estado de render", 1 << 44), ("Memo de conjuntos de textura", 1 << 45),
        ("Caminho rápido de UpdateImage", 1 << 30),
    ]),
]

# Startup: environment of the next run; only what differs from probe_tlou.py's defaults is passed.
# (label, variable, value on, value off, on by default)
STARTUP = [
    ("Threads", [
        ("Pipeline de draws", "GOW3_DRAW_PIPE", "1", "0", True),
        ("Gravação Vulkan em thread própria", "GOW3_VK_RECORD_THREAD", "1", "0", True),
        ("Prioridade alta nas threads da GPU", "GOW3_GPU_THREAD_PRIORITY", "above", "normal", True),
        ("Quadros em andamento", "GOW3_FRAMES_IN_FLIGHT", "1", "0", True),
        ("Menos esperas entre estágios", "GOW3_FEWER_DRAINS", "1", "0", True),
        ("Busca de dados sem bloquear", "GOW3_FETCH_NO_BLOCK", "1", "0", True),
        ("Timer de 1 ms", "GOW3_TIMER_RES", "1", "0", True),
        ("Sem limitação de energia", "GOW3_POWER_THROTTLE", "0", "1", True),
        ("Condition variables rápidas", "GOW3_FUTEX_COND", "1", "0", True),
        ("Reaproveitar buffers de draws", "GOW3_PREP_POOL", "1", "0", True),
        ("Economias por draw", "GOW3_CPU_TRIMS", "1", "0", True),
        ("Ajudante de texturas (causou bugs gráficos)", "GOW3_TEXTURE_HELPER", "1", "0", False),
    ]),
    ("Memória e leitura da GPU", [
        ("Escritas ao lado de dados da GPU sem espera", "GOW3_SHARE_UNFINISHED_WRITES", "1", "0", True),
        ("Resultados de DMA no fim do pipe", "GOW3_DMA_EOP_READBACK", "1", "0", True),
        ("Cópia de imagens minúsculas (foco da mira)", "GOW3_TINY_IMAGE_READBACK", "1", "0", True),
        ("Acesso direto à memória", "GOW3_DIRECT_MEMORY_ACCESS", "1", "0", True),
        ("TSC nativo", "GOW3_NATIVE_TSC", "1", "0", True),
        ("Buffer grande de staging reservado", "GOW3_STAGING_LARGE_MB", "128", "0", True),
    ]),
    ("Shaders e proteção", [
        ("Cache de pipelines", "GOW3_PIPELINE_CACHE", "1", "0", True),
        ("Binários de pipeline", "GOW3_PIPELINE_BINARIES", "1", "0", True),
        ("Prefetch de pipelines", "GOW3_PREFETCH_PIPELINES", "1", "0", True),
        ("Proteção da red zone", "GOW3_RED_ZONE_REWRITE", "1", "0", True),
    ]),
]

# The art is the player's own dump's (sce_sys), read at run time: no game file in the repository.
ART = [GAME / "sce_sys/pic1.png", GAME / "sce_sys/pic0.png"]
UI_LANGUAGES = {"pt": "Português", "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch",
                "it": "Italiano", "pl": "Polski", "ru": "Русский", "ja": "日本語"}
KEYS = ("subtitle video game language ui_language display resolution fps upscaler quality vsync show_fps "
        "motion_blur job_sleep profile play running starting ready debug log no_game no_exe borderless fullscreen "
        "windowed off q_native q_quality q_balanced q_performance q_ultra warn tab_live tab_startup note_live "
        "note_startup reset").split()
TEXT_TABLE = {
    "pt": ["Port para PC", "Vídeo", "Jogo", "Idioma", "Idioma do launcher", "Modo de tela", "Resolução",
           "Limite de FPS", "Upscaler", "Qualidade do upscaler", "VSync", "Mostrar FPS no jogo", "Motion blur",
           "Reduzir uso de CPU ocioso", "Gravar perfil de desempenho (cerca de 10% menos FPS)", "JOGAR", "EM EXECUÇÃO",
           "INICIANDO...", "Pronto", "Debug", "Abrir log", "Jogo não encontrado em {}",
           "Executável não encontrado: rode gow3_pc/build.sh", "Sem borda", "Tela cheia", "Janela", "Desligado", "Nativo",
           "Qualidade", "Equilibrado", "Desempenho", "Ultra desempenho",
           "Para diagnóstico. Algumas opções podem travar o jogo ou causar bugs gráficos.", "Ao vivo", "Ao iniciar",
           "Valem na hora, com o jogo aberto, e duram só esta execução.", "Valem a partir da próxima vez que o jogo abrir.",
           "Restaurar padrão"],
    "en": ["PC port", "Video", "Game", "Language", "Launcher language", "Display mode", "Resolution",
           "FPS limit", "Upscaler", "Upscaler quality", "VSync", "Show FPS in game", "Motion blur",
           "Reduce idle CPU use", "Record a performance profile (about 10% fewer FPS)", "PLAY", "RUNNING", "STARTING...",
           "Ready", "Debug", "Open log", "Game not found in {}", "Executable not found: run gow3_pc/build.sh", "Borderless",
           "Fullscreen", "Windowed", "Off", "Native", "Quality", "Balanced", "Performance", "Ultra performance",
           "For diagnostics. Some options may hang the game or cause graphics bugs.", "Live", "At start",
           "Apply at once, with the game open, for this run only.", "Apply the next time the game opens.",
           "Restore defaults"],
    "es": ["Port para PC", "Vídeo", "Juego", "Idioma", "Idioma del launcher", "Modo de pantalla",
           "Resolución", "Límite de FPS", "Upscaler", "Calidad del upscaler", "VSync", "Mostrar FPS en el juego",
           "Desenfoque de movimiento", "Reducir el uso de CPU inactiva",
           "Grabar perfil de rendimiento (cerca de 10% menos FPS)", "JUGAR", "EN EJECUCIÓN", "INICIANDO...", "Listo", "Debug",
           "Abrir registro", "Juego no encontrado en {}", "Ejecutable no encontrado: ejecuta gow3_pc/build.sh", "Sin bordes",
           "Pantalla completa", "Ventana", "Desactivado", "Nativo", "Calidad", "Equilibrado", "Rendimiento",
           "Ultra rendimiento", "Para diagnóstico. Algunas opciones pueden bloquear el juego o causar errores gráficos.",
           "En vivo", "Al iniciar", "Se aplican al momento, con el juego abierto, solo en esta ejecución.",
           "Se aplican la próxima vez que se abra el juego.", "Restaurar valores"],
    "fr": ["Portage PC", "Vidéo", "Jeu", "Langue", "Langue du launcher", "Mode d'affichage", "Résolution",
           "Limite d'IPS", "Upscaler", "Qualité de l'upscaler", "VSync", "Afficher les IPS en jeu", "Flou de mouvement",
           "Réduire l'usage du CPU au repos", "Enregistrer un profil de performance (environ 10 % d'IPS en moins)", "JOUER",
           "EN COURS", "DÉMARRAGE...", "Prêt", "Debug", "Ouvrir le journal", "Jeu introuvable dans {}",
           "Exécutable introuvable : lancez gow3_pc/build.sh", "Sans bordure", "Plein écran", "Fenêtré", "Désactivé", "Natif",
           "Qualité", "Équilibré", "Performance", "Ultra performance",
           "Pour le diagnostic. Certaines options peuvent bloquer le jeu ou causer des bugs graphiques.", "En direct",
           "Au démarrage", "S'appliquent tout de suite, jeu ouvert, pour cette session seulement.",
           "S'appliquent à la prochaine ouverture du jeu.", "Rétablir les valeurs"],
    "de": ["PC-Port", "Video", "Spiel", "Sprache", "Launcher-Sprache", "Anzeigemodus", "Auflösung", "FPS-Limit",
           "Upscaler", "Upscaler-Qualität", "VSync", "FPS im Spiel anzeigen", "Bewegungsunschärfe",
           "CPU-Last im Leerlauf senken", "Leistungsprofil aufzeichnen (etwa 10 % weniger FPS)", "SPIELEN", "LÄUFT",
           "STARTET...", "Bereit", "Debug", "Log öffnen", "Spiel nicht gefunden in {}",
           "Programmdatei nicht gefunden: gow3_pc/build.sh ausführen", "Randlos", "Vollbild", "Fenster", "Aus", "Nativ",
           "Qualität", "Ausgewogen", "Leistung", "Ultra-Leistung",
           "Zur Diagnose. Manche Optionen können das Spiel einfrieren oder Grafikfehler verursachen.", "Live", "Beim Start",
           "Gelten sofort bei laufendem Spiel, nur für diesen Start.", "Gelten beim nächsten Spielstart.",
           "Standard wiederherstellen"],
    "it": ["Port per PC", "Video", "Gioco", "Lingua", "Lingua del launcher", "Modalità schermo",
           "Risoluzione", "Limite FPS", "Upscaler", "Qualità dell'upscaler", "VSync", "Mostra FPS in gioco",
           "Sfocatura di movimento", "Riduci l'uso della CPU inattiva",
           "Registra profilo prestazioni (circa 10% di FPS in meno)", "GIOCA", "IN ESECUZIONE", "AVVIO...", "Pronto", "Debug",
           "Apri log", "Gioco non trovato in {}", "Eseguibile non trovato: esegui gow3_pc/build.sh", "Senza bordi",
           "Schermo intero", "Finestra", "Disattivato", "Nativo", "Qualità", "Bilanciato", "Prestazioni", "Ultra prestazioni",
           "Per la diagnostica. Alcune opzioni possono bloccare il gioco o causare errori grafici.", "Dal vivo", "All'avvio",
           "Valgono subito, a gioco aperto, solo per questa esecuzione.", "Valgono al prossimo avvio del gioco.",
           "Ripristina predefiniti"],
    "pl": ["Port na PC", "Obraz", "Gra", "Język", "Język launchera", "Tryb ekranu", "Rozdzielczość", "Limit FPS",
           "Upscaler", "Jakość upscalera", "VSync", "Pokazuj FPS w grze", "Rozmycie ruchu", "Mniejsze użycie CPU w bezczynności",
           "Nagrywaj profil wydajności (około 10% mniej FPS)", "GRAJ", "URUCHOMIONO", "URUCHAMIANIE...", "Gotowe", "Debug",
           "Otwórz log", "Nie znaleziono gry w {}", "Nie znaleziono pliku wykonywalnego: uruchom gow3_pc/build.sh",
           "Bez ramek", "Pełny ekran", "Okno", "Wyłączone", "Natywna", "Jakość", "Zrównoważona", "Wydajność", "Ultra wydajność",
           "Do diagnostyki. Niektóre opcje mogą zawiesić grę lub powodować błędy grafiki.", "Na żywo", "Przy starcie",
           "Działają od razu, przy otwartej grze, tylko w tym uruchomieniu.", "Działają od następnego uruchomienia gry.",
           "Przywróć domyślne"],
    "ru": ["Порт для ПК", "Видео", "Игра", "Язык", "Язык лаунчера", "Режим экрана", "Разрешение", "Лимит FPS",
           "Апскейлер", "Качество апскейлера", "VSync", "Показывать FPS в игре", "Размытие в движении",
           "Снизить нагрузку на ЦП в простое", "Записывать профиль производительности (примерно на 10% меньше FPS)", "ИГРАТЬ",
           "ЗАПУЩЕНО", "ЗАПУСК...", "Готово", "Отладка", "Открыть журнал", "Игра не найдена в {}",
           "Исполняемый файл не найден: запустите gow3_pc/build.sh", "Без рамки", "Полный экран", "В окне", "Выключено",
           "Родное", "Качество", "Баланс", "Производительность", "Ультрапроизводительность",
           "Для диагностики. Некоторые параметры могут привести к зависанию или графическим ошибкам.", "На лету", "При запуске",
           "Применяются сразу, при открытой игре, только на этот запуск.", "Применяются при следующем запуске игры.",
           "Восстановить значения"],
    "ja": ["PC移植版", "映像", "ゲーム", "言語", "ランチャーの言語", "表示モード", "解像度", "FPS上限", "アップスケーラー",
           "アップスケーラーの品質", "VSync", "ゲーム内にFPSを表示", "モーションブラー", "待機時のCPU使用を減らす",
           "パフォーマンスプロファイルを記録(FPSが約10%低下)", "プレイ", "実行中", "起動中...", "準備完了", "デバッグ", "ログを開く",
           "ゲームが見つかりません: {}", "実行ファイルが見つかりません: gow3_pc/build.sh を実行してください", "ボーダーレス", "フルスクリーン",
           "ウィンドウ", "オフ", "ネイティブ", "品質", "バランス", "パフォーマンス", "ウルトラパフォーマンス",
           "診断用です。一部のオプションはゲームの停止や表示の不具合を起こす場合があります。", "ライブ", "起動時",
           "ゲーム実行中にすぐ反映され、今回の実行のみ有効です。", "次回ゲームを開いたときに反映されます。", "初期設定に戻す"],
}
TEXTS = {code: dict(zip(KEYS, values)) for code, values in TEXT_TABLE.items()}

BG, PANEL, TEXT, MUTED, ACCENT, ACCENT_HOT = "#090909", "#141414", "#ece9e2", "#8f8f88", "#c8862a", "#e4a23f"
DISABLED, ERROR = "#2b2b2b", "#e06c5a"


def read_ini(path=None):
    """{key: value} of the settings file; {} when it does not exist yet."""
    path = path or INI
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def write_ini(changes, path=None):
    """Sets these keys in place; every other line, comments included, stays as it is."""
    path = path or INI
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    left = dict(changes)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in left:
            lines[i] = f"{key}={left.pop(key)}"
    lines += [f"{key}={value}" for key, value in left.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def read_switches(path=None):
    path = path or SWITCHES
    values = dict(DEFAULT_SWITCHES)
    try:
        values.update({k: bool(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()
                       if k in DEFAULT_SWITCHES})
    except (OSError, ValueError):
        pass
    return values


def read_overrides(path=None):
    """The debug menu's startup options that differ from their defaults: {variable: value}."""
    known = {option[1]: option[2:4] for _, options in STARTUP for option in options}
    try:
        saved = json.loads((path or SWITCHES).read_text(encoding="utf-8")).get("overrides", {})
    except (OSError, ValueError, AttributeError):
        return {}
    return {k: v for k, v in saved.items() if k in known and v in known[k]}


def read_ui_language(path=None):
    try:
        saved = json.loads((path or SWITCHES).read_text(encoding="utf-8")).get("ui_language")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_LANGUAGE
    return saved if saved in TEXTS else DEFAULT_LANGUAGE


def load_art(width, height):
    """The dump's key art, covering width x height and kept to its right edge; None without it."""
    path = next((p for p in ART if p.is_file()), None)
    if path is None:
        return None
    try:
        from PIL import Image, ImageTk
        image = Image.open(path).convert("RGB")
        scale = max(width / image.width, height / image.height)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
        left, top = image.width - width, (image.height - height) // 2
        return ImageTk.PhotoImage(image.crop((left, top, left + width, top + height)))
    except ImportError:
        return tk.PhotoImage(file=str(path)).zoom(2).subsample(3)   # 1920x1080 -> 1280x720
    except (OSError, ValueError):
        return None


def toggle_mask(disabled):
    return sum(set(disabled))


def write_toggles(mask, path=None):
    """Writes the live toggles for the running game (read every 250 ms)."""
    path = path or TOGGLE_FILE
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(str(mask), encoding="ascii")
    os.replace(temporary, path)


def game_env(switches, base=None, overrides=None):
    """The environment of a run with these switches."""
    env = dict(os.environ if base is None else base)
    env.update(overrides or {})
    env["GOW3_NO_MOTION_BLUR"] = "0" if switches["motion_blur"] else "1"
    env["TLOU_JOB_SLEEP"] = "1" if switches["job_sleep"] else "0"
    if switches["profile"]:
        env.update(PROFILE_ENV)
    return env


def python_exe():
    """python.exe beside this interpreter (pythonw has no output for the scripts it runs)."""
    candidate = Path(sys.executable).with_name("python.exe")
    return str(candidate if candidate.is_file() else sys.executable)


def game_running():
    no_window = 0x08000000
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq gow3-probe.exe", "/NH"], capture_output=True,
                             text=True, errors="replace", creationflags=no_window).stdout
    except OSError:
        return False
    return "gow3-probe" in out


def key_for(options, value, fallback):
    return next((label for label, v in options.items() if v == value), fallback)


class Launcher(tk.Tk):
    WIDTH, HEIGHT = 1180, 636

    def __init__(self, seconds=0):
        super().__init__()
        self.seconds = seconds
        self.process = None
        self.overrides = read_overrides()
        self.disabled = set()   # live toggles switched off in the debug menu
        self.was_running = False
        self.debug_window = None
        self.language = read_ui_language()
        self.title("The Last of Us Remastered")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.art = load_art(self.WIDTH, self.HEIGHT)
        self.style()
        self.ready_message = None
        self.build()
        self.refresh()

    def t(self, key):
        return TEXTS[self.language][key]

    def labels(self, options):
        """{text on screen: value} of a table keyed by text keys (other keys are shown as they are)."""
        return {self.t(k) if k in KEYS else k: v for k, v in options.items()}

    def build(self):
        """The whole window: called again when the launcher's language changes."""
        for child in self.winfo_children():
            if child is not self.debug_window:
                child.destroy()
        ini, switches = read_ini(), read_switches()
        canvas = self.canvas = tk.Canvas(self, width=self.WIDTH, height=self.HEIGHT, bg=BG, highlightthickness=0)
        canvas.place(x=0, y=0)
        if self.art:
            canvas.create_image(self.WIDTH, 0, image=self.art, anchor="ne")
        x = 44
        canvas.create_text(x, 30, text="THE LAST OF US", anchor="nw", fill=TEXT, font=("Segoe UI Light", 32))
        canvas.create_text(x + 2, 84, text=f"REMASTERED   ·   {self.t('subtitle')}", anchor="nw", fill=ACCENT,
                           font=("Segoe UI Semibold", 10))

        panel = tk.Frame(self, bg=BG)
        panel.place(x=x, y=124, width=460)
        panel.columnconfigure(1, weight=1)
        row = self.section(panel, 0, self.t("language"))
        self.ui_labels = {name: code for code, name in UI_LANGUAGES.items()}
        self.ui_language = self.choice(panel, row, self.t("ui_language"), list(self.ui_labels),
                                       UI_LANGUAGES[self.language], self.change_language)
        row = self.section(panel, row + 1, self.t("video"))
        self.display_labels = self.labels(DISPLAY)
        self.display = self.choice(panel, row, self.t("display"), list(self.display_labels),
                                   key_for(self.display_labels, ini.get("display_mode"), self.t("borderless")))
        res = ini.get("output_res", "1920x1080")
        self.resolution = self.choice(panel, row + 1, self.t("resolution"),
                                      RESOLUTIONS + ([res] if res not in RESOLUTIONS else []), res)
        fps = ini.get("fps_limit", "60")
        self.fps = self.choice(panel, row + 2, self.t("fps"), FPS if fps in FPS else FPS + [fps], fps)
        self.upscaler_labels = self.labels(UPSCALERS)
        self.upscaler = self.choice(panel, row + 3, self.t("upscaler"), list(self.upscaler_labels),
                                    key_for(self.upscaler_labels, ini.get("upscaler"), self.t("off")))
        self.preset_labels = self.labels(PRESETS)
        self.preset = self.choice(panel, row + 4, self.t("quality"), list(self.preset_labels),
                                  key_for(self.preset_labels, ini.get("preset"), self.t("q_native")))
        self.vsync = self.check(panel, row + 5, self.t("vsync"), ini.get("vsync", "0") == "1")
        self.show_fps = self.check(panel, row + 6, self.t("show_fps"), ini.get("show_fps", "1") == "1")
        row = self.section(panel, row + 7, self.t("game"))
        self.motion_blur = self.check(panel, row, self.t("motion_blur"), switches["motion_blur"])
        self.job_sleep = self.check(panel, row + 1, self.t("job_sleep"), switches["job_sleep"])
        self.profile = self.check(panel, row + 2, self.t("profile"), switches["profile"])

        self.play_button = tk.Button(self, text=self.t("play"), command=self.play, bg=ACCENT, fg=BG,
                                     activebackground=ACCENT_HOT, activeforeground=BG, bd=0, relief="flat",
                                     font=("Segoe UI Semibold", 15), cursor="hand2", disabledforeground="#77756f")
        self.play_button.place(x=self.WIDTH - 300, y=self.HEIGHT - 88, width=256, height=52)
        self.status = canvas.create_text(self.WIDTH - 300, self.HEIGHT - 26, anchor="w", fill=MUTED, font=("Segoe UI", 9))
        self.link(canvas, self.WIDTH - 44, self.t("debug"), self.open_debug)
        self.link(canvas, self.WIDTH - 104, self.t("log"), self.open_log)
        self.ready_message = self.check_install()

    def style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=ACCENT,
                        bordercolor="#2c2c2c", lightcolor=PANEL, darkcolor=PANEL, selectbackground=PANEL,
                        selectforeground=TEXT, padding=3)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", TEXT)],
                  bordercolor=[("focus", ACCENT), ("hover", "#555")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(12, 5), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#222")], foreground=[("selected", TEXT)])
        style.configure("Vertical.TScrollbar", background="#2c2c2c", troughcolor=PANEL, arrowcolor=MUTED, bordercolor=PANEL)
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)

    def section(self, parent, row, title):
        tk.Label(parent, text=title.upper(), bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 9)).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 3))
        return row + 1

    def choice(self, parent, row, text, values, current, command=None):
        tk.Label(parent, text=text, bg=BG, fg=TEXT, font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=2)
        variable = tk.StringVar(value=current)
        box = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=24)
        box.grid(row=row, column=1, sticky="e", pady=2)
        box.bind("<<ComboboxSelected>>", lambda _: (box.selection_clear(), (command or self.save)()))
        return variable

    def check(self, parent, row, text, value):
        variable = tk.BooleanVar(value=value)
        tk.Checkbutton(parent, text=text, variable=variable, command=self.save, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT, font=("Segoe UI", 10), bd=0,
                       highlightthickness=0, anchor="w").grid(row=row, column=0, columnspan=2, sticky="w")
        return variable

    def link(self, canvas, x, text, command):
        item = canvas.create_text(x, self.HEIGHT - 26, text=text, anchor="e", fill=ACCENT, font=("Segoe UI", 9, "underline"))
        canvas.tag_bind(item, "<Button-1>", lambda _: command())
        canvas.tag_bind(item, "<Enter>", lambda _: canvas.configure(cursor="hand2"))
        canvas.tag_bind(item, "<Leave>", lambda _: canvas.configure(cursor=""))

    def change_language(self):
        self.language = self.ui_labels[self.ui_language.get()]
        self.save()
        window = self.debug_window
        if window is not None and window.winfo_exists():
            window.destroy()
        self.build()

    def check_install(self):
        if not (GAME / "eboot.bin").is_file():
            return self.t("no_game").format(GAME)
        if not (ROOT / "gow3_pc/out/gow3-probe.exe").is_file():
            return self.t("no_exe")
        return ""

    def switches(self):
        return {"motion_blur": self.motion_blur.get(), "job_sleep": self.job_sleep.get(), "profile": self.profile.get()}

    def save(self):
        write_ini({"display_mode": self.display_labels[self.display.get()], "output_res": self.resolution.get(),
                   "fps_limit": self.fps.get(), "upscaler": self.upscaler_labels[self.upscaler.get()],
                   "preset": self.preset_labels[self.preset.get()], "vsync": int(self.vsync.get()),
                   "show_fps": int(self.show_fps.get())})
        SWITCHES.write_text(json.dumps({**self.switches(), "ui_language": self.language, "overrides": self.overrides},
                                       indent=2) + "\n", encoding="utf-8")

    def refresh(self):
        """Keeps JOGAR and the status line current, also for a game started some other way."""
        def check():
            running = self.process is not None and self.process.poll() is None or game_running()
            self.after(0, lambda: self.show_state(running))
        threading.Thread(target=check, daemon=True).start()
        self.after(2000, self.refresh)

    def show_state(self, running):
        # probe_tlou.py deleted the file at the start: the menu's choices go back once it runs.
        if running and not self.was_running and self.disabled:
            self.after(3000, lambda: write_toggles(toggle_mask(self.disabled)))
        self.was_running = running
        if self.ready_message:
            self.canvas.itemconfigure(self.status, text=self.ready_message, fill=ERROR)
            self.play_button.config(state="disabled", text=self.t("play"), bg=DISABLED)
        elif running:
            self.canvas.itemconfigure(self.status, text=self.t("running").capitalize(), fill=MUTED)
            self.play_button.config(state="disabled", text=self.t("running"), bg=DISABLED)
        else:
            self.canvas.itemconfigure(self.status, text=self.t("ready"), fill=MUTED)
            self.play_button.config(state="normal", text=self.t("play"), bg=ACCENT)

    def play(self):
        self.save()
        self.play_button.config(state="disabled", text=self.t("starting"), bg=DISABLED)
        env = game_env(self.switches(), overrides=self.overrides)
        if self.profile.get():
            Path(PROFILE_ENV["GOW3_DUMP_DIR"]).mkdir(parents=True, exist_ok=True)
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RUN_LOG.open("w", encoding="utf-8") as output:
            self.process = subprocess.Popen(
                [python_exe(), "tools/probe_tlou.py", "--boot", "--seconds", str(self.seconds)], cwd=ROOT, env=env,
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=0x08000000)

    def open_debug(self):
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()
            return
        self.debug_window = window = tk.Toplevel(self, bg=BG)
        window.title(self.t("debug"))
        window.geometry(f"640x640+{self.winfo_rootx() + 40}+{self.winfo_rooty() + 20}")
        tk.Label(window, text=self.t("warn"), bg=BG, fg=ERROR, font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(12, 8))
        tabs = ttk.Notebook(window)
        tabs.pack(fill="both", expand=True, padx=14)
        self.live_tab(tabs)
        self.startup_tab(tabs)

    def scroll_area(self, tabs, title, note):
        outer = tk.Frame(tabs, bg=PANEL)
        tabs.add(outer, text=title)
        tk.Label(outer, text=note, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=10, pady=(8, 4))
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=PANEL)
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.bind("<Enter>", lambda _: canvas.bind_all(
            "<MouseWheel>", lambda e: canvas.winfo_exists() and canvas.yview_scroll(-e.delta // 120, "units")))
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 8))
        return outer, body

    def group(self, body, title):
        tk.Label(body, text=title, bg=PANEL, fg=ACCENT, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(8, 2))

    def option(self, body, text, variable, command):
        tk.Checkbutton(body, text=text, variable=variable, command=command, bg=PANEL, fg=TEXT, selectcolor=BG,
                       activebackground=PANEL, activeforeground=TEXT, font=("Segoe UI", 10), bd=0,
                       highlightthickness=0, anchor="w").pack(anchor="w")

    def reset_link(self, outer, command):
        button = tk.Button(outer, text=self.t("reset"), command=command, bg=BG, fg=TEXT, bd=0, cursor="hand2",
                           activebackground=BG, activeforeground=ACCENT, font=("Segoe UI", 9))
        button.place(relx=1.0, x=-30, y=6, anchor="ne")

    def live_tab(self, tabs):
        outer, body = self.scroll_area(tabs, self.t("tab_live"), self.t("note_live"))
        variables = {}

        def apply(bit):
            (self.disabled.discard if variables[bit].get() else self.disabled.add)(bit)
            write_toggles(toggle_mask(self.disabled))

        for title, items in TOGGLES:
            self.group(body, title)
            for text, bit in items:
                variables[bit] = tk.BooleanVar(value=bit not in self.disabled)
                self.option(body, text, variables[bit], lambda b=bit: apply(b))

        def reset():
            self.disabled.clear()
            write_toggles(0)
            for variable in variables.values():
                variable.set(True)

        self.reset_link(outer, reset)

    def startup_tab(self, tabs):
        outer, body = self.scroll_area(tabs, self.t("tab_startup"), self.t("note_startup"))
        variables = {}

        def apply(option):
            name, on_value, off_value, default = option[1:]
            wanted = variables[name].get()
            if wanted == default:
                self.overrides.pop(name, None)
            else:
                self.overrides[name] = on_value if wanted else off_value
            self.save()

        for title, items in STARTUP:
            self.group(body, title)
            for option in items:
                text, name, on_value, _, default = option
                current = self.overrides.get(name)
                variables[name] = tk.BooleanVar(value=default if current is None else current == on_value)
                self.option(body, text, variables[name], lambda o=option: apply(o))

        def reset():
            self.overrides.clear()
            self.save()
            for _, items in STARTUP:
                for _, name, _, _, default in items:
                    variables[name].set(default)

        self.reset_link(outer, reset)

    def open_log(self):
        if LOG.is_file():
            os.startfile(LOG)


def main():
    seconds = 0
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    app = Launcher(seconds)
    if "--close-after" in sys.argv:
        app.after(int(sys.argv[sys.argv.index("--close-after") + 1]) * 1000, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
