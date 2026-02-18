import csv
import importlib
import json
import sys
import types
from pathlib import Path


def _ensure_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is not None:
        return module

    try:
        return importlib.import_module(name)
    except ImportError:
        pass

    module = types.ModuleType(name)
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        parent = _ensure_module(parent_name)
        if not hasattr(parent, "__path__"):
            parent.__path__ = []
        setattr(parent, child_name, module)
    else:
        module.__path__ = []

    sys.modules[name] = module
    return module


def _install_numpy_stub() -> None:
    numpy = _ensure_module("numpy")
    numpy.integer = int
    numpy.floating = float
    numpy.nan = float("nan")


def _install_pandas_stub() -> None:
    pandas = _ensure_module("pandas")

    class Series(list):
        def apply(self, fn):
            return Series(fn(value) for value in self)

    class DataFrame:
        def __init__(self, data=None):
            self.columns = []
            self._rows = []

            if data is None:
                return
            if isinstance(data, DataFrame):
                self.columns = list(data.columns)
                self._rows = [dict(row) for row in data._rows]
                return

            if isinstance(data, dict):
                self.columns = list(data.keys())
                column_values = {k: list(v) for k, v in data.items()}
                row_count = max((len(v) for v in column_values.values()), default=0)
                for row_idx in range(row_count):
                    row = {}
                    for col in self.columns:
                        values = column_values[col]
                        row[col] = values[row_idx] if row_idx < len(values) else None
                    self._rows.append(row)
                return

            if isinstance(data, list):
                if not data:
                    return

                first = data[0]
                if isinstance(first, dict):
                    self.columns = list(first.keys())
                    for row in data:
                        self._rows.append({col: row.get(col) for col in self.columns})
                    return

                if isinstance(first, (list, tuple)):
                    self.columns = [str(i) for i in range(len(first))]
                    for row in data:
                        self._rows.append({str(i): row[i] for i in range(len(first))})
                    return

            raise TypeError(f"Unsupported DataFrame input: {type(data)!r}")

        @property
        def values(self):
            return [[row.get(col) for col in self.columns] for row in self._rows]

        def to_dict(self, orient="records"):
            if orient != "records":
                raise ValueError("Only orient='records' is supported in test stub")
            return [dict(row) for row in self._rows]

        def __getitem__(self, column):
            return Series([row.get(column) for row in self._rows])

        def __setitem__(self, column, values):
            if column not in self.columns:
                self.columns.append(column)

            if isinstance(values, Series):
                values = list(values)
            if isinstance(values, (list, tuple)):
                if len(values) != len(self._rows):
                    raise ValueError("Column assignment length mismatch")
                for idx, row in enumerate(self._rows):
                    row[column] = values[idx]
                return

            for row in self._rows:
                row[column] = values

        def __len__(self):
            return len(self._rows)

        def __repr__(self):
            return f"DataFrame(columns={self.columns!r}, rows={len(self._rows)})"

    def read_csv(path, *args, **kwargs):
        with Path(path).open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        return DataFrame(rows)

    def read_json(path, *args, **kwargs):
        payload = json.loads(Path(path).read_text())
        if isinstance(payload, list):
            return DataFrame(payload)
        if isinstance(payload, dict):
            return DataFrame(payload)
        raise ValueError("Unsupported JSON payload")

    pandas.Series = Series
    pandas.DataFrame = DataFrame
    pandas.read_csv = read_csv
    pandas.read_json = read_json


