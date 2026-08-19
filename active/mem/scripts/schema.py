#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "copier>=9.0.0",
#   "jinja2>=3.1.0",
#   "pydantic>=2.0.0",
#   "pyyaml>=6.0.0",
# ]
# ///
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field, model_validator


SKILL_DIR = Path(__file__).resolve().parents[1]
REFERENCES_DIR = SKILL_DIR / "references" / "schemas"
DEFAULT_TEMPLATE = "default"
PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
PathStyle = Literal["directory", "dotted"]
PATH_STYLE_CHOICES: tuple[PathStyle, ...] = ("directory", "dotted")
DEFAULT_PATH_STYLE: PathStyle = "directory"


class VariableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str] = Field(default_factory=lambda: ["*"])
    default: str | None = None
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_shorthand(cls, value: Any) -> Any:
        if isinstance(value, list):
            return {"values": value}
        if isinstance(value, str):
            return {"values": [value]}
        return value


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_extension: str | None = None


class InsertionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_when: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)


class ChildSchemaRef(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: str | None = Field(default=None, alias="schema")
    path: str | None = None
    vars: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def coerce_shorthand(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"schema": value}
        return value

    @model_validator(mode="after")
    def require_one_reference(self) -> "ChildSchemaRef":
        if bool(self.schema_name) == bool(self.path):
            raise ValueError("children_from entries must set exactly one of schema or path")
        return self


class SchemaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    insertion_policy: InsertionPolicy | None = None
    template: str | None = None
    children: dict[str, "SchemaNode"] = Field(default_factory=dict)
    children_from: list[ChildSchemaRef] = Field(default_factory=list)
    dynamic_child: bool = False

    @model_validator(mode="before")
    @classmethod
    def coerce_shorthand(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"description": value, "template": DEFAULT_TEMPLATE}
        if isinstance(value, dict):
            children_from = value.get("children_from")
            if isinstance(children_from, (str, dict)):
                value = dict(value)
                value["children_from"] = [children_from]
        return value


class SchemaDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str | float
    output: OutputConfig = Field(default_factory=OutputConfig)
    variables: dict[str, VariableSpec] = Field(default_factory=dict)
    tree: dict[str, SchemaNode] = Field(alias="schema")

    @model_validator(mode="before")
    @classmethod
    def coerce_variables(cls, value: dict[str, Any]) -> dict[str, Any]:
        variables = value.get("variables", {})
        if isinstance(variables, list):
            merged: dict[str, Any] = {}
            for item in variables:
                if not isinstance(item, dict):
                    raise TypeError("variables list entries must be mappings")
                merged.update(item)
            value["variables"] = merged
        return value


SchemaNode.model_rebuild()


@dataclass(frozen=True)
class MaterializedFile:
    relative_path: Path
    template_path: Path
    context: dict[str, Any]


def should_materialize(node: SchemaNode) -> bool:
    if node.template is not None:
        return True
    return not node.children and not node.children_from


def load_schema(schema_name: str) -> tuple[Path, SchemaDocument]:
    schema_path = schema_path_for_name(schema_name)
    return load_schema_file(schema_path)


def load_schema_file(schema_path: Path) -> tuple[Path, SchemaDocument]:
    if not schema_path.exists():
        raise FileNotFoundError(f"schema not found: {schema_path}")
    data = yaml.safe_load(schema_path.read_text()) or {}
    return schema_path.parent, SchemaDocument.model_validate(data)


def schema_search_roots() -> list[Path]:
    cwd = Path.cwd().resolve(strict=False)
    roots = [directory / "schemas" for directory in (cwd, *cwd.parents)]
    roots.extend([Path.home() / ".schemas", REFERENCES_DIR])

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def schema_path_for_name(schema_name: str) -> Path:
    for root in schema_search_roots():
        candidate = root / schema_name / "schema.yaml"
        if candidate.is_file():
            return candidate.resolve(strict=False)
    return (REFERENCES_DIR / schema_name / "schema.yaml").resolve(strict=False)


def resolve_child_schema_path(parent_schema_dir: Path, child_ref: ChildSchemaRef) -> Path:
    if child_ref.schema_name:
        return schema_path_for_name(child_ref.schema_name)

    assert child_ref.path is not None
    child_path = Path(child_ref.path)
    if not child_path.is_absolute():
        child_path = parent_schema_dir / child_path
    if child_path.is_dir():
        child_path = child_path / "schema.yaml"
    return child_path.resolve()


def parse_assignments(assignments: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise ValueError(f"--var must use key=value form: {assignment}")
        key, value = assignment.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--var has an empty key: {assignment}")
        parsed[key] = value
    return parsed


def parse_include_paths(includes: list[str], path_style: PathStyle) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    for include in includes:
        normalized = include.strip()
        if "/" in normalized:
            parts = tuple(part for part in normalized.split("/") if part)
        elif path_style == "dotted":
            parts = tuple(part for part in normalized.split(".") if part)
        else:
            parts = (normalized,)
        if not parts:
            raise ValueError(f"--include has an empty path: {include}")
        paths.append(parts)
    return paths


def normalized_file_extension(file_extension: str | None) -> str | None:
    if not file_extension:
        return None
    return file_extension if file_extension.startswith(".") else f".{file_extension}"


def inspect_existing_path_style(destination: Path, file_extension: str | None = None) -> PathStyle | None:
    if not destination.is_dir():
        return None

    expected_suffix = normalized_file_extension(file_extension)
    dotted_signals = 0
    directory_signals = 0
    scanned = 0
    for path in destination.rglob("*"):
        if not path.is_file():
            continue
        if expected_suffix and path.suffix != expected_suffix:
            continue
        scanned += 1
        if path.parent == destination and "." in path.stem:
            dotted_signals += 1
        elif path.parent != destination:
            directory_signals += 1
        if scanned >= 500:
            break

    if dotted_signals > directory_signals:
        return "dotted"
    if directory_signals > dotted_signals:
        return "directory"
    return None


def infer_path_style(destination: Path, includes: list[str], file_extension: str | None = None) -> PathStyle:
    normalized_includes = [include.strip() for include in includes if include.strip()]
    if any("/" in include for include in normalized_includes):
        return "directory"
    if any("." in include for include in normalized_includes):
        return "dotted"
    return inspect_existing_path_style(destination, file_extension) or DEFAULT_PATH_STYLE


def include_state(segments: tuple[str, ...], include_paths: list[tuple[str, ...]]) -> tuple[bool, bool]:
    exact = False
    descendant = False
    for include_path in include_paths:
        if include_path == segments:
            exact = True
        elif len(include_path) > len(segments) and include_path[: len(segments)] == segments:
            descendant = True
    return exact, descendant


def validate_variables(document: SchemaDocument, values: dict[str, str]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for name, spec in document.variables.items():
        if name in values:
            value = values[name]
        elif spec.default is not None:
            value = spec.default
        else:
            continue

        if "*" not in spec.values and value not in spec.values:
            allowed = ", ".join(spec.values)
            raise ValueError(f"{name}={value!r} is not allowed; expected one of: {allowed}")
        context[name] = value

    for name, value in values.items():
        context.setdefault(name, value)

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    context.setdefault("last_refreshed", now)
    context.setdefault("last_refreshed_by", "codex/mem")
    return context


def render_template_text(template: str, context: dict[str, Any]) -> str:
    env = Environment(undefined=StrictUndefined, autoescape=False)
    return env.from_string(template).render(**context)


def render_segment(segment: str, context: dict[str, Any], *, optional: bool) -> str | None:
    missing = [name for name in PLACEHOLDER_RE.findall(segment) if name not in context]
    if missing:
        if optional:
            return None
        joined = ", ".join(missing)
        raise ValueError(f"missing variable(s) for path segment {segment!r}: {joined}")
    return render_template_text(segment, context)


def render_child_vars(child_ref: ChildSchemaRef, context: dict[str, Any]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, value in child_ref.vars.items():
        template = str(value)
        missing = [variable for variable in PLACEHOLDER_RE.findall(template) if variable not in context]
        if missing:
            continue
        rendered[name] = render_template_text(template, context)
    return rendered


def find_template(schema_dir: Path, template_name: str) -> Path:
    candidates: list[Path] = []
    if template_name.endswith(".jinja"):
        candidates.append(schema_dir / template_name)
    else:
        candidates.append(schema_dir / f"{template_name}.jinja")
        candidates.extend(sorted(schema_dir.glob(f"{template_name}.*.jinja")))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path.name) for path in candidates)
    raise FileNotFoundError(f"template {template_name!r} not found in {schema_dir}; searched: {searched}")


def output_extension(document: SchemaDocument, template_path: Path) -> str:
    if document.output.file_extension:
        extension = document.output.file_extension
        return extension if extension.startswith(".") else f".{extension}"

    basename = template_path.name.removesuffix(".jinja")
    suffix = Path(basename).suffix
    return suffix


def title_for(segments: list[str]) -> str:
    last = segments[-1]
    if last.lower() in {"api", "cli"}:
        return last.upper()
    return last.replace("-", " ").replace("_", " ").title()


def relative_output_path(
    document: SchemaDocument,
    segments: list[str],
    template_path: Path,
    path_style: PathStyle,
) -> Path:
    extension = output_extension(document, template_path)
    if path_style == "dotted":
        return Path(".".join(segments) + extension)
    return Path(*segments[:-1], segments[-1] + extension)


def collect_files(
    schema_dir: Path,
    document: SchemaDocument,
    nodes: dict[str, SchemaNode],
    context: dict[str, Any],
    *,
    raw_path: tuple[str, ...] = (),
    rendered_segments: tuple[str, ...] = (),
    include_paths: list[tuple[str, ...]] | None = None,
    output_document: SchemaDocument | None = None,
    path_style: PathStyle = DEFAULT_PATH_STYLE,
    schema_stack: tuple[Path, ...] = (),
    blocked_segments: set[str] | None = None,
) -> list[MaterializedFile]:
    files: list[MaterializedFile] = []
    include_paths = include_paths or []
    output_document = output_document or document

    for raw_segment, node in nodes.items():
        rendered_segment = render_segment(raw_segment, context, optional=True)
        if rendered_segment is None:
            continue
        if blocked_segments and rendered_segment in blocked_segments:
            continue

        next_raw_path = raw_path + (raw_segment,)
        next_segments = rendered_segments + (rendered_segment,)
        include_exact, include_descendant = include_state(next_segments, include_paths)
        if not include_exact and not include_descendant:
            continue

        if should_materialize(node) and include_exact:
            template_name = node.template or DEFAULT_TEMPLATE
            template_path = find_template(schema_dir, template_name)
            file_context = dict(context)
            file_context.update(
                {
                    "description": node.description or "",
                    "dotted_path": ".".join(next_segments),
                    "path_segments": list(next_segments),
                    "raw_path_segments": list(next_raw_path),
                    "template": template_name,
                    "title": title_for(list(next_segments)),
                }
            )
            files.append(
                MaterializedFile(
                    relative_path=relative_output_path(
                        output_document,
                        list(next_segments),
                        template_path,
                        path_style,
                    ),
                    template_path=template_path,
                    context=file_context,
                )
            )

        files.extend(
            collect_files(
                schema_dir,
                document,
                node.children,
                context,
                raw_path=next_raw_path,
                rendered_segments=next_segments,
                include_paths=include_paths,
                output_document=output_document,
                path_style=path_style,
                schema_stack=schema_stack,
            )
        )
        files.extend(
            collect_mounted_child_files(
                schema_dir,
                output_document,
                node,
                context,
                next_raw_path,
                next_segments,
                include_paths=include_paths,
                path_style=path_style,
                schema_stack=schema_stack,
                existing_paths={item.relative_path for item in files},
            )
        )

    return files


def rendered_child_nodes(nodes: dict[str, SchemaNode], context: dict[str, Any]) -> dict[str, tuple[str, SchemaNode]]:
    rendered: dict[str, tuple[str, SchemaNode]] = {}
    for raw_segment, node in nodes.items():
        segment = render_segment(raw_segment, context, optional=True)
        if segment is not None:
            rendered[segment] = (raw_segment, node)
    return rendered


def collect_mounted_child_files(
    parent_schema_dir: Path,
    output_document: SchemaDocument,
    node: SchemaNode,
    parent_context: dict[str, Any],
    raw_path: tuple[str, ...],
    rendered_segments: tuple[str, ...],
    *,
    include_paths: list[tuple[str, ...]],
    path_style: PathStyle,
    schema_stack: tuple[Path, ...],
    existing_paths: set[Path],
) -> list[MaterializedFile]:
    files: list[MaterializedFile] = []
    explicit_children = rendered_child_nodes(node.children, parent_context)

    for child_ref in node.children_from:
        child_schema_path = resolve_child_schema_path(parent_schema_dir, child_ref)
        if child_schema_path in schema_stack:
            chain = " -> ".join(str(path) for path in (*schema_stack, child_schema_path))
            raise ValueError(f"children_from cycle detected: {chain}")

        child_schema_dir, child_document = load_schema_file(child_schema_path)
        child_values = render_child_vars(child_ref, parent_context)
        child_context = validate_variables(child_document, child_values)
        child_files = collect_mounted_document_files(
            child_schema_dir,
            child_document,
            child_context,
            parent_context,
            raw_path,
            rendered_segments,
            include_paths=include_paths,
            output_document=output_document,
            path_style=path_style,
            schema_stack=(*schema_stack, child_schema_path),
            explicit_children=explicit_children,
        )
        for item in child_files:
            if item.relative_path in existing_paths:
                continue
            existing_paths.add(item.relative_path)
            files.append(item)

    return files


def collect_mounted_document_files(
    child_schema_dir: Path,
    child_document: SchemaDocument,
    child_context: dict[str, Any],
    parent_context: dict[str, Any],
    raw_path: tuple[str, ...],
    rendered_segments: tuple[str, ...],
    *,
    include_paths: list[tuple[str, ...]],
    output_document: SchemaDocument,
    path_style: PathStyle,
    schema_stack: tuple[Path, ...],
    explicit_children: dict[str, tuple[str, SchemaNode]],
) -> list[MaterializedFile]:
    files: list[MaterializedFile] = []

    for child_raw_segment, child_node in child_document.tree.items():
        child_rendered_segment = render_segment(child_raw_segment, child_context, optional=True)
        if child_rendered_segment is None:
            continue

        next_raw_path = raw_path + (child_raw_segment,)
        next_segments = rendered_segments + (child_rendered_segment,)
        include_exact, include_descendant = include_state(next_segments, include_paths)
        if not include_exact and not include_descendant:
            continue

        if child_rendered_segment in explicit_children:
            _, parent_child_node = explicit_children[child_rendered_segment]
            blocked_segments = set(rendered_child_nodes(parent_child_node.children, parent_context))
            files.extend(
                collect_files(
                    child_schema_dir,
                    child_document,
                    child_node.children,
                    child_context,
                    raw_path=next_raw_path,
                    rendered_segments=next_segments,
                    include_paths=include_paths,
                    output_document=output_document,
                    path_style=path_style,
                    schema_stack=schema_stack,
                    blocked_segments=blocked_segments,
                )
            )
            files.extend(
                collect_mounted_child_files(
                    child_schema_dir,
                    output_document,
                    child_node,
                    child_context,
                    next_raw_path,
                    next_segments,
                    include_paths=include_paths,
                    path_style=path_style,
                    schema_stack=schema_stack,
                    existing_paths={item.relative_path for item in files},
                )
            )
            continue

        files.extend(
            collect_files(
                child_schema_dir,
                child_document,
                {child_raw_segment: child_node},
                child_context,
                raw_path=raw_path,
                rendered_segments=rendered_segments,
                include_paths=include_paths,
                output_document=output_document,
                path_style=path_style,
                schema_stack=schema_stack,
            )
        )

    return files


def run_copier_copy(source: Path, destination: Path, data: dict[str, Any], overwrite: bool) -> None:
    try:
        from copier import run_copy
    except ImportError as exc:
        raise RuntimeError("copier is required; run this script with `uv run` to install script dependencies") from exc

    try:
        run_copy(
            str(source),
            str(destination),
            data=data,
            defaults=True,
            overwrite=overwrite,
            unsafe=True,
            quiet=True,
        )
    except TypeError:
        run_copy(
            src_path=str(source),
            dst_path=str(destination),
            data=data,
            defaults=True,
            overwrite=overwrite,
            unsafe=True,
            quiet=True,
        )


def materialize(
    schema_name: str,
    destination: Path,
    values: dict[str, str],
    *,
    explicit_schema_path: Path | None = None,
    overwrite: bool,
    skip_existing: bool,
    includes: list[str],
    path_style: PathStyle | None,
    mount_root: str | None = None,
) -> list[Path]:
    schema_path = explicit_schema_path.resolve() if explicit_schema_path else schema_path_for_name(schema_name)
    schema_dir, document = load_schema_file(schema_path)
    resolved_path_style = path_style or infer_path_style(destination, includes, document.output.file_extension)
    include_paths = parse_include_paths(includes, resolved_path_style)
    context = validate_variables(document, values)
    effective_mount = mount_root if mount_root is not None else ("pkg" if schema_name == "pkg" else ".")
    mount_path = Path(effective_mount)
    if mount_path.is_absolute() or ".." in mount_path.parts or "\\" in effective_mount:
        raise ValueError("schema mount root must remain inside the output directory")
    mount_segments = tuple(segment for segment in mount_path.parts if segment != ".")
    files = collect_files(
        schema_dir,
        document,
        document.tree,
        context,
        raw_path=mount_segments,
        rendered_segments=mount_segments,
        include_paths=include_paths,
        path_style=resolved_path_style,
        schema_stack=(schema_path,),
    )
    if not files:
        raise ValueError(f"schema {schema_name!r} produced no files")

    written: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)

    for item in files:
        target = destination / item.relative_path
        if target.exists() and skip_existing:
            continue
        if target.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite existing file: {target}")

        with tempfile.TemporaryDirectory(prefix="mem-schema-copier-") as tmp:
            source = Path(tmp) / "template"
            source.mkdir()
            (source / "copier.yml").write_text("_answers_file: .copier-answers.yml\n")
            template_target = source / (str(item.relative_path) + ".jinja")
            template_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item.template_path, template_target)
            run_copier_copy(source, destination, item.context, overwrite=overwrite)

        answers_file = destination / ".copier-answers.yml"
        if answers_file.exists():
            answers_file.unlink()
        written.append(target)

    return written


