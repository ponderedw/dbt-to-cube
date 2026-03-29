"""
Offline dbt macro resolver for [[ macro_call() ]] patterns in metric SQL.

Loads macro definitions from dbt project / package .sql files and evaluates
them using Jinja2 — no database connection required.

${...} references are intentionally left intact so Cube.js can handle them
natively as measure/dimension references.
"""
import os
import re
from typing import Dict, Optional, Tuple
from jinja2 import Environment


class MacroResolver:
    """
    Resolves [[ macro_call(args) ]] expressions in metric SQL by loading
    macro definitions from dbt project and dbt_packages macro directories.

    Usage:
        resolver = MacroResolver.from_project_dir('/path/to/dbt_project')
        resolved = resolver.resolve("[[ safe_divide('${a}', '${b}') ]]")
        # → "${a} / NULLIF(${b}, 0)"
    """

    def __init__(self, project_dirs: list):
        """
        Args:
            project_dirs: list of (directory_path, package_name_or_None) tuples.
                          package_name is used to register namespace-qualified
                          calls like dbt_simple_metrics.safe_divide(…).
        """
        self._macro_defs: Dict[str, str] = {}           # name  -> full {% macro %}…{% endmacro %} string
        self._pkg_macro_defs: Dict[str, Dict[str, str]] = {}  # pkg -> {name -> macro_def}

        for dirpath, pkg_name in project_dirs:
            self._load_dir(dirpath, pkg_name)

        self._env = self._build_env()

    # ── public ────────────────────────────────────────────────────────────────

    @classmethod
    def from_manifest(cls, manifest: dict) -> "MacroResolver":
        """
        Build a MacroResolver directly from a parsed manifest.json dict.
        Uses the macro_sql field that dbt writes for every macro, so no
        separate project directory or database connection is needed.
        """
        instance = cls.__new__(cls)
        instance._macro_defs = {}
        instance._pkg_macro_defs = {}

        for node in manifest.get('macros', {}).values():
            macro_sql = node.get('macro_sql', '')
            pkg_name = node.get('package_name') or None
            if macro_sql:
                instance._parse_macros(macro_sql, pkg_name)

        instance._env = instance._build_env()
        return instance

    @classmethod
    def from_project_dir(cls, project_dir: str) -> "MacroResolver":
        """
        Build a MacroResolver from a dbt project root directory.
        Scans project macros/ and dbt_packages/*/macros/ automatically.
        """
        dirs = [(project_dir, None)]

        packages_dir = os.path.join(project_dir, 'dbt_packages')
        if os.path.isdir(packages_dir):
            for pkg in os.listdir(packages_dir):
                pkg_path = os.path.join(packages_dir, pkg)
                if os.path.isdir(pkg_path):
                    dirs.append((pkg_path, pkg))

        return cls(dirs)

    def resolve(self, sql_expr: str) -> str:
        """
        Resolve any [[ macro_call(args) ]] patterns in sql_expr.
        Returns the expression unchanged if no [[ ]] are present.
        """
        if '[[' not in sql_expr:
            return sql_expr
        jinja_expr = sql_expr.replace('[[', '{{').replace(']]', '}}')
        try:
            return self._env.from_string(jinja_expr).render().strip()
        except Exception as exc:
            print(f"  Warning: could not resolve macro in '{sql_expr}': {exc}")
            return sql_expr

    # ── private ───────────────────────────────────────────────────────────────

    def _load_dir(self, dirpath: str, pkg_name: Optional[str]):
        macros_dir = os.path.join(dirpath, 'macros')
        if not os.path.isdir(macros_dir):
            return
        for root, _, files in os.walk(macros_dir):
            for fname in files:
                if fname.endswith('.sql'):
                    fpath = os.path.join(root, fname)
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        self._parse_macros(f.read(), pkg_name)

    _MACRO_RE = re.compile(
        r'\{%-?\s*macro\s+(\w+)\s*\(([^)]*)\)\s*-?%\}(.*?)\{%-?\s*endmacro\s*-?%\}',
        re.DOTALL,
    )

    def _parse_macros(self, content: str, pkg_name: Optional[str]):
        for m in self._MACRO_RE.finditer(content):
            name = m.group(1)
            args = m.group(2).strip()
            body = m.group(3)
            macro_def = f"{{% macro {name}({args}) %}}{body}{{% endmacro %}}"
            self._macro_defs[name] = macro_def
            if pkg_name is not None:
                self._pkg_macro_defs.setdefault(pkg_name, {})[name] = macro_def

    def _build_env(self) -> Environment:
        env = Environment(extensions=['jinja2.ext.do'])

        if not self._macro_defs:
            return env

        # Build one template that defines every macro, then extract them as a
        # Jinja2 template module so they are proper callable macro objects.
        # Compile each macro individually and skip any that fail (e.g. macros
        # that reference dbt-specific globals not available outside dbt runtime).
        valid_defs = []
        for name, macro_def in self._macro_defs.items():
            try:
                env.parse(macro_def)
                valid_defs.append(macro_def)
            except Exception:
                pass  # skip macros with dbt-only syntax we can't parse

        if not valid_defs:
            return env

        all_defs = '\n'.join(valid_defs)
        module = env.from_string(all_defs).module

        # Register each macro as an unqualified global (e.g. safe_divide(…))
        for name in self._macro_defs:
            fn = getattr(module, name, None)
            if fn is not None:
                env.globals[name] = fn

        # Register package-namespaced globals (e.g. dbt_simple_metrics.safe_divide(…))
        for pkg_name, macros in self._pkg_macro_defs.items():
            valid_pkg_defs = []
            for macro_def in macros.values():
                try:
                    env.parse(macro_def)
                    valid_pkg_defs.append(macro_def)
                except Exception:
                    pass

            if not valid_pkg_defs:
                continue

            pkg_module = env.from_string('\n'.join(valid_pkg_defs)).module
            ns = _AttrDict({
                macro_name: getattr(pkg_module, macro_name)
                for macro_name in macros
                if getattr(pkg_module, macro_name, None) is not None
            })
            env.globals[pkg_name] = ns

        return env


class _AttrDict(dict):
    """Dict whose keys are also accessible as attributes (for Jinja2 namespace access)."""
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)