def _install_typer_stub() -> None:
    typer = _ensure_module("typer")

    class Exit(Exception):
        def __init__(self, code=0):
            self.code = code
            super().__init__(code)

    class Context:
        invoked_subcommand = None

    class Typer:
        def __init__(self, *args, **kwargs):
            pass

        def command(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def callback(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def __call__(self, *args, **kwargs):
            return None

    def Option(default=None, *args, **kwargs):
        return default

    def Argument(default=None, *args, **kwargs):
        return default

    typer.Exit = Exit
    typer.Context = Context
    typer.Typer = Typer
    typer.Option = Option
    typer.Argument = Argument


def _install_rich_stub() -> None:
    _ensure_module("rich")
    rich_console = _ensure_module("rich.console")
    rich_panel = _ensure_module("rich.panel")
    rich_table = _ensure_module("rich.table")
    rich_text = _ensure_module("rich.text")

    class Console:
        def __init__(self, *args, **kwargs):
            pass

        def print(self, *args, **kwargs):
            return None

    class Panel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def fit(cls, *args, **kwargs):
            return cls(*args, **kwargs)

    class Table:
        def __init__(self, *args, **kwargs):
            self.columns = []
            self.rows = []

        def add_column(self, *args, **kwargs):
            self.columns.append((args, kwargs))

        def add_row(self, *args, **kwargs):
            self.rows.append((args, kwargs))

    class Text:
        def __init__(self, text="", *args, **kwargs):
            self.parts = [text]

        def append(self, text, style=None):
            self.parts.append(text)

        def __str__(self):
            return "".join(self.parts)

    rich_console.Console = Console
    rich_panel.Panel = Panel
    rich_table.Table = Table
    rich_text.Text = Text


def _install_plotly_stub() -> None:
    _ensure_module("plotly")
    plotly_io = _ensure_module("plotly.io")
    graph_objects = _ensure_module("plotly.graph_objects")

    class Figure:
        def __init__(self, *args, **kwargs):
            pass

        def add_trace(self, *args, **kwargs):
            return None

        def update_layout(self, *args, **kwargs):
            return None

        def to_image(self, *args, **kwargs):
            return b""

    plotly_io.to_image = lambda *args, **kwargs: b""
    graph_objects.Figure = Figure


def _install_google_stubs() -> None:
    google = _ensure_module("google")
    oauth2 = _ensure_module("google.oauth2")
    service_account_mod = _ensure_module("google.oauth2.service_account")

    class Credentials:
        @classmethod
        def from_service_account_info(cls, *args, **kwargs):
            return cls()

        @classmethod
        def from_service_account_file(cls, *args, **kwargs):
            return cls()

    service_account_mod.Credentials = Credentials
    oauth2.service_account = service_account_mod

    genai = _ensure_module("google.genai")
    genai_types = _ensure_module("google.genai.types")

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _Response:
        text = "stub-response"

    class Client:
        def __init__(self, *args, **kwargs):
            self.models = self

        def generate_content(self, *args, **kwargs):
            return _Response()

    genai.Client = Client
    genai_types.GenerateContentConfig = GenerateContentConfig
    genai.types = genai_types
    google.genai = genai


def _install_google_api_client_stub() -> None:
    googleapiclient = _ensure_module("googleapiclient")
    discovery = _ensure_module("googleapiclient.discovery")
    errors = _ensure_module("googleapiclient.errors")
    http = _ensure_module("googleapiclient.http")

    class _Service:
        def __getattr__(self, name):
            return self

        def __call__(self, *args, **kwargs):
            return self

        def execute(self):
            return {}

    class HttpError(Exception):
        pass

    class MediaIoBaseUpload:
        def __init__(self, *args, **kwargs):
            pass

    discovery.build = lambda *args, **kwargs: _Service()
    errors.HttpError = HttpError
    http.MediaIoBaseUpload = MediaIoBaseUpload

    googleapiclient.discovery = discovery
    googleapiclient.errors = errors
    googleapiclient.http = http


def _install_openai_stub() -> None:
    openai = _ensure_module("openai")

    class APIError(Exception):
        pass

    class RateLimitError(APIError):
        pass

    class AuthenticationError(APIError):
        pass

    class _Message:
        content = "ok"

    class _Choice:
        message = _Message()

    class _ChatCompletions:
        def create(self, *args, **kwargs):
            return types.SimpleNamespace(choices=[_Choice()])

    class _Chat:
        completions = _ChatCompletions()

    class OpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _Chat()

    openai.APIError = APIError
    openai.RateLimitError = RateLimitError
    openai.AuthenticationError = AuthenticationError
    openai.OpenAI = OpenAI


def _install_git_stub() -> None:
    git = _ensure_module("git")

    class Repo:
        @staticmethod
        def clone_from(*args, **kwargs):
            return None

    git.Repo = Repo


def _install_dbt_stub() -> None:
    _ensure_module("dbt")
    _ensure_module("dbt.cli")
    dbt_cli_main = _ensure_module("dbt.cli.main")

    class dbtRunner:
        def invoke(self, *args, **kwargs):
            return types.SimpleNamespace(success=True)

    dbt_cli_main.dbtRunner = dbtRunner


def _install_databricks_stub() -> None:
    databricks = _ensure_module("databricks")
    databricks_sql = _ensure_module("databricks.sql")

    class _ArrowResult:
        def to_pandas(self):
            import pandas as pd

            return pd.DataFrame([])

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchall_arrow(self):
            return _ArrowResult()

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def cursor(self):
            return _Cursor()

    databricks_sql.connect = lambda *args, **kwargs: _Connection()
    databricks.sql = databricks_sql


def pytest_configure(config):
    _install_numpy_stub()
    _install_pandas_stub()
    _install_typer_stub()
    _install_rich_stub()
    _install_plotly_stub()
    _install_google_stubs()
    _install_google_api_client_stub()
    _install_openai_stub()
    _install_git_stub()
    _install_dbt_stub()
    _install_databricks_stub()
