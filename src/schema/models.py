"""parameters.yaml の型付きモデル（pydantic v2）。

A-2 の出力（因果モデル）を構造検証して読み込む。kind ごとに必須フィールドが異なる。
DSL 式（constraints / oracle.rules / relations / derived.expr / plus_if.when）は
文字列として保持し、パース・意味検証は a2_lint.py が dsl パーサで行う。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LookupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")  # 写像のキーになるパラメータ名
    map: Dict[str, int]               # 値 -> チャンネル数 などの写像


class PlusIf(BaseModel):
    model_config = ConfigDict(extra="forbid")
    when: str   # DSL 条件。真なら add を加算
    add: int


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: Literal["independent", "derived", "coupled"]
    # independent
    values: Optional[List[Union[str, int]]] = None
    # derived（lookup+plus_if もしくは expr）
    lookup: Optional[LookupSpec] = None
    plus_if: Optional[PlusIf] = None
    expr: Optional[str] = None
    # coupled
    group: Optional[str] = None
    partitions: Optional[List[int]] = None

    @model_validator(mode="after")
    def _check_kind(self) -> "Parameter":
        if self.kind == "independent":
            if not self.values:
                raise ValueError(f"parameter '{self.name}': independent には values が必要")
        elif self.kind == "derived":
            if not (self.lookup or self.expr):
                raise ValueError(f"parameter '{self.name}': derived には lookup か expr が必要")
        elif self.kind == "coupled":
            if not self.group or not self.partitions:
                raise ValueError(f"parameter '{self.name}': coupled には group と partitions が必要")
        return self


class Oracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hit_policy: Literal["first"] = "first"
    rules: List[str]                       # DSL: when <cond> then usable|unusable
    otherwise: Literal["usable", "unusable"]


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_dimension: Optional[int] = None
    max_file_size: Optional[int] = None


class ParametersModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    parameters: List[Parameter]
    relations: List[str] = []              # DSL: <name> = <arith>
    interactions: List[List[str]] = []     # 強相互作用ペア（フル網羅）
    constraints: List[str] = []            # DSL: when <cond> then <cond>
    oracle: Oracle
    limits: Limits = Limits()
    notes: List[str] = []

    # --- 便利アクセサ ---
    def independent(self) -> List[Parameter]:
        return [p for p in self.parameters if p.kind == "independent"]

    def derived(self) -> List[Parameter]:
        return [p for p in self.parameters if p.kind == "derived"]

    def coupled(self) -> List[Parameter]:
        return [p for p in self.parameters if p.kind == "coupled"]

    def groups(self) -> Dict[str, List[Parameter]]:
        out: Dict[str, List[Parameter]] = {}
        for p in self.coupled():
            out.setdefault(p.group, []).append(p)
        return out

    def by_name(self) -> Dict[str, Parameter]:
        return {p.name: p for p in self.parameters}

    def all_names(self) -> set:
        return {p.name for p in self.parameters}


def load_parameters(path: str | Path) -> ParametersModel:
    """parameters.yaml を読み込み、構造検証して返す。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ParametersModel.model_validate(data)