def list_schemas() -> int:
    discovered: dict[str, Path] = {}
    for root in schema_search_roots():
        for schema_path in sorted(root.glob("*/schema.yaml")):
            discovered.setdefault(schema_path.parent.name, schema_path)

    for schema_name, schema_path in sorted(discovered.items()):
        try:
            _, document = load_schema_file(schema_path)
            roots = ", ".join(document.tree.keys())
            print(f"{schema_name}\troot: {roots}")
        except Exception as exc:
            print(f"{schema_name}\tinvalid: {exc}")
    return 0


def merge_schema_nodes_for_show(parent_node: SchemaNode, mounted_node: SchemaNode) -> SchemaNode:
    merged = parent_node.model_copy(deep=True)
    for segment, child_node in mounted_node.children.items():
        if segment in merged.children:
            merged.children[segment] = merge_schema_nodes_for_show(merged.children[segment], child_node)
        else:
            merged.children[segment] = child_node.model_copy(deep=True)
    return merged


def expanded_children_for_show(
    schema_dir: Path,
    node: SchemaNode,
    *,
    schema_stack: tuple[Path, ...],
) -> dict[str, SchemaNode]:
    children = {segment: child.model_copy(deep=True) for segment, child in node.children.items()}

    for child_ref in node.children_from:
        child_schema_path = resolve_child_schema_path(schema_dir, child_ref)
        if child_schema_path in schema_stack:
            chain = " -> ".join(str(path) for path in (*schema_stack, child_schema_path))
            raise ValueError(f"children_from cycle detected: {chain}")

        _, child_document = load_schema_file(child_schema_path)
        for segment, mounted_node in child_document.tree.items():
            if segment in children:
                children[segment] = merge_schema_nodes_for_show(children[segment], mounted_node)
            else:
                children[segment] = mounted_node.model_copy(deep=True)

    return children


