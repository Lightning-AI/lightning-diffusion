import subprocess
import threading
from lightning import LightningFlow, LightningWork, BuildConfig
from lightning.app.utilities.load_app import load_app_from_file
from watchfiles import watch, PythonFilter
import traceback
from time import sleep
from lightning.app.frontend.frontend import Frontend

class PythonWatcher(threading.Thread):

    def __init__(self, component):
        super().__init__(daemon=True)
        self.component = component

    def run(self):
        try:
            self.component.should_reload = True

            while self.component.should_reload:
                sleep(1)

            for _ in watch('.', watch_filter=PythonFilter(ignore_paths=[__file__])):

                self.component.should_reload = True

                while self.component.should_reload:
                    sleep(1)

        except Exception as e:
            print(traceback.print_exc())


class VSCodeBuildConfig(BuildConfig):
    def build_commands(self):
        return [
            "sudo apt update",
            "sudo apt install python3.8-venv",
            "curl -fsSL https://code-server.dev/install.sh | sh",
        ]


class VSCodeServer(LightningWork):
    def __init__(self):
        super().__init__(
            cloud_build_config=VSCodeBuildConfig(),
            parallel=True,
        )
        self.should_reload = False
        self._thread = None

    def run(self):
        self._thread = PythonWatcher(self)
        self._thread.start()
        # subprocess.call("mkdir ~/playground && cd ~/playground && python -m venv venv", shell=True)
        subprocess.call(f"code-server --auth=none . --bind-addr={self.host}:{self.port}", shell=True)

    def on_exit(self):
        self._thread.join(0)


class VSCodeFrontend(Frontend):

    def start_server(self, host: str, port: int, root_path: str = "") -> None:
        self._process = subprocess.Popen(f"code-server --auth=none . --bind-addr={host}:{port}", shell=True)

    def stop_server(self):
        self._process.kill()


class VSCodeFlow(LightningFlow):

    def __init__(self):
        super().__init__()

    def configure_layout(self):
        return VSCodeFrontend()


class VSCode(LightningFlow):

    def __init__(self, entrypoint_file: str):
        super().__init__()
        self.entrypoint_file = entrypoint_file
        self.flow = None
        self.vscode = VSCodeFlow()
        self.should_reload = False
        self._thread = None

    def run(self):
        if self._thread is None:
            self._thread = PythonWatcher(self)
            self._thread.start()

        if self.should_reload:

            if self.flow:
                for w in self.flow.works():
                    w.stop()

            try:
                new_flow = load_app_from_file(self.entrypoint_file).root
                new_flow = self.upgrade_fn(self.flow, new_flow)
                del self.flow
                self.flow = new_flow
            except Exception:
                print(traceback.print_exc())

            self.should_reload = False

        if self.flow:
            self.flow.run()

    def configure_layout(self):
        tabs = [{"name": "vscode", "content": self.vscode}]
        if self.flow:
            try:
                new_tabs = self.flow.configure_layout()
                # TODO: Validate new_tabs format.
                tabs += new_tabs
            except Exception:
                print(traceback.print_exc())
        return tabs

    def upgrade_fn(self, old_flow, new_flow):
        return new_flow