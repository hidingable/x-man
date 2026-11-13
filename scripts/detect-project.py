#!/usr/bin/env python3
"""项目特征探测器。

读构建文件、配置文件和 git 历史，推断 project-context.md 的 Tier 1 字段
（脚本能确定性判定的那些）。语义类字段（核心业务、目标用户、产品类型）
不在这里——那需要读代码，交给 agent。

支持 monorepo / 多工程同仓：先发现子工程，再逐个扫描技术栈，根级字段取并集。

输出 TSV 到 stdout：
  <字段名>\t<值>                          普通字段
  __structure__\t<目录树，\\n 转义>        项目结构
  __archetype__\t<形态>                   frontend|backend|fullstack|cli|
                                          library|mobile|monorepo|unknown
  __module__\t<相对路径>\t<形态>\t<技术栈摘要>   子工程（可 0..N 行）
"""

import glob
import json
import os
import re
import subprocess
import sys

# 列目录树时的降噪集合
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "target", "vendor", ".next",
    ".nuxt", "__pycache__", ".venv", "venv", ".idea", ".vscode", "coverage",
    ".turbo", ".cache", "out", ".ai-configs", "tmp", "temp", "docs", "test",
    "tests", "__tests__", "examples", "example", "scripts",
}

# 发现子工程时的跳过集合，必须比 SKIP_DIRS 窄得多：
# docs / examples / scripts / tests 都可能是 workspace 里的真实包
# （create-turbo 默认就生成 apps/docs），用 SKIP_DIRS 会把它们整个吞掉。
# 这里只排除构建产物和依赖目录——那些不可能是源码工程。
MODULE_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "target", "vendor", ".next",
    ".nuxt", "__pycache__", ".venv", "venv", ".idea", ".vscode", "coverage",
    ".turbo", ".cache", "out", ".ai-configs",
}

# 出现这些文件即认为该目录是一个独立工程
MANIFESTS = (
    "package.json", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "pyproject.toml", "requirements.txt", "Gemfile",
    "composer.json", "Package.swift", "Podfile", "pubspec.yaml",
)

# 源码扩展名 → 语言。用于没有任何构建清单的项目（纯脚本集合、Xcode 工程等）
# 兜底判定语言。只统计源码，构建产物和资源文件不算。
EXT_LANG = {
    ".swift": "Swift", ".kt": "Kotlin", ".java": "Java", ".py": "Python",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".vue": "Vue SFC", ".c": "C", ".h": "C/C++",
    ".cpp": "C++", ".cc": "C++", ".m": "Objective-C", ".mm": "Objective-C++",
    ".cs": "C#", ".sh": "Shell", ".lua": "Lua", ".dart": "Dart",
    ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir",
}