def print_tree(
    nodes: dict[str, SchemaNode],
    *,
    schema_dir: Path,
    prefix: str = "",
    schema_stack: tuple[Path, ...] = (),
) -> None:
    items = list(nodes.items())
    for index, (segment, node) in enumerate(items):
        is_last = index == len(items) - 1
        connector = "`-- " if is_last else "|-- "
        print(f"{prefix}{connector}{segment}")
        child_prefix = prefix + ("    " if is_last else "|   ")
        print_tree(
            expanded_children_for_show(schema_dir, node, schema_stack=schema_stack),
            schema_dir=schema_dir,
            prefix=child_prefix,
            schema_stack=schema_stack,
        )


def collect_descriptions(
    nodes: dict[str, SchemaNode],
    *,
    schema_dir: Path,
    schema_stack: tuple[Path, ...],
    path: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    descriptions: list[tuple[str, str]] = []
    for segment, node in nodes.items():
        next_path = (*path, segment)
        if node.description:
            descriptions.append(("/".join(next_path), node.description))
        descriptions.extend(
            collect_descriptions(
                expanded_children_for_show(schema_dir, node, schema_stack=schema_stack),
                schema_dir=schema_dir,
                schema_stack=schema_stack,
                path=next_path,
            )
        )
    return descriptions


def print_descriptions(
    descriptions: list[tuple[str, str]],
) -> None:
    for path, description in descriptions:
        print(f"- {path}: {description}")


def show_schema(schema_name: str, explicit_schema_path: Path | None = None) -> int:
    schema_path = explicit_schema_path.resolve() if explicit_schema_path else schema_path_for_name(schema_name)
    schema_dir, document = load_schema_file(schema_path)
    extension = document.output.file_extension or "<template>"
    print(f"{schema_name} [version={document.version} extension={extension}]")
    if document.variables:
        print("|-- variables")
        variables = list(document.variables.items())
        for index, (name, spec) in enumerate(variables):
            connector = "`-- " if index == len(variables) - 1 else "|-- "
            default = f", default={spec.default}" if spec.default else ""
            print(f"|   {connector}{name}: {', '.join(spec.values)}{default}")
    if document.variables:
        print("|-- tree")
        print_tree(document.tree, schema_dir=schema_dir, prefix="    ", schema_stack=(schema_path,))
    else:
        print("|-- tree")
        print_tree(document.tree, schema_dir=schema_dir, prefix="    ", schema_stack=(schema_path,))
    return 0


def describe_schema(schema_name: str, explicit_schema_path: Path | None = None) -> int:
    schema_path = explicit_schema_path.resolve() if explicit_schema_path else schema_path_for_name(schema_name)
    schema_dir, document = load_schema_file(schema_path)
    descriptions = collect_descriptions(document.tree, schema_dir=schema_dir, schema_stack=(schema_path,))
    print_descriptions(descriptions)
    return 0


def validate_schema(schema_name: str, explicit_schema_path: Path | None = None) -> int:
    schema_path = explicit_schema_path.resolve() if explicit_schema_path else schema_path_for_name(schema_name)
    schema_dir, document = load_schema_file(schema_path)
    collect_descriptions(document.tree, schema_dir=schema_dir, schema_stack=(schema_path,))
    print(f"{schema_name}\tvalid\t{schema_path}")
    return 0


def add_schema_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--schema-path",
        type=Path,
        help="Use an explicit schema.yaml file instead of the bundled schema name.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schema",
        description="Materialize files from bundled schemas.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List available schemas.")

    show = subparsers.add_parser("show", help="Show a schema tree.")
    show.add_argument("schema")
    add_schema_path_argument(show)

    describe = subparsers.add_parser("describe", help="Show schema descriptions as Markdown bullets.")
    describe.add_argument("schema")
    add_schema_path_argument(describe)

    validate = subparsers.add_parser("validate", help="Validate a schema and its composed children.")
    validate.add_argument("schema")
    add_schema_path_argument(validate)

    materialize_parser = subparsers.add_parser("materialize", help="Materialize a schema into an output directory.")
    materialize_parser.add_argument("schema")
    add_schema_path_argument(materialize_parser)
    materialize_parser.add_argument("--out", required=True, type=Path, help="Output directory.")
    materialize_parser.add_argument(
        "--mount-root",
        help="Relative schema mount; use . to materialize without a root namespace.",
    )
    materialize_parser.add_argument("--var", action="append", default=[], help="Template variable in key=value form.")
    materialize_parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Optional full rendered schema path to materialize.",
    )
    materialize_parser.add_argument(
        "--path-style",
        choices=PATH_STYLE_CHOICES,
        help="Output path style. Defaults to include/output-root convention when omitted.",
    )
    materialize_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files.")
    materialize_parser.add_argument("--skip-existing", action="store_true", help="Leave existing files untouched.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            return list_schemas()
        if args.command == "show":
            return show_schema(args.schema, args.schema_path)
        if args.command == "describe":
            return describe_schema(args.schema, args.schema_path)
        if args.command == "validate":
            return validate_schema(args.schema, args.schema_path)
        if args.command == "materialize":
            if args.overwrite and args.skip_existing:
                raise ValueError("use either --overwrite or --skip-existing, not both")
            values = parse_assignments(args.var)
            written = materialize(
                args.schema,
                args.out.resolve(),
                values,
                explicit_schema_path=args.schema_path,
                overwrite=args.overwrite,
                skip_existing=args.skip_existing,
                includes=args.include,
                path_style=args.path_style,
                mount_root=args.mount_root,
            )
            for path in written:
                print(path)
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