class Project:
    """单个工程目录的探测单元。"""

    def __init__(self, root):
        self.root = root
        self.pkg = self._read_json("package.json") or {}
        self.deps = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            val = self.pkg.get(key)
            if isinstance(val, dict):
                self.deps.update(val)

    # ── 基础 IO ──
    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def exists(self, *parts):
        return os.path.exists(self.p(*parts))

    def _read_json(self, *parts):
        try:
            with open(self.p(*parts), encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def text(self, *parts):
        try:
            with open(self.p(*parts), encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except Exception:
            return ""

    def glob_any(self, *names):
        try:
            entries = os.listdir(self.root)
        except OSError:
            return None
        for name in names:
            if name.endswith("*"):          # 前缀匹配，如 vite.config.*
                stem = name[:-1]
                for e in entries:
                    if e.startswith(stem):
                        return e
            elif name.startswith("*"):      # 后缀匹配，如 *.xcodeproj
                suffix = name[1:]
                for e in entries:
                    if e.endswith(suffix):
                        return e
            elif name in entries:
                return name
        return None

    def dep_ver(self, pkg):
        return str(self.deps[pkg]).lstrip("^~>=< ").strip()

    def has(self, *names):
        for n in names:
            if n in self.deps:
                return n
        return None

    # ── 各字段探测 ──
    def language(self):
        langs = []
        if self.exists("go.mod"):
            m = re.search(r"^go\s+([\d.]+)", self.text("go.mod"), re.M)
            langs.append(f"Go {m.group(1)}" if m else "Go")
        if self.exists("Cargo.toml"):
            langs.append("Rust")
        if self.exists("pyproject.toml") or self.exists("requirements.txt") or self.exists("setup.py"):
            m = re.search(r'requires-python\s*=\s*["\']([^"\']+)', self.text("pyproject.toml"))
            langs.append(f"Python {m.group(1)}" if m else "Python")
        if self.exists("pom.xml"):
            m = re.search(r"<java\.version>([^<]+)</java\.version>", self.text("pom.xml"))
            langs.append(f"Java {m.group(1)}" if m else "Java")
        elif self.exists("build.gradle") or self.exists("build.gradle.kts"):
            langs.append("Java/Kotlin (Gradle)")
        if self.exists("Gemfile"):
            langs.append("Ruby")
        if self.exists("composer.json"):
            langs.append("PHP")
        if self.pkg:
            if self.exists("tsconfig.json"):
                langs.append(f"TypeScript {self.dep_ver('typescript')}" if "typescript" in self.deps else "TypeScript")
            else:
                langs.append("JavaScript")
        return ", ".join(langs)

    def frontend(self):
        for pkg, label in (
            ("next", "Next.js"), ("nuxt", "Nuxt"), ("@remix-run/react", "Remix"),
            ("@angular/core", "Angular"), ("react", "React"), ("vue", "Vue"),
            ("svelte", "Svelte"), ("solid-js", "Solid"),
        ):
            if pkg in self.deps:
                return f"{label} {self.dep_ver(pkg)}".strip()
        return ""

    def ui(self):
        hits = []
        for pkg, label in (
            ("antd", "Ant Design"), ("element-plus", "Element Plus"),
            ("@mui/material", "MUI"), ("naive-ui", "Naive UI"),
            ("@chakra-ui/react", "Chakra UI"), ("vuetify", "Vuetify"),
            ("dpl-react", "DPL React"), ("react-better-table", "react-better-table"),
            ("@arco-design/web-react", "Arco Design"),
        ):
            if pkg in self.deps:
                hits.append(label)
        if self.exists("components.json") and self.has("tailwindcss"):
            hits.append("shadcn/ui")
        if self.has("tailwindcss"):
            hits.append("Tailwind CSS")
        return ", ".join(hits)

    def state(self):
        hits = []
        for pkg, label in (
            ("@reduxjs/toolkit", "Redux Toolkit"), ("redux", "Redux"),
            ("zustand", "Zustand"), ("pinia", "Pinia"), ("vuex", "Vuex"),
            ("mobx", "MobX"), ("jotai", "Jotai"), ("recoil", "Recoil"),
            ("@tanstack/react-query", "TanStack Query"),
        ):
            if pkg in self.deps:
                hits.append(label)
        return ", ".join(hits)

    def backend(self):
        for pkg, label in (
            ("@nestjs/core", "NestJS"), ("express", "Express"), ("koa", "Koa"),
            ("fastify", "Fastify"), ("@hapi/hapi", "Hapi"),
        ):
            if pkg in self.deps:
                return f"{label} {self.dep_ver(pkg)}".strip()
        pom = self.text("pom.xml") + self.text("build.gradle") + self.text("build.gradle.kts")
        if "spring-boot" in pom:
            m = re.search(r"<spring-boot\.version>([^<]+)", pom)
            return f"Spring Boot {m.group(1)}" if m else "Spring Boot"
        reqs = (self.text("requirements.txt") + self.text("pyproject.toml")).lower()
        for needle, label in (("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask")):
            if needle in reqs:
                return label
        gomod = self.text("go.mod")
        for needle, label in (("gin-gonic/gin", "Gin"), ("labstack/echo", "Echo"),
                              ("gofiber/fiber", "Fiber")):
            if needle in gomod:
                return label
        return ""

    def db(self):
        hits = []
        for pkg, label in (
            ("pg", "PostgreSQL"), ("mysql2", "MySQL"), ("mysql", "MySQL"),
            ("mongoose", "MongoDB"), ("mongodb", "MongoDB"),
            ("redis", "Redis"), ("ioredis", "Redis"),
            ("better-sqlite3", "SQLite"), ("sqlite3", "SQLite"),
        ):
            if pkg in self.deps and label not in hits:
                hits.append(label)
        for orm, label in (("prisma", "Prisma"), ("typeorm", "TypeORM"),
                           ("sequelize", "Sequelize"), ("drizzle-orm", "Drizzle")):
            if orm in self.deps:
                hits.append(label)
        if self.exists("prisma", "schema.prisma"):
            m = re.search(r'provider\s*=\s*"(\w+)"', self.text("prisma", "schema.prisma"))
            if m and m.group(1) != "prisma-client-js":
                hits.append(m.group(1))
        return ", ".join(dict.fromkeys(hits))

    def build(self):
        hit = self.glob_any("vite.config.*", "webpack.config.*", "rollup.config.*",
                            "next.config.*", "nuxt.config.*", "turbo.json",
                            "rsbuild.config.*", "esbuild.config.*")
        if hit:
            return {
                "vite": "Vite", "webpack": "Webpack", "rollup": "Rollup",
                "next": "Turbopack/Next.js", "nuxt": "Nuxt", "turbo": "Turborepo",
                "rsbuild": "Rsbuild", "esbuild": "esbuild",
            }.get(hit.split(".")[0], hit)
        if self.exists("pom.xml"):
            return "Maven"
        if self.exists("build.gradle") or self.exists("build.gradle.kts"):
            return "Gradle"
        if self.exists("Cargo.toml"):
            return "Cargo"
        if self.exists("Makefile"):
            return "Make"
        return ""

    def pm(self):
        pm_field = self.pkg.get("packageManager")
        if isinstance(pm_field, str) and pm_field:
            return pm_field.replace("@", " ")
        if self.exists("pnpm-workspace.yaml"):
            return "pnpm"
        for lock, label in (("pnpm-lock.yaml", "pnpm"), ("bun.lockb", "bun"),
                            ("yarn.lock", "yarn"), ("package-lock.json", "npm")):
            if self.exists(lock):
                return label
        for lock, label in (("poetry.lock", "poetry"), ("uv.lock", "uv"),
                            ("Pipfile.lock", "pipenv"), ("go.sum", "go modules"),
                            ("Cargo.lock", "cargo")):
            if self.exists(lock):
                return label
        return ""

    def style(self):
        hits = []
        if self.glob_any("eslint.config.*", ".eslintrc*"):
            hits.append("ESLint")
        if self.glob_any(".prettierrc*", "prettier.config.*"):
            hits.append("Prettier")
        if self.exists("biome.json") or self.exists("biome.jsonc"):
            hits.append("Biome")
        if self.glob_any("ruff.toml", ".ruff.toml") or "[tool.ruff]" in self.text("pyproject.toml"):
            hits.append("Ruff")
        if self.glob_any(".golangci.yml", ".golangci.yaml"):
            hits.append("golangci-lint")
        if self.exists(".editorconfig"):
            hits.append("EditorConfig")
        return " + ".join(hits)

    def test(self):
        hits = []
        for pkg, label in (("vitest", "Vitest"), ("jest", "Jest"),
                           ("@playwright/test", "Playwright"), ("cypress", "Cypress"),
                           ("mocha", "Mocha")):
            if pkg in self.deps:
                hits.append(label)
        reqs = (self.text("requirements.txt") + self.text("pyproject.toml")).lower()
        if "pytest" in reqs:
            hits.append("pytest")
        pom = self.text("pom.xml")
        if "junit" in pom:
            hits.append("JUnit")
        return ", ".join(hits)

    def deploy(self):
        hits = []
        wf = self.p(".github", "workflows")
        if os.path.isdir(wf):
            try:
                n = len([f for f in os.listdir(wf) if f.endswith((".yml", ".yaml"))])
                hits.append(f"GitHub Actions（{n} 个 workflow）")
            except OSError:
                hits.append("GitHub Actions")
        if self.exists(".gitlab-ci.yml"):
            hits.append("GitLab CI")
        if self.exists("Jenkinsfile"):
            hits.append("Jenkins")
        if self.glob_any("Dockerfile", "Dockerfile.*"):
            hits.append("Docker")
        if self.exists("docker-compose.yml") or self.exists("compose.yaml"):
            hits.append("Docker Compose")
        if self.exists("vercel.json"):
            hits.append("Vercel")
        if self.exists("wrangler.toml") or self.exists("wrangler.jsonc"):
            hits.append("Cloudflare Workers")
        if os.path.isdir(self.p("k8s")) or os.path.isdir(self.p("helm")):
            hits.append("Kubernetes")
        return ", ".join(hits)

    def archetype(self):
        fe, be, db = self.frontend(), self.backend(), self.db()
        if self.has("react-native", "expo") or self.exists("pubspec.yaml"):
            return "mobile"
        # Xcode / SwiftPM 工程：没有常规清单，靠目录后缀认
        if self.exists("Package.swift") or self.exists("Podfile") or \
                self.glob_any("*.xcodeproj", "*.xcworkspace"):
            return "mobile"
        if fe and (be or db):
            return "fullstack"
        if fe:
            return "frontend"
        if be or db:
            return "backend"
        if self.pkg.get("bin") or os.path.isdir(self.p("cmd")):
            return "cli"
        if self.pkg.get("main") or self.pkg.get("exports") or self.exists("Cargo.toml"):
            return "library"
        return "unknown"

    def stack_summary(self):
        """子工程一行摘要。用 · 分隔——这行会落进 markdown 表格单元格，
        不能用 | ，否则会把表格列冲掉。"""
        parts = [self.language(), self.frontend(), self.ui(), self.state(),
                 self.backend(), self.db(), self.build()]
        return " · ".join(x for x in parts if x)


# ─── monorepo 发现 ───

def is_project_dir(path):
    return any(os.path.exists(os.path.join(path, m)) for m in MANIFESTS)


def workspace_globs(root):
    """从 workspace 声明文件里取子工程目录 glob。"""
    globs = []
    pkg_path = os.path.join(root, "package.json")
    try:
        with open(pkg_path, encoding="utf-8") as fh:
            data = json.load(fh)
        ws = data.get("workspaces")
        if isinstance(ws, list):
            globs += ws
        elif isinstance(ws, dict) and isinstance(ws.get("packages"), list):
            globs += ws["packages"]
    except Exception:
        pass
    ws_yaml = os.path.join(root, "pnpm-workspace.yaml")
    if os.path.exists(ws_yaml):
        try:
            with open(ws_yaml, encoding="utf-8") as fh:
                for line in fh:
                    m = re.match(r"\s*-\s*['\"]?([^'\"\n]+)", line)
                    if m:
                        globs.append(m.group(1).strip())
        except Exception:
            pass
    return globs


def declared_modules(root, globs):
    """按 workspace 声明的 glob 展开子工程目录。

    BFS 有 max_depth 限制，声明的 glob 没有——packages/** 这种深层布局
    只有按声明展开才能发现。排除项（! 开头）和命中的独立仓库目录跳过。
    """
    found = []
    for g in globs:
        g = g.strip().strip("'\"")
        if not g or g.startswith("!"):
            continue
        for match in glob.glob(os.path.join(root, g), recursive=True):
            if not os.path.isdir(match):
                continue
            if os.path.exists(os.path.join(match, ".git")):
                continue
            rel = os.path.relpath(match, root)
            if set(rel.split(os.sep)) & MODULE_SKIP_DIRS:
                continue
            if is_project_dir(match):
                found.append(rel)
    return found


# 未声明 workspace 时，只有这些父目录下的深层目录才算子工程。
# 否则像 x-mansion 这种 skills/<name>/ 各自带依赖的仓库会被误判成 monorepo。
CONVENTIONAL_PARENTS = {
    "apps", "packages", "services", "libs", "modules", "projects",
    "sites", "servers", "clients", "components", "workspaces",
}


def discover_modules(root, max_depth=2):
    """发现子工程，返回相对路径列表。

    BFS 受 max_depth 限制；声明了 workspace 时另按声明的 glob 展开
    （不受深度限制），两者取并集。含独立 .git 的目录一律跳过。
    """
    found = []
    globs = workspace_globs(root)
    declared = bool(globs) or any(
        os.path.exists(os.path.join(root, f))
        for f in ("pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json")
    )

    def walk(cur_rel, depth):
        if depth > max_depth:
            return
        cur_abs = os.path.join(root, cur_rel) if cur_rel else root
        try:
            entries = sorted(os.listdir(cur_abs))
        except OSError:
            return
        for e in entries:
            if e.startswith(".") or e in MODULE_SKIP_DIRS:
                continue
            abs_p = os.path.join(cur_abs, e)
            if not os.path.isdir(abs_p):
                continue
            rel = os.path.join(cur_rel, e) if cur_rel else e
            # 有独立 .git 的目录是另一个仓库（submodule / vendored /
            # 工作区内嵌的独立仓），不是本项目的子工程，整棵跳过。
            if os.path.exists(os.path.join(abs_p, ".git")):
                continue
            if is_project_dir(abs_p):
                found.append(rel)
                # 找到工程就不再往里钻（避免把它自己的子包也列出来）
                continue
            walk(rel, depth + 1)

    walk("", 1)

    if declared:
        # 声明了 workspace 就信任声明：glob 命中的包不受 max_depth 限制
        # （packages/** 下 depth>2 的包也能发现），与 BFS 结果取并集。
        for rel in declared_modules(root, globs):
            if rel not in found:
                found.append(rel)
        found.sort()
    else:
        # 没有 workspace 声明时收紧：只认根的直接子目录，以及 apps/ packages/
        # 这类约定目录下的一层。这样 frontend/ + backend/ 的常见布局仍然识别，
        # 而 skills/<name>/ 这种"每个子目录各带依赖的集合"不会被误判。
        kept = []
        for rel in found:
            parts = rel.split(os.sep)
            if len(parts) == 1:
                kept.append(rel)
            elif len(parts) == 2 and parts[0] in CONVENTIONAL_PARENTS:
                kept.append(rel)
        found = kept

    return found, declared


def git(root, *args):
    try:
        out = subprocess.run(["git", "-C", root, *args],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def repo_url(root):
    for remote in ("github", "origin", "upstream"):
        url = git(root, "remote", "get-url", remote)
        if url:
            return url
    return ""


def branch_strategy(root):
    branches = git(root, "branch", "-r")
    if not branches:
        return ""
    names = {b.strip().split("/")[-1] for b in branches.splitlines()}
    has_dev = bool({"develop", "dev"} & names)
    has_release = any(n.startswith("release") for n in names)
    if has_dev and has_release:
        return "Git Flow（develop + release 分支）"
    if has_dev:
        return "Git Flow 简化版（develop 分支）"
    return "Trunk-based（主干开发）"


CONVENTIONAL = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]*\))?!?:\s"
)


def commit_convention(root):
    log = git(root, "log", "--no-merges", "--pretty=%s", "-n", "50")
    lines = [l for l in log.splitlines() if l.strip()]
    if not lines:
        return ""
    hits = sum(1 for l in lines if CONVENTIONAL.match(l))
    ratio = hits / len(lines)
    if ratio >= 0.8:
        return f"Conventional Commits（近 {len(lines)} 条命中 {hits} 条）"
    if ratio >= 0.4:
        return f"部分遵循 Conventional Commits（近 {len(lines)} 条命中 {hits} 条，未统一）"
    return ""


def structure(root, modules):
    if modules:
        lines = []
        for rel in modules[:20]:
            lines.append(f"{rel}/")
        if len(modules) > 20:
            lines.append(f"... 另有 {len(modules) - 20} 个子工程")
        return "\n".join(lines)
    base = None
    for cand in ("src", "app", "lib", "internal", "cmd"):
        if os.path.isdir(os.path.join(root, cand)):
            base = cand
            break
    if base is None:
        return ""
    try:
        subs = sorted(
            d for d in os.listdir(os.path.join(root, base))
            if os.path.isdir(os.path.join(root, base, d))
            and not d.startswith(".") and d not in SKIP_DIRS
        )
    except OSError:
        return ""
    if not subs:
        return ""
    lines = [f"{base}/"] + [f"  {d}/" for d in subs[:15]]
    if len(subs) > 15:
        lines.append(f"  ... 另有 {len(subs) - 15} 个目录")
    return "\n".join(lines)


def language_by_extension(root, max_files=4000):
    """没有构建清单时，靠源码扩展名统计兜底判定语言。

    真实项目里这类不少：纯 .py 脚本集合、Xcode 工程、只有 .sh 的工具仓。
    只统计源码扩展名，且对遍历量设上限，避免在大仓上卡住。
    """
    counts = {}
    scanned = 0
    for cur, dirs, files in os.walk(root):
        # 有独立 .git 的目录是另一个仓库，不计入本项目的语言统计
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS
                   and not os.path.exists(os.path.join(cur, d, ".git"))]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            lang = EXT_LANG.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
            scanned += 1
            if scanned >= max_files:
                break
        if scanned >= max_files:
            break

    if not counts:
        return ""
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    total = sum(counts.values())
    # 只报占比 >=10% 的语言，最多 3 个——避免把零星的 .sh 也列进主语言。
    # 不报具体文件数：遍历有 max_files 上限且过滤了 SKIP_DIRS，得到的是抽样
    # 而非总量，报出来会误导。占比只用于内部排序取舍。
    picked = [lang for lang, n in ranked[:3] if n / total >= 0.10]
    return ", ".join(picked)


def swift_project(root):
    """Xcode 工程没有普通意义上的清单文件，靠目录后缀识别。"""
    try:
        entries = os.listdir(root)
    except OSError:
        return ""
    for e in entries:
        if e.endswith(".xcworkspace"):
            return f"Xcode workspace（{e}）"
        if e.endswith(".xcodeproj"):
            return f"Xcode 工程（{e}）"
    if os.path.exists(os.path.join(root, "Package.swift")):
        return "Swift Package Manager"
    return ""


def union(values):
    """合并多个子工程的同名字段，去重保序。"""
    seen = []
    for v in values:
        for part in (x.strip() for x in v.split(",")):
            if part and part not in seen:
                seen.append(part)
    return ", ".join(seen)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    root_proj = Project(root)
    module_rels, declared = discover_modules(root)

    # 根目录本身是不是一个实打实的工程（有依赖、有框架）
    root_is_project = bool(root_proj.deps) or any(
        root_proj.exists(m) for m in MANIFESTS if m != "package.json"
    )
    modules = [(rel, Project(os.path.join(root, rel))) for rel in module_rels]
    # 只有一个子工程且根目录没内容时，不当 monorepo 处理
    is_mono = len(modules) >= 2 or (declared and len(modules) >= 1)
    # 根目录不是工程、但底下正好有一个工程（如仓库里只有 web/ 或 backend/）：
    # 这不是 monorepo，只是嵌了一层，技术栈应当取那个工程而不是空手而归。
    nested_single = (not is_mono) and (not root_is_project) and len(modules) == 1

    out = {}

    def emit(field, value):
        if value:
            out[field] = " ".join(str(value).split())

    # 基础信息始终取根
    emit("项目名称", root_proj.pkg.get("name") or os.path.basename(root))
    emit("项目描述", root_proj.pkg.get("description"))
    emit("当前版本", root_proj.pkg.get("version"))
    emit("仓库地址", repo_url(root))
    emit("Git 分支策略", branch_strategy(root))
    emit("提交规范", commit_convention(root))
    emit("部署方式", root_proj.deploy())

    # 技术栈：monorepo 取子工程并集，嵌套单工程取那个子工程，否则取根
    if is_mono:
        sources = [p for _, p in modules]
        if root_is_project:
            sources = [root_proj] + sources
    elif nested_single:
        sources = [modules[0][1]]
    else:
        sources = [root_proj]

    # 语言：清单优先；一无所获时回退到扩展名统计（纯脚本集合 / Xcode 工程）
    lang = union([s.language() for s in sources])
    if not lang:
        lang = language_by_extension(root)
    emit("语言", lang)
    emit("前端框架", union([s.frontend() for s in sources]))
    emit("UI 组件库", union([s.ui() for s in sources]))
    emit("状态管理", union([s.state() for s in sources]))
    emit("后端框架", union([s.backend() for s in sources]))
    emit("数据库", union([s.db() for s in sources]))
    # 构建工具：清单优先，回退到 Xcode / SwiftPM（它们没有常规清单文件）
    build = union([s.build() for s in sources]) or swift_project(root)
    emit("构建工具", build)
    # 包管理器和代码风格是仓库级配置，子工程往往不各自声明，回退到根
    emit("包管理器", union([s.pm() for s in sources]) or root_proj.pm())
    emit("代码风格", union([s.style() for s in sources]) or root_proj.style())

    tests = union([s.test() for s in sources])
    if tests:
        emit("测试要求", f"已接入 {tests}（覆盖率要求需人工确认）")

    for k, v in out.items():
        print(f"{k}\t{v}")

    struct = structure(root, module_rels if is_mono else [])
    if struct:
        print("__structure__\t" + struct.replace("\n", "\\n"))

    if is_mono:
        print("__archetype__\tmonorepo")
        for rel, proj in modules:
            summary = proj.stack_summary() or "(未识别技术栈)"
            print(f"__module__\t{rel}\t{proj.archetype()}\t{summary}")
    elif nested_single:
        print("__archetype__\t" + modules[0][1].archetype())
    else:
        print("__archetype__\t" + root_proj.archetype())


if __name__ == "__main__":
    main()
